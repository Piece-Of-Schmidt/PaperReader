# install dependencies
# pip install -r requirements.txt


# Import dependencies
import csv
import PyPDF2
import re
import os
import glob
import smtplib
from openai import OpenAI
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

class ResearchAssistant:

    def __init__(self):
        self.settings = None
        self.client = None
        self.pdf = None
        self.summary = None
        self.audio = None

    def read_settings(self, path='settings.csv'):
        """
        Reads the function settings from a CSV file.
        """
        try:
            with open(path, mode='r', encoding = 'utf-8') as csv_file:
                csv_reader = csv.DictReader(csv_file)
                self.settings = {row["Setting"]: row["Value"] for row in csv_reader}
        except FileNotFoundError:
            print(f"Did not find file {path}.")
        except Exception as e:
            print(f"Error: {e}")

    def init_client(self):
        self.client = OpenAI(api_key = self.settings["API_Key"])

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
        
        lang = self.settings["Summary_Language"]
        suffix = f" Please answer in {lang}." if lang != "English" else ""
        
        instruction = self.settings["LLM_Instruction"]
        prompt = f"{self.settings['LLM_Prompt']}{suffix} \n\n {self.pdf}"
        
        try:
            self.summary = self.client.chat.completions.create(
                model = self.settings["GPT_Model"],
                messages=[
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": prompt}
                ]
            )
        except Exception as e:
            print(f"Error creating summary: {e}")

    def save_summary(self, filename):
        """
        Saves the created summary locally.
        """
        if self.summary:
            try:
                with open(filename, 'w') as file:
                    file.write(self.summary.choices[0].message.content)
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
            self.audio = self.client.audio.speech.create(
                model = self.settings["TTS_Model"],
                voice = self.settings["TTS_Voice"],
                speed = float(self.settings["TTS_Speed"]),
                input = self.summary.choices[0].message.content,
            )
            self.audio.stream_to_file(filename)
        except Exception as e:
            print(f"Error creating audio: {e}")

    def send_email(self):
        """
        Sends an email with the specified settings and attachments.
        """
        try:
            msg = MIMEMultipart()
            msg['From'] = self.settings["Email_From"]
            msg['To'] = self.settings["Email_To"]
            msg['Subject'] = self.settings["Email_Subject"]
            msg.attach(MIMEText(self.settings["Email_Body"], 'plain', 'utf-8'))

            # Attach files
            for file_path in glob.glob(os.path.join(self.settings["Destination_Directory"], '*.mp3')):
                filename = os.path.basename(file_path)
                with open(file_path, 'rb') as attachment:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f"attachment; filename= {filename}")
                msg.attach(part)

            # Setup and send the email
            server = smtplib.SMTP(self.settings["SMTP_Host"], int(self.settings["SMTP_Port"]))
            server.starttls()
            try:
                server.login(self.settings["SMTP_User"], self.settings["SMTP_Password"])
                server.send_message(msg)
            finally:
                server.quit()
        except Exception as e:
            print(f"Error sending email: {e}")
        
    def read_and_summarize_pdf(self, remove_after_process=True):

        filedir = self.settings["File_Directory"]
        destdir = self.settings["Destination_Directory"]
        sendmail = self.settings["Send_Email"].lower() == 'true'
        unlink = self.settings["remove_pdfs_after_process"].lower() == 'true'
        all_files = glob.glob(os.path.join(filedir, '*.pdf'))

        # double check: create destdir if it does not exist
        if not os.path.exists(destdir):
            os.makedirs(destdir)

        for file_path in all_files:
            
            # get file name
            file = os.path.basename(file_path)
            
            # read PDF file
            print('read PDF file:', file)
            self.read_pdf(path = file_path)

            # create summary
            print('create summary')
            self.create_summary()

            # save summary locally
            filename = os.path.join(destdir, os.path.splitext(file)[0] + ".txt")
            self.save_summary(filename = filename)

            # create audio from summary
            print('create audio file')
            filename = os.path.join(destdir, os.path.splitext(file)[0] + ".mp3")
            self.create_audio_from_summary(filename = filename)

            # remove file from folder
            if unlink:
                print('remove file')
                os.remove(file_path)

            # send email
            if sendmail: self.send_email()


## Run Code
            
assi = ResearchAssistant()
assi.read_settings()
assi.init_client()
assi.read_and_summarize_pdf()
