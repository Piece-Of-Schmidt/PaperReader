import csv
import PyPDF2
import re
import os
import glob
import smtplib
import random
from fpdf import FPDF
from openai import OpenAI
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

class PDF(FPDF):
    def header(self):
        self.set_font('helvetica', 'B', 12)
        self.cell(0, 10, 'Portfolio', 0, 1, 'C')

    def chapter_title(self, title):
        self.set_font('helvetica', 'B', 12)
        self.cell(0, 10, title, 0, 1, 'L')
        self.ln(10)

    def chapter_body(self, body):
        self.set_font('helvetica', '', 12)
        self.multi_cell(0, 10, body)
        self.ln()

class ResearchAssistant:

    def __init__(self, settings_path='settings.csv', portfolio_maker=None):
        self.settings = self.read_settings(path=settings_path)
        self.client = OpenAI(api_key = self.settings["API_Key"])
        self.pdf = None
        self.summary = None
        self.all_summaries = []
        self.audio = None
        self.pdf_maker = portfolio_maker

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
            reader = PyPDF2.PdfReader(path)
            pages = [reader.pages[idx].extract_text() for idx in range(len(reader.pages))]
            pages = ''.join(pages)
            pages = re.sub(self.settings["Exclude_Pattern"], '', pages)

            if remove_references:
                pages = re.sub('(\n)?References(\n)?.*', '', pages, flags=re.DOTALL)

            self.pdf = pages
        except Exception as e:
            print(f"Error reading PDF {path}: {e}")
            self.pdf = None

    
    def create_summary(self):
        """
        Creates a summary of the provided text.
        """
        if not self.pdf:
            print("No PDF file available.")
            return
        
        lang = self.settings['Inference_Language']
        suffix = f" Please answer in {lang}." if lang != "English" else ""
        
        instruction = self.settings["LLM_Instruction"]
        prompt = f"{self.settings['LLM_Prompt']}{suffix} \n\n {self.pdf}"
        
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

    def relace_mail_body_with_newsletter_text(self):
        """
        Creates a newsletter text based on the summaries.
        """
        lang = self.settings["Summary_Language"]
        suffix = f" Please answer in {lang}." if lang != "English" else ""
        
        instruction = self.settings['Newsletter_Prompt']
        prompt = f"{' \n\nNext text:\n\n'.join(self.all_summaries)}{suffix}"
        
        try:
            newsletter_text = self.client.chat.completions.create(
                model = self.settings['GTP_Newsletter_Model'],
                messages=[
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": prompt}
                ]).choices[0].message.content
            self.settings['Email_Body'] = newsletter_text
        except Exception as e:
            print(f"Error creating newsletter: {e}")

    def send_email(self, build_portfolio=False):
        """
        Sends an email with the specified settings and attachments.
        """
        try:
            msg = MIMEMultipart()
            msg['From'] = self.settings['Email_From']
            msg['To'] = self.settings['Email_To']
            msg['Subject'] = self.settings['Email_Subject']
            msg.attach(MIMEText(self.settings['Email_Body'], 'plain', 'utf-8'))

            # Attach files
            relevant_files = glob.glob(os.path.join(self.settings['Destination_Directory'], f'*{self.settings['Audio_Format']}'))
            if build_portfolio:
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
        
    def read_and_summarize_pdf(self, remove_after_process=True):

        filedir = self.settings["File_Directory"]
        destdir = self.settings["Destination_Directory"]
        create_audio = self.settings["create_audio"].lower() == 'true'
        create_newsletter = self.settings["create_newsletter"].lower() == 'true'
        sendmail = self.settings["send_email"].lower() == 'true'
        unlink = self.settings["remove_pdfs_after_process"].lower() == 'true'
        build_portfolio = self.settings["build_portfolio"].lower() == 'true'
        all_files = glob.glob(os.path.join(filedir, '*.pdf'))
        
        # double check: create destdir if it does not exist
        if not os.path.exists(destdir):
            os.makedirs(destdir)

        if build_portfolio:
            pdf = self.pdf_maker
            pdf.add_page()

        for file_path in all_files:
            
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
            filename = os.path.join(destdir, root_name + ".txt")
            self.save_summary(filename = filename)

            # create audio from summary
            if create_audio:
                print('create audio file')
                filename = os.path.join(destdir, root_name)
                self.create_audio_from_summary(filename = filename)

            # remove file from folder
            if unlink:
                print('remove file')
                os.remove(file_path)

        # create newsletter
        if create_newsletter:
            print('create newsletter')
            self.relace_mail_body_with_newsletter_text()

        # build and save portfolio locally
        if build_portfolio:
            print('build pdf portfolio')
            filenames = [os.path.splitext(os.path.basename(file))[0] for file in all_files]
            for summary, meta in zip(self.all_summaries, filenames):
                title = meta.encode('latin-1', 'replace').decode('latin-1')
                body = summary.encode('latin-1', 'replace').decode('latin-1')
                pdf.chapter_title(title)
                pdf.chapter_body(body)
            pdf.output(os.path.join(destdir, 'Portfolio.pdf'))

        # send email
        if sendmail: self.send_email(build_portfolio=build_portfolio)


# run code
assi = ResearchAssistant('settings.csv', portfolio_maker=PDF())
assi.read_and_summarize_pdf()