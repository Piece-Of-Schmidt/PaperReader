import csv
import re
import os
import glob
import smtplib
import random
import requests
from datetime import date
from PyPDF2 import PdfReader
from fpdf import FPDF, XPos, YPos
from datetime import date
from openai import OpenAI
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

class PDF(FPDF):
    def header(self):
        # Einstellungen für die Kopfzeile
        self.set_font('helvetica', 'B', 12)
        self.cell(0, 10, 'Portfolio', new_x=XPos.LEFT, new_y=YPos.NEXT, align='C')

    def footer(self):
        # Einstellungen für die Fußzeile
        self.set_y(-15)
        self.set_font('helvetica', 'I', 8)
        self.cell(0, 10, f'Seite {self.page_no()}', new_x=XPos.LEFT, new_y=YPos.TOP, align='C')

    def chapter_title(self, title):
        # Einstellungen für Kapiteltitel
        self.set_font('helvetica', 'B', 14)
        self.cell(0, 10, title, new_x=XPos.LEFT, new_y=YPos.NEXT, align='L')
        self.ln(10)

    def chapter_body(self, body):
        # Einstellungen für den Haupttext
        self.set_font('helvetica', '', 12)
        self.multi_cell(0, 10, body)
        self.ln()

class ResearchAssistant:

    def __init__(self, settings_path='settings.csv', portfolio_maker=None):
        self.settings = self.read_settings(path=settings_path)
        self.client = OpenAI(api_key = self.settings["API_Key"])
        self.files_to_read = glob.glob(os.path.join(self.settings["File_Directory"], '*.pdf'))
        self.paper = None
        self.summary = None
        self.all_summaries = []
        self.audio = None
        self.pdf_maker = portfolio_maker
        self.notion_header = self.notion_build_header()
        self.notion_page_id = None
        self.paper_metrices = None

    def read_settings(self, path='settings.csv'):
        """
        Reads the function settings from a CSV file.
        """
        try:
            with open(path, mode='r', encoding = 'utf-8') as csv_file:
                csv_reader = csv.DictReader(csv_file)
                settings = {row["Setting"]: row["Value"] for row in csv_reader}
            return(settings)
        except FileNotFoundError:
            print(f"Did not find file {path}.")
        except Exception as e:
            print(f"Error: {e}")

    def read_pdf(self, path, remove_references=True):
        """
        Reads and processes a PDF file from the given path.
        """
        try:
            reader = PdfReader(path)
            pages = [reader.pages[idx].extract_text() for idx in range(len(reader.pages))]
            pages = ''.join(pages)
            pages = re.sub(self.settings["Exclude_Pattern"], '', pages)

            if remove_references:
                pages = re.sub('(\n)?References(\n)?.*', '', pages, flags=re.DOTALL)

            self.paper = pages
        except Exception as e:
            print(f"Error reading PDF {path}: {e}")
            self.paper = None

    def get_paper_metrices(self, paper_title=None):
        """
        Extracts information about author, publication date and paper title from document name.
        If the document name does not contain these information (according on regex matching),
        ChatGPT (the concrete model being specified in the settings['GPT_Newsletter_Model']) tries to guess these information.
        """
        # regex
        pattern = r'^(?P<author>.+?)\s+\((?P<year>\d{4})\)\s+(?P<title>.+)$'
        match = re.match(pattern, paper_title)
        
        if match:
            metrices = match.groupdict()
            metrices['year'] = int(metrices['year'])  # year to integer
            
        else:
            instruction = 'Please extract from the following text the information about the author(s), the publishing year and the title. Provide the information in the following format: author (year) title'
            prompt = self.paper[:1000] 
        
            try:
                metrices = self.client.chat.completions.create(
                    model = self.settings['GPT_Newsletter_Model'],
                    messages=[
                        {"role": "system", "content": instruction},
                        {"role": "user", "content": prompt}
                    ]).choices[0].message.content
                
                metrices = re.match(pattern, metrices)
                metrices = metrices.groupdict()

                metrices['year'] = int(metrices['year'])  # year to integer

            except Exception as e:
                print(f"Error creating newsletter: {e}")
        
        self.paper_metrices = metrices
    

    def create_summary(self):
        """
        Creates a summary of the provided text.
        """
        if not self.paper:
            print("No PDF file available.")
            return
        
        lang = self.settings['Inference_Language']
        suffix = f" Please answer in {lang}." if lang != "English" else ""
        
        instruction = self.settings["LLM_Instruction"]
        prompt = f"{self.settings['LLM_Prompt']}{suffix} \n\n {self.paper}"
        
        try:
            summary = self.client.chat.completions.create(
                model = self.settings["GPT_Summarizer_Model"],
                messages=[
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": prompt}
                ]
            ).choices[0].message.content
            self.summary = summary
            self.all_summaries.append(summary)
        except Exception as e:
            print(f"Error creating summary: {e}")

    def save_summary(self, filename):
        """
        Saves the created summary locally.
        """
        if self.summary:
            try:
                with open(filename, 'w') as file:
                    file.write(self.summary)
            except Exception as e:
                print(f"Error saving summary: {e}")

    # create audio file
    def create_audio_from_summary(self, filename):
        """
        Creates an audio file based on the created summary and saves it locally.
        """
        if not self.summary:
            print("No summary available to create audio.")
            return

        try:
            voice = random.choice(['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer']) if self.settings['TTS_Voice'] == 'shuffle' else self.settings['TTS_Voice']
            self.audio = self.client.audio.speech.create(
                model = self.settings['TTS_Model'],
                voice = voice,
                speed = float(self.settings['TTS_Speed']),
                input = self.summary,
            )
            self.audio.stream_to_file(filename + self.settings['Audio_Format'])
        except Exception as e:
            print(f"Error creating audio: {e}")

    # if newsletter: replace e mail body text with automatically generated newletter text
    def replace_mail_body_with_newsletter_text(self):
        """
        Creates a newsletter text based on the summaries.
        """
        lang = self.settings['Inference_Language']
        suffix = f" Please answer in {lang}." if lang != "English" else ""
        
        instruction = self.settings['Newsletter_Prompt']
        prompt = ' \n\nNext text:\n\n'.join(self.all_summaries) + suffix
        
        try:
            newsletter_text = self.client.chat.completions.create(
                model = self.settings['GPT_Newsletter_Model'],
                messages=[
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": prompt}
                ]).choices[0].message.content
            self.settings['Email_Body'] = newsletter_text
        except Exception as e:
            print(f"Error creating newsletter: {e}")

    # method for sending email with attachments
    def send_email(self, include_pdf_portfolio=False):
        """
        Sends an email with the specified settings and attachments.
        """
        if self.settings['include_notion'].lower() == 'true':
            self.settings['Email_Body'] = self.settings['Email_Body'] + '\n\nLink to Notion Database:\n' + f"https://www.notion.so/{assi.settings['Notion_Database_Id']}"
        try:
            msg = MIMEMultipart()
            msg['From'] = self.settings['Email_From']
            msg['To'] = self.settings['Email_To']
            msg['Subject'] = self.settings['Email_Subject']
            msg.attach(MIMEText(self.settings['Email_Body'], 'plain', 'utf-8'))

            # Attach files
            relevant_files = glob.glob(os.path.join(self.settings['Destination_Directory'], f"*{self.settings['Audio_Format']}"))
            if include_pdf_portfolio:
                relevant_files.append(*glob.glob(os.path.join(self.settings['Destination_Directory'], '*.pdf')))
            for file_path in relevant_files:
                filename = os.path.basename(file_path)
                with open(file_path, 'rb') as attachment:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename= {filename}')
                msg.attach(part)

            # Setup and send the email
            server = smtplib.SMTP(self.settings['SMTP_Host'], int(self.settings['SMTP_Port']))
            server.starttls()
            try:
                server.login(self.settings['SMTP_User'], self.settings['SMTP_Password'])
                server.send_message(msg)
            finally:
                server.quit()
        except Exception as e:
            print(f"Error sending email: {e}")
    

    # ---- NOTION STUFF ----
            
    # build header for notion requests
    def notion_build_header(self):
        return{
            "Authorization": "Bearer " + self.settings['Notion_Token'],
            "Content-Type": "application/json",
            "Notion-Version": self.settings['Notion_Version']
        }    

    def notion_create_tags(self, summary=None, tags=""):
        """
        Assigns 1-3 tags to the created article summary based on the tags provided in settings.csv
        """
        if len(tags) > 0:

            summary = summary if summary is not None else self.summary
            instruction = f'Read the following text and assign 1-3 of the following labels to it. Please only provide labels that truely describe the text. If you find no label matches the text, return "none". Return the labels as a comma-seperated list.\nTags: {tags}'
            
            try:
                tags = self.client.chat.completions.create(
                    model = self.settings['GPT_Newsletter_Model'],
                    messages=[
                        {"role": "system", "content": instruction},
                        {"role": "user", "content": summary}
                    ]).choices[0].message.content
                
            except Exception as e:
                print(f"Error creating tags: {e}")
                tags = ""

        return tags
    
    # edit page in notion database
    def notion_parse_text_content(self, text_content, header_content=None):
        """
        transforms summary to correct format
        """

        blocks = []
        
        # build headline
        if header_content:
            header = {'object': 'block', 'type': 'heading_3', 'heading_3': {'rich_text': [{'type': 'text', 'text': {'content': header_content}, 'annotations': {'bold': True}}]}}
            blocks.append(header)
        
        # build text content as paragraph blocks
        text_chunks = re.findall(r".{1,2000}(?=\s|$|\n)", text_content) # because of character limit per text block
        for chunk in text_chunks:
            paragraph_block = {'object': 'block', 'type': 'paragraph', 'paragraph': {'rich_text': [{'type': 'text', 'text': {'content': chunk.strip()}}]}}
            blocks.append(paragraph_block)
        
        # paste headline block and text block
        blocks.append({'object': 'block', 'type': 'paragraph', 'paragraph': {'rich_text': [{'type': 'text', 'text': {'content': "\n"}}]}})
        
        return blocks
    

    def notion_create_new_page(self, author=None, year=None, title=None, summary=None):
        """
        creates a new entry to a given notion database. The database ID is provided by settings.csv.
        The database is expected to have columns "Author", "Year", "Title", "Added" und "Tags".
        To work properly, make sure the properties of your Notion Database are correctly defined:
            Autor: Title (Aa)
            Year: Number (#)
            Title: Text (<lines symbol>)
            Added: Date (<calender symbol>)
            Tags: Text (<lines symbol>)
        """
        
        create_url = 'https://api.notion.com/v1/pages'

        author = author if author is not None else self.paper_metrices['author']
        year = year if year is not None else self.paper_metrices['year']
        title = title if title is not None else self.paper_metrices['title']
        added = date.today().isoformat()
        summary = summary if summary is not None else self.summary
        tags = tags if tags is not None else self.settings['Notion_Document_Tags']
        
        properties = {
            "Author": {"title": [{"text": {"content": author}}]},
            "Year": {"number": year},
            "Title": {"rich_text": [{"text": {"content": title}}]},
            "Added": {"date": {"start": added}},
            "Tags": {"rich_text": [{"text": {"content": self.notion_create_tags(summary, tags)}}]} 
            }

        children = self.notion_parse_text_content(summary, header_content=title)

        payload = {"parent": {"database_id": self.settings['Notion_Database_Id']}, "properties": properties, "children": children}
        response = requests.post(create_url, headers=self.notion_header, json=payload)
        if response.status_code == 200:
            self.notion_page_id = response.json()['id']
            print("Neue Seite erfolgreich in Notion erstellt.")
        else:
            print("Fehler beim Erstellen der neuen Seite in Notion:", response.text)

    
    # ---- END: NOTION STUFF ----

    # build pdf portfolio
    def build_pdf_portfolio(self):
        # Portfolio-Initialisierung
        pdf = self.pdf_maker
        pdf.add_page()
        
        # Seitenränder setzen (oben, unten, links, rechts)
        pdf.set_margins(10, 10, 10)
        
        filenames = [os.path.splitext(os.path.basename(file))[0] for file in self.files_to_read]
        for title, body in zip(filenames, self.all_summaries):
            pdf.chapter_title(title)
            pdf.chapter_body(body.encode('latin-1', 'replace').decode('latin-1'))
        
        # PDF lokal speichern
        pdf.output(os.path.join(self.settings['Destination_Directory'], 'Portfolio.pdf'))

    # complete loop
    def read_and_summarize_pdf(self, remove_after_process=True):

        # dim vars
        destdir = self.settings["Destination_Directory"]
        create_audio = self.settings["create_audio"].lower() == 'true'
        include_notion = self.settings["include_notion"].lower() == 'true'
        build_portfolio = self.settings["build_portfolio"].lower() == 'true'
        create_newsletter = self.settings["create_newsletter"].lower() == 'true'
        sendmail = self.settings["send_email"].lower() == 'true'
        unlink = self.settings["remove_pdfs_after_process"].lower() == 'true'
        
        # pre-loop: create destdir if it does not exist
        if not os.path.exists(destdir):
            os.makedirs(destdir)
     
        # loop through all pdf files in folder
        for file_path in self.files_to_read:
            
            # get file name
            file = os.path.basename(file_path)
            root_name = os.path.splitext(file)[0]
            
            # read PDF file
            print('read PDF file:', file)
            self.read_pdf(path = file_path)

            # create summary
            print('create summary')
            self.create_summary()

            # save summary locally
            print('save summary locally')
            filename = os.path.join(destdir, root_name + ".txt")
            self.save_summary(filename = filename)

            # create audio from summary
            if create_audio:
                print('create audio file')
                filename = os.path.join(destdir, root_name)
                self.create_audio_from_summary(filename = filename)

            # add summary to notion page
            if include_notion:
                print('append Notion page')
                self.get_paper_metrices(root_name)
                self.notion_create_new_page()
            
            # remove file from folder
            if unlink:
                print('remove file')
                os.remove(file_path)

        # post-loop: create newsletter text based on all created summaries
        if create_newsletter & (len(self.all_summaries)>0):
            print('create newsletter')
            self.replace_mail_body_with_newsletter_text()

        # post-loop: create pdf portfolio based on all created summaries and save locally
        if build_portfolio & (len(self.all_summaries)>0):
            print('build pdf portfolio')
            self.build_pdf_portfolio()

        # post-loop: send email
        if sendmail:
            print('send mail')
            self.send_email(include_pdf_portfolio=build_portfolio)

# run code
assi = ResearchAssistant('settings.csv', portfolio_maker=PDF())
assi.read_and_summarize_pdf()
