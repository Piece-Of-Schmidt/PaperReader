import os
import glob
import re
import random
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from PyPDF2 import PdfReader
from PyPDF2.errors import PdfReadError

# Konfiguration des Logging-Moduls
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')


class PaperReader:
    def __init__(self, settings, OpenAIclient=None):
        self.settings = settings
        self.client = OpenAIclient
        self.files_to_read = glob.glob(os.path.join(self.settings["File_Directory"], '*.pdf'))
        self.paper = None
        self.all_summaries = []
        self.audio = None
        self.paper_metrices = None

    def read_pdf(self, path, remove_references=True):
        """
        Liest und verarbeitet eine PDF-Datei vom angegebenen Pfad.
        """
        try:
            reader = PdfReader(path)
            pages = [reader.pages[idx].extract_text() for idx in range(len(reader.pages))]
            pages = ''.join(pages)
            pages = re.sub(self.settings["Exclude_Pattern"], '', pages)

            if remove_references:
                pages = re.sub(r'(\n)?References(\n)?.*', '', pages, flags=re.DOTALL)

            self.paper = pages

            # Extrahiere Paper-Metriken
            filename = os.path.splitext(os.path.basename(path))[0]
            self.get_paper_metrices(paper_title=filename)

        except FileNotFoundError as e:
            logging.error(f"PDF-Datei nicht gefunden {path}: {e}")
            self.paper = None
        except PdfReadError as e:
            logging.error(f"Fehler beim Lesen der PDF-Datei {path}: {e}")
            self.paper = None
        except Exception as e:
            logging.exception(f"Unerwarteter Fehler beim Lesen der PDF-Datei {path}: {e}")
            self.paper = None

    def get_paper_metrices(self, paper_title=None, paper=None, project_name=None, summary=None):
        """
        Extrahiert Informationen über Autor, Veröffentlichungsjahr und Titel aus dem Dokumentnamen.
        Wenn diese Informationen nicht im Dokumentnamen enthalten sind, versucht das LLM, diese zu schätzen.
        Fügt den Projektnamen aus settings.csv zu den Metriken hinzu.
        Extrahiert die DOI des Papers und generiert einen Link, über den das Paper zu finden ist.
        """
        # Paper einalden
        paper = paper if paper is not None else self.paper
        
        # Lese Projektname aus den Einstellungen
        project_name = project_name if project_name is not None else self.settings.get('Notion_Project_Name', '')

        # Regex-Muster zur Extraktion von Autor, Jahr und Titel
        pattern = r'^(?P<author>.+?)\s+\((?P<year>\d{4})\)\s+(?P<title>.+)$'
        match = re.match(pattern, paper_title)

        metrices = {}
        # Suche nach Regex im Dokumentnamen
        if match:
            metrices = match.groupdict()
            metrices['year'] = int(metrices['year'])  # Jahr als Integer
        else:
            instruction = 'Please extract from the following text the information about the author(s), the publishing year and the title. Provide the information in the following format: author (year) title'
            prompt = paper[:1000]

            try:
                response = self.client.chat.completions.create(
                    model=self.settings.get('GPT_Newsletter_Model'),
                    messages=[
                        {"role": "system", "content": instruction},
                        {"role": "user", "content": prompt}
                    ]
                )
                content = response.choices[0].message.content.strip()
                match = re.match(pattern, content)
                if match:
                    metrices = match.groupdict()
                    metrices['year'] = int(metrices['year'])  # Jahr als Integer
                else:
                    logging.warning("Das LLM konnte die Metadaten nicht korrekt extrahieren.")
                    metrices = {'author': 'Unknown', 'year': 0, 'title': 'Unknown'}
            except Exception as e:
                logging.error(f"Fehler beim Extrahieren der Paper-Metriken: {e}")
                metrices = {'author': 'Unknown', 'year': 0, 'title': 'Unknown'}

        # Regex-Muster zur Extraktion der DOI
        doi_pattern = r'\b(10\.\d{4,9}/.*)\b'
        doi_match = re.search(doi_pattern, paper[:10000])

        # Füge Projektnamen aus settings.csv hinzu
        metrices['project_name'] = project_name

        # Füge Paper-Link hinzu
        metrices['doi_link'] = f"https://doi.org/{doi_match.group(1)}" if doi_match else ""
    
        # Extrahiere Abstract
        metrices['abstract'] = self.extract_abstract()

        # Füge Platzhalter für Zusammenfassung und Tags hinzu
        metrices['summary'] = summary

        self.paper_metrices = metrices

    def extract_abstract(self, paper=None):
        """
        Extrahiert den Abstract aus dem zu verarbeitenden Paper basierend auf einer einfachen Regex-Suche.
        """
        paper = paper if paper is not None else self.paper

        # Suche nach 'Abstract' im Text
        match = re.search(r'Abstract(.*?)(\n\n|\Z)', paper, flags=re.S | re.I)

        if match:
            abstract = match.group(1).strip()[:1995] + '...'
            abstract = re.sub(r'(\nkey( )?words|\nintroduction)(.*)', '', abstract, flags=re.S | re.I)
            abstract = re.sub(r'^abstract', '', abstract, flags=re.I).strip()
        else:
            abstract = 'No abstract found.'

        return abstract

    def create_summary(self):
        """
        Erstellt eine Zusammenfassung des bereitgestellten Textes.
        """
        if not self.paper:
            logging.warning("Keine PDF-Datei verfügbar.")
            return

        lang = self.settings.get('Inference_Language', 'English')
        suffix = f" Please answer in {lang}." if lang != "English" else ""

        instruction = self.settings.get("LLM_Instruction", "")
        prompt = f"{self.settings.get('LLM_Prompt', '')}{suffix} \n\n {self.paper}"

        try:
            response = self.client.chat.completions.create(
                model=self.settings.get("GPT_Summarizer_Model"),
                messages=[
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": prompt}
                ]
            )
            summary = response.choices[0].message.content.strip()
            
            # DOI-Link hinzufügen
            doi_link = self.paper_metrices.get('doi_link')
            if doi_link:
                summary += f"\n\nURL to Paper: {doi_link}"
            
            self.paper_metrices['summary'] = summary
            self.all_summaries.append(summary)
        except Exception as e:
            logging.error(f"Fehler beim Erstellen der Zusammenfassung: {e}")

    def save_summary(self, filename):
        """
        Speichert die erstellte Zusammenfassung lokal.
        """
        summary = self.paper_metrices.get('summary')
        if summary:
            try:
                with open(filename, 'w', encoding='utf-8') as file:
                    file.write(summary)
            except Exception as e:
                logging.error(f"Fehler beim Speichern der Zusammenfassung: {e}")
        else:
            logging.warning("Keine Zusammenfassung zum Speichern vorhanden.")

    def create_audio_from_summary(self, filename):
        """
        Erstellt eine Audiodatei basierend auf der erstellten Zusammenfassung und speichert sie lokal.
        """
        summary = self.paper_metrices.get('summary')
        if not summary:
            logging.warning("Keine Zusammenfassung verfügbar, um Audio zu erstellen.")
            return

        try:
            voice_options = ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer']
            voice_setting = self.settings.get('TTS_Voice', 'alloy')
            voice = random.choice(voice_options) if voice_setting == 'shuffle' else voice_setting

            self.audio = self.client.audio.speech.create(
                model=self.settings.get('TTS_Model'),
                voice=voice,
                speed=float(self.settings.get('TTS_Speed', 1.0)),
                input=summary,
            )
            self.audio.stream_to_file(filename + self.settings.get('Audio_Format', '.mp3'))
        except Exception as e:
            logging.error(f"Fehler beim Erstellen des Audios: {e}")

    def create_newsletter_text(self, all_summaries=None):
        """
        Erstellt einen Newsletter-Text basierend auf den in PaperReader.all_summaries gespeicherten Zusammenfassungen.
        Wenn eine Liste von Texten bereitgestellt wird, werden diese verwendet.
        """
        # Lade alle Zusammenfassungen
        all_summaries = all_summaries if all_summaries is not None else self.all_summaries

        if not all_summaries:
            logging.warning("Keine Zusammenfassungen verfügbar, um einen Newsletter zu erstellen.")
            return ""

        # Lasse das LLM den Newsletter-Text erstellen
        lang = self.settings.get('Inference_Language', 'English')
        suffix = f" Please answer in {lang}." if lang != "English" else ""

        instruction = self.settings.get('Newsletter_Prompt', '')
        prompt = ' \n\nNext text:\n\n'.join(all_summaries) + suffix

        try:
            response = self.client.chat.completions.create(
                model=self.settings.get('GPT_Newsletter_Model'),
                messages=[
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": prompt}
                ]
            )
            newsletter_text = response.choices[0].message.content.strip()
            return newsletter_text
        except Exception as e:
            logging.error(f"Fehler beim Erstellen des Newsletters: {e}")
            return ""

    def send_email(self, include_pdf_portfolio=False):
        """
        Sendet eine E-Mail mit den angegebenen Einstellungen und Anhängen.
        """
        if self.settings.get('include_notion', 'false').lower() == 'true':
            self.settings['Email_Body'] += '\n\nLink to Notion Database:\n' + f"https://www.notion.so/{self.settings['Notion_Database_Id']}"

        msg = MIMEMultipart()
        msg['From'] = self.settings.get('Email_From')
        msg['To'] = self.settings.get('Email_To')
        msg['Subject'] = self.settings.get('Email_Subject')
        msg.attach(MIMEText(self.settings.get('Email_Body', ''), 'plain', 'utf-8'))

        # Anhänge hinzufügen
        relevant_files = glob.glob(os.path.join(self.settings['Destination_Directory'], f"*{self.settings.get('Audio_Format', '.mp3')}"))
        if include_pdf_portfolio:
            relevant_files.extend(glob.glob(os.path.join(self.settings['Destination_Directory'], '*.pdf')))

        for file_path in relevant_files:
            filename = os.path.basename(file_path)
            try:
                with open(file_path, 'rb') as attachment:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename= {filename}')
                msg.attach(part)
            except Exception as e:
                logging.error(f"Fehler beim Anhängen der Datei {filename}: {e}")

        # E-Mail senden
        try:
            with smtplib.SMTP(self.settings['SMTP_Host'], int(self.settings['SMTP_Port'])) as server:
                server.starttls()
                server.login(self.settings['SMTP_User'], self.settings['SMTP_Password'])
                server.send_message(msg)
                logging.info("E-Mail erfolgreich gesendet.")
        except Exception as e:
            logging.error(f"Fehler beim Senden der E-Mail: {e}")
