import csv
import os
import logging
from paperreader import PaperReader
from notionmanager import NotionManager
from portfoliomaker import PortfolioMaker
from openai import OpenAI

# Konfiguration des Logging-Moduls
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')

def read_settings(path='settings.csv'):
    """
    Liest die Einstellungen aus einer CSV-Datei.
    """
    try:
        with open(path, mode='r', encoding='utf-8') as csv_file:
            csv_reader = csv.DictReader(csv_file)
            settings = {row["Setting"]: row["Value"] for row in csv_reader}
        return settings
    except FileNotFoundError:
        logging.error(f"Die Datei {path} wurde nicht gefunden.")
        return {}
    except Exception as e:
        logging.exception(f"Fehler beim Lesen der Einstellungen: {e}")
        return {}

def str_to_bool(value):
    """
    Konvertiert einen String in einen booleschen Wert.
    """
    return value.lower() in ('true', '1', 'yes')

if __name__ == '__main__':
    # Setze das Arbeitsverzeichnis auf das Skriptverzeichnis
    script_directory = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_directory)

    # Lese die Einstellungen
    settings = read_settings('settings.csv')

    # Initialisiere den OpenAI Client
    OpenAIclient = OpenAI(api_key=settings.get('API_Key'))

    # Initialisiere die PaperReader-Klasse
    assi = PaperReader(settings, OpenAIclient)

    # Variablen festlegen
    destdir = settings.get("Destination_Directory", "./output")
    create_summary = str_to_bool(settings.get("create_summary", "false"))
    create_audio = str_to_bool(settings.get("create_audio", "false"))
    include_notion = str_to_bool(settings.get("include_notion", "false"))
    build_portfolio = str_to_bool(settings.get("build_portfolio", "false"))
    create_newsletter = str_to_bool(settings.get("create_newsletter", "false"))
    sendmail = str_to_bool(settings.get("send_email", "false"))
    unlink = str_to_bool(settings.get("remove_pdfs_after_process", "false"))

    # Erstelle das Zielverzeichnis, falls es nicht existiert
    if not os.path.exists(destdir):
        os.makedirs(destdir)

    # Initialisiere den NotionManager und überprüfe die erforderlichen Spalten
    if include_notion:
        noti = NotionManager(settings, OpenAIclient)
        noti.check_and_add_missing_properties()

    # Initialisiere den PortfolioMaker
    if build_portfolio:
        pdf = PortfolioMaker(settings, assi.files_to_read, assi.all_summaries)

    # Durchlaufe alle PDF-Dateien im Ordner
    for file_path in assi.files_to_read:
        # Dateiname extrahieren
        file = os.path.basename(file_path)
        root_name = os.path.splitext(file)[0]

        # PDF-Datei lesen
        logging.info(f'Lese PDF-Datei: {file}')
        assi.read_pdf(path=file_path)

        # Zusammenfassung erstellen
        if create_summary:
            logging.info('Erstelle Zusammenfassung')
            assi.create_summary()

            # Zusammenfassung lokal speichern
            logging.info('Speichere Zusammenfassung lokal')
            filename = os.path.join(destdir, root_name + ".txt")
            assi.save_summary(filename=filename)

            # Paper-Metriken übergeben, vor allem wg. der DOI
            if build_portfolio:
                pdf.metrices_list.append(assi.paper_metrices)

        # Audio aus Zusammenfassung erstellen
        if create_summary and create_audio:
            logging.info('Erstelle Audiodatei')
            filename = os.path.join(destdir, root_name)
            assi.create_audio_from_summary(filename=filename)

        # Zusammenfassung zur Notion-Seite hinzufügen
        if include_notion:
            logging.info('Füge Zusammenfassung zu Notion hinzu')
            noti.paper_metrices = assi.paper_metrices
            noti.add_paper_to_database()

        # Datei aus dem Ordner entfernen
        if unlink:
            logging.info('Entferne Datei')
            os.remove(file_path)

    # Nachbearbeitung: Newsletter-Text basierend auf allen erstellten Zusammenfassungen erstellen
    if create_newsletter and assi.all_summaries:
        logging.info('Erstelle Newsletter')
        newsletter_text = assi.create_newsletter_text()
        assi.settings['Email_Body'] = newsletter_text

    # Nachbearbeitung: PDF-Portfolio erstellen und lokal speichern
    if build_portfolio and assi.all_summaries:
        logging.info('Erstelle PDF-Portfolio')
        pdf.build_pdf_portfolio()

    # Nachbearbeitung: E-Mail senden
    if sendmail:
        logging.info('Sende E-Mail')
        assi.send_email(include_pdf_portfolio=build_portfolio)
