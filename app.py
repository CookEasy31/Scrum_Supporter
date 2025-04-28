import streamlit as st
import google.generativeai as genai
import fitz  # PyMuPDF
import os
from dotenv import load_dotenv

# --- Konfiguration ---
PDF_PATH = "Oeffentliches_Gestalten.pdf"  # Sicherstellen, dass die PDF so heißt
MODEL_NAME = "gemini-2.5-flash-preview-04-17" # Verwende das aktuellste Flash-Modell

# API Key aus Streamlit Secrets oder Umgebungsvariablen laden
def get_api_key():
    """Holt den API Key aus Streamlit Secrets oder .env Datei"""
    try:
        # Versuche zuerst, den Key aus Streamlit Secrets zu laden
        return st.secrets["GOOGLE_API_KEY"]
    except Exception:
        # Fallback zur .env Datei für lokale Entwicklung
        load_dotenv()
        return os.getenv("GOOGLE_API_KEY")

API_KEY = get_api_key()

# --- Konstanten für UI & Styling ---
# Verbesserte Farbpalette für modernen Dark Mode
PRIMARY_COLOR = "#8A2BE2"  # Kräftigeres Violett (BlueViolet)
SECONDARY_COLOR = "#FF1493"  # Kräftigeres Pink (DeepPink)
BG_DARK = "#121212"  # Sehr dunkler Hintergrund
CARD_BG_DARK = "#1E1E1E"  # Etwas hellere Karten
TEXT_COLOR_LIGHT = "#F0F0F0"  # Helles Grau für Text (besserer Kontrast)
TEXT_COLOR_MEDIUM = "#A0A0A0" # Mittleres Grau für sekundären Text
BORDER_COLOR = "#333333"    # Dezente Trennlinien/Ränder
SIDEBAR_BG = "#181818"  # Dunkler Sidebar-Hintergrund

PAGE_CONFIG = {
    "layout": "wide",
    "page_title": "💡 Creative Director AI Hilfstool",
    "page_icon": "", # Emoji geändert für "Idee"
    "initial_sidebar_state": "expanded"
}

# --- Hilfsfunktionen ---

@st.cache_data(ttl=3600)  # Cache für 1 Stunde, um Änderungen an der PDF zu ermöglichen
def extract_pdf_data(pdf_path):
    """
    Extrahiert den vollständigen Text und versucht, ein Inhaltsverzeichnis zu generieren.
    Gibt Text, ToC-String und potenzielle Fehler zurück.
    """
    toc_text = "Inhaltsverzeichnis von 'Öffentliches Gestalten':\n\n"
    full_text = ""
    toc_error = None
    pdf_error = None

    if not os.path.exists(pdf_path):
        return None, None, f"Fehler: Die Handbuchdatei '{pdf_path}' wurde nicht gefunden.", None

    try:
        doc = fitz.open(pdf_path)

        # 1. Versuche, ToC direkt zu extrahieren
        toc = doc.get_toc()
        if toc:
            for level, title, page in toc:
                indent = "  " * (level - 1)
                toc_text += f"{indent}- {title} (Seite {page})\n"
        else:
            # 2. Fallback: Versuche, ToC aus Text zu extrahieren (erste Seiten)
            max_toc_pages = 10
            found_toc_lines = 0
            for page_num in range(min(max_toc_pages, doc.page_count)):
                page = doc.load_page(page_num)
                text = page.get_text("text")
                lines = text.split('\n')
                for line in lines:
                    # Heuristik für Inhaltsverzeichniszeilen
                    clean_line = line.strip()
                    if "..." in clean_line and any(char.isdigit() for char in clean_line):
                        toc_text += f"- {clean_line}\n"
                        found_toc_lines += 1
                    elif clean_line and clean_line[-1].isdigit() and len(clean_line) > 3:
                         # Einfache Prüfung auf Zeilenende mit Seitenzahl
                        toc_text += f"- {clean_line}\n"
                        found_toc_lines += 1

            if found_toc_lines < 3 : # Wenn kaum ToC-Zeilen gefunden wurden
                 toc_error = "Konnte kein detailliertes Inhaltsverzeichnis extrahieren. Analyse basiert auf Volltext."
                 toc_text = None # Kein brauchbares ToC gefunden

        # 3. Extrahiere den Volltext mit Seitenzahlen
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            page_text = page.get_text("text")
            # Füge Seitenzahl-Marker hinzu (etwas dezenter)
            full_text += f"\n\n[Seite {page_num + 1}]\n{page_text}"

        doc.close()

    except Exception as e:
        pdf_error = f"Fehler bei der PDF-Verarbeitung: {e}"
        return None, None, toc_error, pdf_error # Gibt Fehler zurück

    return full_text, toc_text, toc_error, pdf_error

def initialize_pdf_data(pdf_path):
    """Lädt die PDF für die Verwendung mit der Gemini API."""
    if 'pdf_initialized' not in st.session_state:
        with st.spinner(f"Lade '{os.path.basename(pdf_path)}'..."):
            try:
                # Konfiguriere den Gemini Client
                genai.configure(api_key=API_KEY)
                client = genai.GenerativeModel(MODEL_NAME)
                
                # Lade die PDF direkt als Bytes
                with open(pdf_path, 'rb') as file:
                    pdf_data = file.read()
                
                # Speichere die PDF-Daten im Session State
                st.session_state.pdf_data = pdf_data
                st.session_state.pdf_initialized = True
                
                return True
            except Exception as e:
                st.error(f"Fehler beim Laden der PDF: {e}")
                return False
    return True

def get_ai_suggestions(problem_description):
    """Ruft die Gemini API auf, um Übungsvorschläge zu erhalten."""
    if not API_KEY:
        st.error("Google API-Schlüssel nicht konfiguriert. Bitte .env-Datei prüfen.")
        return None

    try:
        # Konfiguriere den Gemini Client
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel(MODEL_NAME)

        # Erstelle den Prompt mit dem System-Kontext und der strukturierten Ausgabe
        prompt = f"""
Du bist ein Expertenassistent, der einem Creative Director bei der Betreuung von Universitätsprojekten hilft.
Die Projekte basieren auf den Methoden im Handbuch 'Öffentliches Gestalten'.
Deine Aufgabe ist es, relevante Übungen/Abschnitte aus dem Handbuch vorzuschlagen, um spezifische Teamprobleme zu lösen.

PROBLEMBESCHREIBUNG DES BENUTZERS:
"{problem_description}"

AUFGABE:
1. Analysiere die Kernprobleme in der Beschreibung des Benutzers.
2. Identifiziere die relevantesten Übungen, die diese Probleme direkt ansprechen:
   - Bei einfachen Problemen schlage nur die eine beste Übung vor.
   - Bei komplexeren Problemen schlage bis zu 3 Übungen vor, wenn wirklich mehrere Ansätze notwendig sind.

3. Für jeden Übungsvorschlag extrahiere:
   - Den exakten Titel der Übung.
   - Die exakten Seitenzahlen des gesamten Übungsabschnitts (von Anfang bis Ende).
   - Die exakte Seitenzahl, auf der der "Vorgehen"-Abschnitt beginnt.
   - Alle angegebenen Metadaten zur Übung wie Zeitrahmen, Niveau, benötigte Materialien und Rollen.

ANTWORTFORMAT:
Strukturiere deine Antwort folgendermaßen:

## 🔍 Problembeschreibung
[Kurze Zusammenfassung des Kernproblems in 1-2 Sätzen]

## 💡 Empfohlene Übung(en)
### 📋 [Titel der Übung 1]
- **Seiten:** [Seitenbereich z.B. 45-48]
- **Vorgehen beginnt auf:** Seite [Seitenzahl]
- **Zeitrahmen:** [Zeit aus dem Handbuch]
- **Niveau:** [Niveau aus dem Handbuch]
- **Materialien:** [Benötigte Materialien]
- **Rollen:** [Benötigte Rollen]

### 📋 [Titel der Übung 2] (falls nötig)
[Gleiche Struktur wie oben]

## ✅ Warum diese Übung(en) passen
[Erklärung, wie die Übung(en) das Problem adressieren]
"""
        # Erstelle die Anfrage mit PDF und Prompt
        with open(PDF_PATH, 'rb') as pdf_file:
            pdf_data = pdf_file.read()
            
        response = model.generate_content(
            contents=[
                {
                    "parts": [
                        {
                            "inline_data": {
                                "mime_type": "application/pdf",
                                "data": pdf_data
                            }
                        },
                        {
                            "text": prompt
                        }
                    ]
                }
            ]
        )

        return response.text

    except Exception as e:
        st.error(f"Fehler bei der Kommunikation mit der Gemini API: {e}")
        return None

# --- UI Styling & Rendering Funktionen ---

def apply_modern_styling():
    """Wendet das benutzerdefinierte CSS für den modernen Dark Mode an."""
    st.markdown(f"""
        <style>
            /* Globale Stile & Dark Mode Basis */
            html, body, [class*="st-"] {{
                background-color: {BG_DARK};
                color: {TEXT_COLOR_LIGHT};
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; /* Modernere Schriftart */
            }}

            /* Hauptcontainer */
            .main .block-container {{
                padding: 2rem 3rem 3rem 3rem; /* Mehr Padding */
                max-width: 1100px;
            }}

            /* Überschriften - nur Text zentriert */
            h1, h2, h3 {{
                text-align: center; /* NUR Überschriften zentrieren */
                color: {TEXT_COLOR_LIGHT};
                font-weight: 600; /* Etwas dicker */
            }}
            h1 {{
                color: {PRIMARY_COLOR}; /* Hauptüberschrift hervorheben */
                border-bottom: 1px solid {BORDER_COLOR};
                padding-bottom: 0.5rem;
                margin-bottom: 1.5rem;
            }}
            h2 {{
                color: {PRIMARY_COLOR};
                margin-top: 2.5rem;
                margin-bottom: 1rem;
            }}
            h3 {{
                color: {TEXT_COLOR_LIGHT};
                font-weight: 500;
                margin-bottom: 0.8rem;
            }}

            /* Textarea */
            .stTextArea textarea {{
                background-color: {CARD_BG_DARK} !important;
                color: {TEXT_COLOR_LIGHT} !important;
                border: 1px solid {BORDER_COLOR} !important;
                border-radius: 8px;
                padding: 12px;
                font-size: 1.05em;
                min-height: 150px; /* Mindesthöhe */
                box-shadow: 0 2px 4px rgba(0,0,0,0.2);
            }}
            .stTextArea label {{
                color: {TEXT_COLOR_MEDIUM} !important; /* Label etwas dezenter */
                font-weight: 500;
                margin-bottom: 0.5rem; /* Mehr Abstand zum Feld */
                text-align: center; /* Label zentrieren */
            }}

            /* Button - Modern & Zentriert */
            .stButton > button {{
                border: none;
                padding: 0.8rem 2.5rem; /* Angepasstes Padding */
                border-radius: 25px; /* Stärker abgerundet */
                background: linear-gradient(45deg, {PRIMARY_COLOR}, {SECONDARY_COLOR}); /* Farbverlauf */
                color: white;
                font-weight: 600;
                font-size: 1.1em;
                letter-spacing: 0.5px;
                cursor: pointer;
                transition: all 0.3s ease;
                display: block; /* Wichtig für margin auto */
                margin: 1.5rem auto 0 auto; /* Oben/Unten Abstand, Links/Rechts zentriert */
                box-shadow: 0 4px 10px rgba(0, 0, 0, 0.3);
            }}
            .stButton > button:hover {{
                box-shadow: 0 6px 15px rgba(0, 0, 0, 0.4);
                transform: translateY(-3px); /* Leichter Schwebeeffekt */
                filter: brightness(1.1); /* Heller beim Hover */
            }}
            .stButton > button:active {{
                transform: translateY(-1px);
                box-shadow: 0 2px 5px rgba(0, 0, 0, 0.3);
            }}

            /* Sidebar */
            section[data-testid="stSidebar"] {{
                background-color: {SIDEBAR_BG};
                border-right: 1px solid {BORDER_COLOR};
                padding: 1.5rem;
            }}
            section[data-testid="stSidebar"] h2 {{
                color: {TEXT_COLOR_LIGHT}; /* Sidebar-Titel in Hell */
                margin-top: 0;
                border-bottom: 1px solid {BORDER_COLOR};
                padding-bottom: 0.5rem;
                text-align: center; /* Sidebar-Überschriften zentrieren */
            }}
            section[data-testid="stSidebar"] .stMarkdown {{
                color: {TEXT_COLOR_MEDIUM}; /* Dezenterer Text in Sidebar */
            }}
            section[data-testid="stSidebar"] strong {{
                color: {TEXT_COLOR_LIGHT}; /* Hervorgehobener Text heller */
            }}

            /* Ergebnis-Karte */
            .result-card {{
                background-color: {CARD_BG_DARK};
                border-radius: 10px;
                border-left: 5px solid {PRIMARY_COLOR}; /* Akzentlinie links */
                padding: 1.5rem 2rem;
                margin: 1.5rem 0;
                box-shadow: 0 3px 8px rgba(0,0,0,0.25);
                color: {TEXT_COLOR_LIGHT};
            }}
            .result-card h2 {{ /* Überschriften in der Ergebnis-Karte */
                color: {PRIMARY_COLOR};
                margin-top: 0; /* Kein extra Abstand oben */
                font-size: 1.4em;
                text-align: center; /* Überschriften zentrieren */
            }}
            .result-card h3 {{
                color: {TEXT_COLOR_LIGHT};
                font-size: 1.2em;
                margin-top: 1rem;
                margin-bottom: 0.5rem;
                border-bottom: 1px solid {BORDER_COLOR};
                padding-bottom: 0.3rem;
                text-align: center; /* Überschriften zentrieren */
            }}
            .result-card strong {{
                color: {TEXT_COLOR_LIGHT}; /* Fettgedrucktes hervorheben */
            }}
            .result-card hr {{
                border-top: 1px solid {BORDER_COLOR};
                margin: 1.5rem 0;
            }}

            /* Intro-Karte */
            .intro-card {{
                background-color: {CARD_BG_DARK};
                border-radius: 10px;
                padding: 1.5rem 2rem;
                margin-bottom: 2rem; /* Mehr Abstand nach unten */
                box-shadow: 0 3px 8px rgba(0,0,0,0.25);
                color: {TEXT_COLOR_MEDIUM}; /* Etwas dezenterer Text */
                text-align: center; /* Intro-Text zentrieren */
                font-size: 1.05em;
            }}

            /* Footer */
            .footer {{
                text-align: center; /* Footer zentrieren */
                color: {TEXT_COLOR_MEDIUM};
                font-size: 0.9em;
                padding: 2rem 1rem 1rem 1rem;
                border-top: 1px solid {BORDER_COLOR};
                margin-top: 4rem; /* Mehr Abstand nach oben */
            }}
        </style>
    """, unsafe_allow_html=True)

def render_app_header():
    """Rendert den modernen App-Header mittig."""
    # Zentriertes Logo und Titel
    st.markdown(f"""
    <div class="logo-container">
        <span style='font-size: 3.5em; display: inline-block;'>{PAGE_CONFIG['page_icon']}</span>
    </div>
    """, unsafe_allow_html=True)
    st.title("Creative Director AI Hilfstool")
    # Zusätzliche Linie wird durch globales h1-Styling erzeugt

def render_introduction():
    """Zeigt eine kurze Einführung in einer gestylten Karte."""
    st.markdown(f"""
    <div class="intro-card">
        Geben Sie hier die Herausforderungen oder Problemstellungen Ihres Scrum-Teams ein. <br>
        Die KI analysiert Ihre Beschreibung und schlägt passende Methoden oder Übungen aus dem Handbuch 'Öffentliches Gestalten' vor.
    </div>
    """, unsafe_allow_html=True)

def render_sidebar_info(pdf_path, model_name):
    """Rendert die Informationen in der Sidebar."""
    with st.sidebar:
        st.header("Tool-Informationen")
        st.markdown(f"""
        <div style="padding: 15px; border-radius: 8px; background-color: {CARD_BG_DARK}; text-align: center;">
            <ul style="list-style-type: none; padding-left: 0; margin-bottom: 1rem;">
                <li style="margin-bottom: 0.8rem;"><strong>KI-Modell:</strong><br> <span style="color:{TEXT_COLOR_MEDIUM};">{model_name}</span></li>
                <li style="margin-bottom: 0.8rem;"><strong>Datenbasis:</strong><br> <span style="color:{TEXT_COLOR_MEDIUM};">{os.path.basename(pdf_path)}</span></li>
            </ul>
            <p style="color:{TEXT_COLOR_MEDIUM}; font-size: 0.95em;">
            Dieses Werkzeug unterstützt Creative Directors bei der Auswahl relevanter Übungen für Scrum-Teams basierend auf dem Handbuch 'Öffentliches Gestalten'.
            </p>
            <p style="font-size: 0.85em; opacity: 0.7; color:{TEXT_COLOR_MEDIUM};">
            <i>Tipp: Je spezifischer die Problembeschreibung, desto treffender die Vorschläge.</i>
            </p>
        </div>
        """, unsafe_allow_html=True)

        # Zitationsinfo in separater Box
        st.markdown(f"""
        <div style="margin-top: 1rem; padding: 15px; border-radius: 8px; background-color: {CARD_BG_DARK};">
            <p style="font-size: 0.9em; color:{TEXT_COLOR_MEDIUM}; margin-bottom: 0.5rem;"><strong>Zitation der Datenbasis:</strong></p>
            <p style="font-size: 0.85em; color:{TEXT_COLOR_MEDIUM}; line-height: 1.4;">
            Paulick-Thiel, C. & Arlt, H. (2020): Öffentliches Gestalten – Handbuch für innovatives Arbeiten in der Verwaltung. 2. Aufl. Berlin: Technologiestiftung Berlin. ISBN 978-3-00-065930-0
            </p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---", unsafe_allow_html=True)
        st.caption(f"© {2024} - AI Hilfstool") # Dynamisches Jahr

def render_footer():
    """Rendert den Footer am Ende der Seite."""
    st.markdown("""
    <div class="footer">
         Entwickelt mit Streamlit & Google Gemini | Refaktorierung & UI-Verbesserung
    </div>
    """, unsafe_allow_html=True)

# --- Hauptanwendung ---
def main():
    """Führt die Streamlit-Anwendung aus."""
    st.set_page_config(**PAGE_CONFIG)
    apply_modern_styling()
    render_app_header()
    render_sidebar_info(PDF_PATH, MODEL_NAME)

    # PDF-Daten initialisieren und prüfen
    if not initialize_pdf_data(PDF_PATH):
        st.error("PDF konnte nicht geladen werden. Die Anwendung kann nicht fortfahren.")
        render_footer()
        return # Abbruch, wenn PDF nicht geladen

    render_introduction()

    # Eingabeformular
    st.subheader("Problembeschreibung eingeben")
    with st.form(key="problem_input_form", clear_on_submit=False):
        problem_description = st.text_area(
            label="Beschreiben Sie die aktuellen Herausforderungen oder Blocker Ihres Teams:",
            height=180, # Etwas höher
            placeholder="Beispiel: Unser Team hat Schwierigkeiten, eine gemeinsame Vision für das Projekt zu entwickeln und die nächsten Schritte zu priorisieren...",
            label_visibility="collapsed" # Label wird durch subheader ersetzt
        )
        submit_button = st.form_submit_button(label="Passende Übungen finden")

    # Verarbeitung und Ausgabe
    if submit_button:
        if not problem_description or len(problem_description) < 20:
            st.warning("Bitte geben Sie eine aussagekräftige Problembeschreibung ein (mind. 20 Zeichen).")
        elif not API_KEY:
            # Fehler wird bereits in get_ai_suggestions behandelt, hier zur Sicherheit
            st.error("Google API-Schlüssel fehlt. Bitte konfigurieren.")
        else:
            with st.spinner("KI analysiert das Problem und sucht nach Übungen..."):
                suggestions = get_ai_suggestions(problem_description)

            st.markdown("---") # Trennlinie vor den Ergebnissen
            st.subheader("Ergebnis der Analyse")
            if suggestions:
                # Ergebnisse in der gestylten Karte anzeigen
                st.markdown(f'<div class="result-card">{suggestions}</div>', unsafe_allow_html=True)
            else:
                # Falls die API-Funktion None zurückgibt (wegen API-Fehler etc.)
                st.error("Es konnten keine Vorschläge generiert werden. Überprüfen Sie die Fehlermeldungen.")

    # Footer immer anzeigen
    render_footer()

# --- App Start ---
if __name__ == "__main__":
    main()