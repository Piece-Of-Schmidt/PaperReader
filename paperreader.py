import os
import glob
import re
import random
import logging
import base64
import tiktoken
import requests
import json
import smtplib
import fitz
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders


# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')


# define function to read settings from a JSON file
def read_settings(path='settings.json'):
    """
    Reads the settings from a JSON file.
    :param path: Path to the settings file.
    :return: Dictionary containing the settings.
    """
    try:
        with open(path, 'r', encoding='utf-8') as file:
            settings = json.load(file)
        return settings
    except FileNotFoundError:
        logging.error(f"File {path} not found.")
        return {}
    except Exception as e:
        logging.exception(f"Error reading settings: {e}")
        return {}


# define main class
class PaperSummarizer:
    settings = None
    client = None
    generation_costs = {'input_tokens': 0, 'output_tokens': 0}
    created_summaries = []

    def get_price_factors(self, model_name, in_modality='text', out_modality='text'):
        """
        Returns the price factors for input and output tokens for a given model and modality.
        :param model_name: Name of the model (e.g. 'gpt-4o', 'gpt-4o-audio-preview')
        :param in_modality: Modality of the input ('text' or 'audio')
        :param out_modality: Modality of the output ('text' or 'audio')
        :return: Tuple with (input_factor, output_factor)
        """
        # mapping of price factors for different models and modalities
        price_mapping = {
            'gpt-4o': {
                'text': {'input_factor': 2.5, 'output_factor': 10}
            },
            'gpt-4o-audio-preview': {
                'text': {'input_factor': 2.5, 'output_factor': 10},
                'audio': {'input_factor': 40, 'output_factor': 80}
            },
            'gpt-4o-mini-audio-preview': {
                'text': {'input_factor': 0.15, 'output_factor': 0.6},
                'audio': {'input_factor': 10, 'output_factor': 20}
            },
            'gpt-4o-mini': {
                'text': {'input_factor': 0.15, 'output_factor': 0.6}
            },
            'tts-1-hd': {
                'text': {'input_factor': 8, 'output_factor': 8} # rough estimation - price is calculated based on the number of characters rather than tokens (Char-Price: 30/Million Chars)
            }
        }
        
        try:
            input_factor = price_mapping[model_name][in_modality]['input_factor']
            output_factor = price_mapping[model_name][out_modality]['output_factor']
        except KeyError:
            raise ValueError(f"Price factors for model '{model_name}' with in_modality'{in_modality}' and out_modality '{out_modality}' not found.")
        
        return input_factor, output_factor

    def num_tokens_from_string(self, string: str, encoding_name: str) -> int:
        """Returns the number of tokens in a text string."""
        encoding = tiktoken.get_encoding(encoding_name)
        num_tokens = len(encoding.encode(string))
        return num_tokens
    
    def call_model(self, instruction, prompt, model_name=None, voice=None, filename=None, file_format=None):
        """
        Calls LLM model, calculates costs for inference and returns the response text.
        :param instruction: Instruction for the model.
        :param prompt: Prompt for the model.
        :param model_name: Name of the model to use.
        :param voice: Voice for audio output.
        :param filename: Name of the file to save the audio output.
        :param file_format: Format of the audio file.
        :return: Response text from the model.
        """
        model_name = model_name if model_name else self.settings.get('Summarizer_Model', 'gpt-4o-mini')
        audio = {"voice": voice, "format": file_format} if 'audio-preview' in model_name else None
        out_modality = ['audio', 'text'] if 'audio-preview' in model_name else ['text']
        lang = self.settings.get('Audio_Output_Language', 'English') if 'audio-preview' in model_name or 'tts' in model_name else self.settings.get('Text_Output_Language', 'English')
        n_tokens = self.num_tokens_from_string(prompt+instruction, 'o200k_base')

        logging.info(f'Settings: Model: {model_name} | Language: {lang} | Voice: {voice} | Format: {file_format} | Input length: {n_tokens} tokens')

        try:
            if 'tts' in model_name:
                # shorten summary if too long for TTS
                if len(prompt) > 4096:
                    logging.warning("Provided summary is too long for TTS' context window. Text will be truncated.")

                # create audio
                audio_file = self.client.audio.speech.create(
                    model=model_name,
                    voice=voice,
                    speed=float(self.settings.get('TTS_Speed', 1.0)),
                    input=prompt[:4096],
                )
                response_text = prompt[:4096]

                # save locally
                if filename and file_format:
                    audio_file.stream_to_file(f'{filename}.{file_format}')

            else:
                # set up kwargs for model call (make sure both openAI and groq Clients are supported)
                kwargs = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": instruction},
                        {"role": "user", "content": prompt}
                    ],
                    **({"modalities": out_modality, "audio": audio} if 'gpt' in model_name else {})
                }
                # call text model
                response = self.client.chat.completions.create(**kwargs)

                # get response text
                response_text = response.choices[0].message.content.strip() if 'audio-preview' not in model_name else '<audio-preview model does not currently support audio + text output>'

                # save response text locally
                if filename:
                    with open(f'{filename}.txt', 'w', encoding='utf-8') as file:
                        file.write(response_text)
            
            # if audio was created with openai model (except with tts, see above): save audio file locally
            if 'audio-preview' in model_name and filename and file_format:
                audio_file = base64.b64decode(response.choices[0].message.audio.data)
                with open(f'{filename}.{file_format}', 'wb') as f:
                    f.write(audio_file)

            # calculate and add costs
            if 'gpt' in model_name:
                input_factor, output_factor = self.get_price_factors(model_name, 'text', out_modality[0])
                PaperSummarizer.generation_costs['input_tokens'] += round((response.usage.prompt_tokens / 1000000) * input_factor, 4)
                PaperSummarizer.generation_costs['output_tokens'] += round((response.usage.completion_tokens / 1000000) * output_factor, 4)

        except Exception as e:
            response_text = ''
            logging.error(f'Error calling model: {e}')

        return response_text
    
    @classmethod
    def initialize(cls, settings, client):
        cls.settings = settings
        cls.client = client


class NotionManager(PaperSummarizer):
    def __init__(self, paper_metrices=None, paper_summary=None):
        """
        Initializes the NotionManager with the given paper metrices and summary.
        :param paper_metrices: Dictionary containing the paper metrices.
        :param paper_summary: Summary of the paper.
        """
        self.notion_header = self.build_header()
        self.paper_metrices = paper_metrices
        self.summary = paper_summary

    def build_header(self):
        """
        Builds the header for the Notion API requests.
        """
        return {
            "Authorization": "Bearer " + self.settings.get('Notion_Token', ''),
            "Content-Type": "application/json",
            "Notion-Version": self.settings.get('Notion_Version', '2021-08-16')
        }

    def validate_paper_metrices(self):
        """
        Checks if the paper_metrices dictionary has the required keys and values.
        """
        required_keys = ['author', 'year', 'title']
        missing_keys = [key for key in required_keys if not self.paper_metrices.get(key)]

        for key in missing_keys:
            self.paper_metrices[key] = 'not provided'

        # make sure year is an integer
        try:
            self.paper_metrices['year'] = int(self.paper_metrices['year'])
        except (ValueError, TypeError):
            logging.error("The 'year' in paper_metrices must be an integer.")
            raise ValueError("The 'year' in paper_metrices must be an integer.")

        logging.info("paper_metrices validation passed.")

    def check_and_add_missing_properties(self):
        """
        Checks if the Notion database has all the required properties and adds the missing ones.
        """
        database_id = self.settings.get('Notion_Database_Id', '')
        get_url = f'https://api.notion.com/v1/databases/{database_id}'

        # read database properties
        response = requests.get(get_url, headers=self.notion_header)
        if response.status_code != 200:
            logging.error(f"Error reading database properties: {response.text}")
            return

        database_properties = response.json().get('properties', {})
        missing_properties = {}

        # define expected properties
        expected_properties = {
            "Title": {"title": {}},
            "Author": {"rich_text": {}},
            "Year": {"number": {}},
            "Added": {"date": {}},
            "Essence": {"rich_text": {}},
            "Status": {
                "select": {
                    "options": [
                        {"name": "To Do", "color": "red"},
                        {"name": "In Progress", "color": "yellow"},
                        {"name": "Done", "color": "green"}
                    ]
                }
            },
            "URL": {"url": {}},
            "Project": {"rich_text": {}},
            "Notes": {"rich_text": {}}
        }

        # check for missing properties
        for prop_name, prop_data in expected_properties.items():
            if prop_name not in database_properties:
                missing_properties[prop_name] = prop_data

        # add any missing properties
        if missing_properties:
            update_url = f'https://api.notion.com/v1/databases/{database_id}'
            payload = {"properties": missing_properties}
            response = requests.patch(update_url, headers=self.notion_header, json=payload)
            if response.status_code == 200:
                logging.info("Missing properties successfully added.")
            else:
                logging.error(f"Failed to add missing properties: {response.text}")

    def parse_text_content(self, text_content, title=None):
        """
        Splits text content into Notion blocks so that they fit into character limit.
        :param text_content: Text content to be split into blocks.
        :param title: Title of the text content.
        :return: List of Notion blocks.
        """
        blocks = []

        # add title as heading
        if title:
            header = {
                'object': 'block',
                'type': 'heading_3',
                'heading_3': {
                    'rich_text': [
                        {
                            'type': 'text',
                            'text': {'content': '🐇 Summary of: ' + title},
                            'annotations': {'bold': True}
                        }
                    ]                }
            }
            blocks.append(header)

        # split text content into chunks due to text block character limits
        text_chunks = re.findall(r".{1,2000}(?=\s|$|\n)", text_content)
        for chunk in text_chunks:
            paragraph_block = {
                'object': 'block',
                'type': 'paragraph',
                'paragraph': {
                    'rich_text': [
                        {'type': 'text', 'text': {'content': chunk.strip()}}
                    ]
                }
            }
            blocks.append(paragraph_block)

        # add empty paragraph block
        blocks.append({
            'object': 'block',
            'type': 'paragraph',
            'paragraph': {
                'rich_text': [
                    {'type': 'text', 'text': {'content': "\n"}}
                ]
            }
        })

        return blocks

    def add_paper_to_database(self, author=None, year=None, title=None, summary=None, project_name=None, abstract=None, doi_link=None):
        """
        Creates a new page in the Notion database with the given paper metrices.
        :param author: Author of the paper.
        :param year: Year of the paper.
        :param title: Title of the paper.
        :param summary: Summary of the paper.
        :param project_name: Name of the project.
        :param abstract: Abstract of the paper.
        :param doi_link: DOI link of the paper.
        """
        # check if paper_metrices have valid values
        self.validate_paper_metrices()

        create_url = 'https://api.notion.com/v1/pages'

        # read paper metrices from paper metrices dictionary
        author = author if author is not None else self.paper_metrices.get('author', 'Unknown')
        year = year if year is not None else self.paper_metrices.get('year', 0)
        title = title if title is not None else self.paper_metrices.get('title', 'Untitled')
        added = date.today().isoformat()
        summary = summary if summary is not None else self.summary
        project_name = project_name if project_name is not None else self.paper_metrices.get('project_name', '')
        abstract = abstract if abstract is not None else self.paper_metrices.get('abstract', '')
        doi_link = doi_link if doi_link is not None else self.paper_metrices.get('doi_link', '')

        # create properties for the new page
        properties = {
            "Title": {"title": [{"text": {"content": title}}]},
            "Author": {"rich_text": [{"text": {"content": author}}]},
            "Year": {"number": year},
            "Added": {"date": {"start": added}},
            "Essence": {"rich_text": [{"text": {"content": self.create_one_line_summary(summary)}}]},
            "Status": {"select": {"name": "To Do", "color": "red"}},
            "URL": {"url": doi_link}
        }

        # add project name to properties
        if project_name:
            properties["Project"] = {"rich_text": [{"text": {"content": project_name}}]}

        # add abstract to children
        children = []
        if abstract:
            children.append({
                'object': 'block',
                'type': 'callout',
                'callout': {
                    'rich_text': [
                        {'type': 'text', 'text': {'content': 'Abstract: '}, 'annotations': {'bold': True}},
                        {'type': 'text', 'text': {'content': abstract.strip()}}
                    ],
                    'icon': {'emoji': '📌'}
                }
            })
            
        # add summary to children
        children += self.parse_text_content(summary, title=title)

        # send request to create page
        payload = {
            "parent": {"database_id": self.settings.get('Notion_Database_Id', '')},
            "properties": properties,
            "children": children
        }
        response = requests.post(create_url, headers=self.notion_header, json=payload)
        if response.status_code == 200:
            logging.info(f"Page successfully created: '{title}'.")
        else:
            logging.error(f"Failed to create page: {response.text}")

    def create_one_line_summary(self, summary=None):
        """
        Creates a one-line summary of the given text.
        :param summary: Text to summarize.
        :return: One-line summary of the text.
        """
        summary = summary if summary is not None else self.summary
        instruction = 'Summarize the following text in one line. Like "Investigates the relationship between chinese and european foreign politics with NLP methods" or "Analyzes the impact of climate change on the global economy".'
        return self.call_model(instruction, summary)
    

class RichPaper(PaperSummarizer):
    def __init__(self, path=None):
        self.path = path
        self.paper = None
        self.paper_metrices = None
        self.summary = None
    
    def get_paper_and_metrices(self):
        """
        Reads the paper from the given path and extracts the metrices.
        Adds data like author, title and year based on document names or info from PDF.
        Adds the project name from settings.csv to the metrices, Extracts the DOI of the paper and generates a link to find the paper.
        Extracts the abstract from the paper.
        """
        
        # read paper
        self.read_pdf(self.path)
        
        # get author year and date information
        filename = os.path.splitext(os.path.basename(self.path))[0]
        metrices = self.get_author_year_title(filename)

        # add num tokens
        metrices['n_tokens_paper'] = self.num_tokens_from_string(self.paper, 'o200k_base')

        # add project name
        metrices['project_name'] = self.settings.get('Notion_Project_Name', '')

        # add DOI and DOI link
        doi_pattern = r'\b(10\.\d{4,9}/[-._;()/:A-Z0-9]+)\b'
        doi_match = re.search(doi_pattern, self.paper[:10000])
        metrices['doi_link'] = f"https://doi.org/{doi_match.group(1)}" if doi_match else None
    
        # extract abstract
        metrices['abstract'] = self.extract_abstract()

        self.paper_metrices = metrices


    def read_pdf(self, remove_references_and_appendix=True):
        """
        Reads the PDF file from the given path and stores the content in the object.
        :param remove_references_and_appendix: If True, removes the references and appendix from the paper.
        """
        
        try:
            pages = []
            doc = fitz.open(self.path) # open document
            [pages.append(page.get_text()) for page in doc]
            whole_doc = ''.join(pages)

            # clean document
            whole_doc = re.sub('-\n', '', whole_doc)
            whole_doc = re.sub('\n', ' ', whole_doc)
            whole_doc = re.sub(' +', ' ', whole_doc)

            if remove_references_and_appendix:
                whole_doc = re.sub(r'(\n)+References.{0,2}(\n)+.*', '', whole_doc, flags=re.DOTALL)

            self.paper = whole_doc

        except FileNotFoundError as e:
            logging.error(f"PDF-Datei nicht gefunden {self.path}: {e}")
            self.paper = None
        except Exception as e:
            logging.exception(f"Unerwarteter Fehler beim Lesen der PDF-Datei {self.path}: {e}")
            self.paper = None


    def get_author_year_title(self, paper_title):
        """
        Extacts information about author, year and title from the document name.
        If this information is not contained in the document name, the LLM tries to estimate it.
        :param paper_title: The title of the paper.
        :return: A dictionary with the extracted metrices.
        """

        # regex pattern for extracting author, year and title from document name
        pattern = r'^(?P<author>(?:[\w\s.]+(?:,\s*)?)+?)\s+\((?P<year>\d{4})\)\s+(?P<title>.+)$'
        match = re.match(pattern, paper_title)

        metrices = {}
        # search for author, year and title in document name
        if match:
            metrices = match.groupdict()
            metrices['year'] = int(metrices['year']) # year as integer
        else:
            instruction = 'Please extract from the following text the information about the author(s), the publishing year and the title. Provide the information in the following format: author (year) title'
            try:
                content = self.call_model(instruction, self.paper[:1000])
                match = re.match(pattern, content)
                if match:
                    metrices = match.groupdict()
                    metrices['year'] = int(metrices['year'])  # year as integer
                else:
                    logging.warning("Meta data could not be extracted from the document name or the text.")
                    metrices = {'author': 'Unknown', 'year': 0, 'title': 'Unknown'}
            except Exception as e:
                logging.error(f"Error extracting metrices: {e}")
                metrices = {'author': 'Unknown', 'year': 0, 'title': 'Unknown'}

        return metrices


    def extract_abstract(self, paper=None):
        """
        Extracts the abstract from a provided paper paper.
        :param paper: The paper from which the abstract should be extracted.
        :return: The extracted abstract.
        """
        paper = paper if paper is not None else self.paper

        # search for abstract in paper
        match = re.search(r'Abstract(.*?)(\n\n|\Z)', paper, flags=re.S | re.I)

        if match:
            abstract = match.group(1).strip()[:1995] + '...'
            abstract = re.sub(r'(key( )?words|introduction)(.*)', '', abstract, flags=re.S | re.I)
            abstract = re.sub(r'^abstract', '', abstract, flags=re.I).strip()
        else:
            abstract = 'No abstract found.'

        return abstract


    def create_summary(self, instruction=None, prompt=None, model_name=None, filename=None):
        """
        Creates a summary of the paper using the LLM.
        :param instruction: The instruction for the LLM.
        :param prompt: The prompt for the LLM.
        :param model_name: The name of the model to use ('gpt-4o-mini' as default).
        :param filename: The name of the file to save the summary to (file format is added automaticall (.txt)).
        """
        model_name = model_name if model_name is not None else self.settings.get('Summarizer_Model', 'gpt-4o-mini')

        if not self.paper:
            logging.warning("No PDF provided.")
            return

        # set language for text output
        lang = self.settings.get('Text_Output_Language', 'English')
        suffix = f" Please answer in {lang}." if lang != "English" else ""

        # call llm to summarize paper
        instruction = 'You are a research assistant specializing in summarizing research papers.' if instruction is None else instruction
        prompt = prompt if prompt is not None else 'Your task is to write a detailed summary of the following research paper. Focus on the methodology and the results of the paper. Finally relate the results to other research on this topic.'
        prompt  = f'{prompt}{suffix}\n\n{self.paper}'
        output = self.call_model(instruction, prompt, model_name=model_name, filename=filename)
        
        # store summary in object
        self.summary = output
        PaperSummarizer.created_summaries.append(output)


    def create_audio_from_summary(self, filename=None, model_name=None, ensure_audio_quality=True):
        """
        Creates an audio file from the summary using the LLM.
        :param filename: The name of the file to save the audio to.
        :param ensure_audio_quality: If True, the summary is reformulated for better listening experience.
        :param model_name: The name of audio generation model ('gpt-4o-mini-audio-preview' as default).
        """
        model_name = model_name if model_name is not None else self.settings.get('Audio_Model', 'gpt-4o-mini-audio-preview')
        lang = self.settings.get('Audio_Output_Language', 'English')
        file_format = self.settings.get('Audio_Format', '.mp3')
        voice_options = ['alloy', 'ash', 'coral', 'echo', 'fable', 'onyx', 'nova', 'shimmer']
        voice_setting = self.settings.get('TTS_Voice', 'alloy')
        voice = random.choice(voice_options) if voice_setting == 'shuffle' else voice_setting

        # define instruction for audio generation / reformulation
        instruction = f'''You are an experienced researcher with years of expertise in transforming complex content into audio content for an interested audience. Your task is to convert the following document into a compelling, naturally-flowing text.\n
Please consider these elements:
- Transform formal language into natural, spoken language
- Maintain a conversational yet professional(!) tone
- don't exagerate or hype up the content, be professional, authentic and engaging
- keep all relevant information from the document
- pleae talk in {lang}'''

        try:
            # reformulate summary for better listeing experience
            if 'audio-preview' not in model_name and ensure_audio_quality:                
                logging.info("Reformulating summary for better listening experience.")
                summary = self.call_model(instruction, self.summary, model_name=model_name, filename=filename)
            else:
                summary = self.summary
            
            # call model and save audio locally (except groq model is used - in this case save audio in a separate step)
            self.call_model(instruction=instruction, prompt=summary, model_name=model_name, voice=voice, filename=filename, file_format=file_format)

            # ------ currently disabled since Neets API is not available anymore ------
            # when groq is used - build audio file with Neets API
            # if not 'gpt' in model_name:
            #     audio_file = requests.request(
            #         method="POST",
            #         url="https://api.neets.ai/v1/tts",
            #         headers={
            #             "Content-Type": "application/json",
            #             "X-API-Key": self.settings.get('Neets_API_Key')
            #         },
            #         json={
            #             "text": summary,
            #             "voice_id": self.settings.get('Neets_voice'),
            #             "params": {
            #             "model": "vits"
            #             }
            #         }
            #     )
            #
            #     # save file
            #     with open(f"{filename}.{file_format}", "wb") as f:
            #         f.write(audio_file.content)
            # ------ currently disabled since Neets API is not available anymore ------
        
        except Exception as e:
            logging.error(f"Error creating audio file: {e}")


class MailHandler(PaperSummarizer):
    def __init__(self):
        self.paper_metrices = None
        self.include_notion = self.settings.get('Include_Notion', False)

    def send_email(self, files_to_send = None):
        """
        Sends an email with the generated summaries and the paper as attachment.
        """
        if self.include_notion:
            self.settings['Email_Body'] += '\n\nLink to Notion Database:\n' + f"https://www.notion.so/{self.settings['Notion_Database_Id']}"

        # add all summaries
        self.settings['Email_Body'] += '\n\nSummaries:\n\n' + '\n\n'.join(PaperSummarizer.created_summaries)

        # create email
        msg = MIMEMultipart()
        msg['From'] = self.settings.get('Email_From')
        recipients = [email.strip() for email in self.settings.get('Email_To', '').split(',')]
        msg['To'] = ', '.join(recipients)
        msg['Subject'] = self.settings.get('Email_Subject')
        msg.attach(MIMEText(self.settings.get('Email_Body', ''), 'plain', 'utf-8'))

        # get all relevant files in the destination directory
        files_to_send = files_to_send if files_to_send is not None else glob.glob(os.path.join(self.settings['Destination_Directory'], f"*{self.settings.get('Audio_Format', 'mp3')}"))

        # add audio files as attachments
        for file_path in files_to_send:
            basename = os.path.basename(file_path)
            
            try:
                with open(file_path, 'rb') as attachment:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename= {basename}')
                msg.attach(part)
            except Exception as e:
                logging.error(f"Error adding attachment {basename}: {e}")

        # send mail
        try:
            with smtplib.SMTP(self.settings['SMTP_Host'], int(self.settings['SMTP_Port'])) as server:
                server.starttls()
                server.login(self.settings['SMTP_User'], self.settings['SMTP_Password'])
                server.send_message(msg)
                logging.info(f"Succesfully sent email to {len(recipients)} recipients.")
        except Exception as e:
            logging.error(f"Error sending email: {e}")