import os
import glob
import re
import random
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from PyPDF2 import PdfReader


class PaperReader:

    def __init__(self, settings, OpenAIclient=None):
        self.settings = settings
        self.client = OpenAIclient
        self.files_to_read = glob.glob(os.path.join(self.settings["File_Directory"], '*.pdf'))
        self.paper = None
        self.all_summaries = []
        self.audio = None
        self.paper_metrices = None
        

    # load PDF into python
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

            # extract paper metrices
            filename = os.path.splitext(os.path.basename(path))[0]
            self.get_paper_metrices(filename)

        except Exception as e:
            print(f"Error reading PDF {path}: {e}")
            self.paper = None    


    # get all relevant information about the paper being processed (author, publishing year, and title, as well as a custom project name)
    def get_paper_metrices(self, paper_title=None, project_name=None, summary=None):
        """
        Extracts information about author, publication date and paper title from document name.
        If the document name does not contain these information (according on regex matching),
        ChatGPT (the concrete model being specified in the settings['GPT_Newsletter_Model']) tries to guess these information.
        Adds the project name provided in settings.csv to the metrices. 
        """

        # read project name from settings
        project_name = project_name if project_name is not None else self.settings['Notion_Project_Name']

        # regex
        pattern = r'^(?P<author>.+?)\s+\((?P<year>\d{4})\)\s+(?P<title>.+)$'
        match = re.match(pattern, paper_title)
        
        # search for regex in document name
        if match:
            metrices = match.groupdict()
            metrices['year'] = int(metrices['year'])  # year to integer

        # if pattern is not found: ask LLM to predict values    
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
                print(f"Error extracting paper metrices: {e}")
        
        # add project name from settings.csv
        metrices['project_name'] = project_name

        # get abstract
        metrices['abstract'] = self.extract_abtract()

        # add summary and tags dummies
        metrices['summary'] = summary

        self.paper_metrices = metrices

    # extract abstract from paper
    def extract_abtract(self, paper=None):
        """
        Extracts the abstract from the paper being processed based on a simple regex search. 
        """
        paper = paper if paper is not None else self.paper

        # use regex search to find summary
        match = re.search('Abstract(.*)', paper, flags=re.S|re.I)

        if match:
            abstract = match.group().strip()[0:2000]+'...'
            abstract = re.sub('(key( )?words|introduction)(.*)','', abstract, flags=re.S|re.I)
            abstract = re.sub('\n|abstract', ' ', abstract, flags=re.I).strip()

        else:
            abstract = 'No abstract found.'

        return abstract

    # create summary based on paper
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
            self.paper_metrices['summary'] = summary
            self.all_summaries.append(summary)
        except Exception as e:
            print(f"Error creating summary: {e}")


    # save summary locally
    def save_summary(self, filename):
        """
        Saves the created summary locally.
        """
        if self.paper_metrices['summary']:
            try:
                with open(filename, 'w') as file:
                    file.write(self.paper_metrices['summary'])
            except Exception as e:
                print(f"Error saving summary: {e}")


    # create audio file
    def create_audio_from_summary(self, filename):
        """
        Creates an audio file based on the created summary and saves it locally.
        """
        if not self.paper_metrices['summary']:
            print("No summary available to create audio.")
            return

        try:
            voice = random.choice(['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer']) if self.settings['TTS_Voice'] == 'shuffle' else self.settings['TTS_Voice']
            self.audio = self.client.audio.speech.create(
                model = self.settings['TTS_Model'],
                voice = voice,
                speed = float(self.settings['TTS_Speed']),
                input = self.paper_metrices['summary'],
            )
            self.audio.stream_to_file(filename + self.settings['Audio_Format'])
        except Exception as e:
            print(f"Error creating audio: {e}")


    # if newsletter: make ChatGPT create a newletter text based on all text summaries
    def create_newsletter_text(self, all_summaries=None):
        """
        Creates a newsletter text based on the summaries that are stored in PaperReader.all_summaries. If a list of texts is provided via function arg, the function will use those instead. 
        """
        
        # load all summaries
        all_summaries = all_summaries if all_summaries is not None else self.all_summaries

        # let ChatGPT create Newsletter text
        lang = self.settings['Inference_Language']
        suffix = f" Please answer in {lang}." if lang != "English" else ""
        
        instruction = self.settings['Newsletter_Prompt']
        prompt = ' \n\nNext text:\n\n'.join(all_summaries) + suffix
        
        try:
            newsletter_text = self.client.chat.completions.create(
                model = self.settings['GPT_Newsletter_Model'],
                messages=[
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": prompt}
                ]).choices[0].message.content
            
        except Exception as e:
            print(f"Error creating newsletter: {e}")

        return newsletter_text


    # method for sending email with attachments
    def send_email(self, include_pdf_portfolio=False):
        """
        Sends an email with the specified settings and attachments.
        """
        if self.settings['include_notion'].lower() == 'true':
            self.settings['Email_Body'] = self.settings['Email_Body'] + '\n\nLink to Notion Database:\n' + f"https://www.notion.so/{self.settings['Notion_Database_Id']}"
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

