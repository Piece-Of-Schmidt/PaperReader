import re
from datetime import date
import requests


class NotionManager:

    def __init__(self, settings, OpenAIclient=None, paper_metrices=None):
        self.settings = settings
        self.client = OpenAIclient
        self.notion_header = self.build_header()
        self.paper_metrices = paper_metrices


    # build header for Notion calls 
    def build_header(self):
        return {
            "Authorization": "Bearer " + self.settings['Notion_Token'],
            "Content-Type": "application/json",
            "Notion-Version": self.settings['Notion_Version']
        }
    
    # check paper_metrices
    def validate_paper_metrices(self):
        required_keys = ['author', 'year', 'title', 'summary']
        missing_keys = [key for key in required_keys if key not in self.paper_metrices or not self.paper_metrices[key]]
        
        # Check for missing keys
        if missing_keys:
            raise ValueError(f"Missing required paper metrices: {', '.join(missing_keys)}")

        # Ensure 'year' is an integer
        if not isinstance(self.paper_metrices['year'], int):
            raise ValueError("The 'year' in paper_metrices must be an integer.")

        print("paper_metrices validation passed.")


    # add all cloumns that do not exist
    def check_and_add_missing_properties(self):
        """
        Checks for missing properties in the Notion database and adds them if they're missing.
        """
        database_id = self.settings['Notion_Database_Id']
        get_url = f'https://api.notion.com/v1/databases/{database_id}'
        
        # Get current database schema
        response = requests.get(get_url, headers=self.notion_header)
        if response.status_code != 200:
            print("Fehler beim Abrufen der Datenbankinformationen:", response.text)
            return
        
        database_properties = response.json().get('properties', {})
        missing_properties = {}

        # Define the expected properties here
        expected_properties = {
            "Author": {"title": {}},
            "Year": {"number": {}},
            "Title": {"rich_text": {}},
            "Added": {"date": {}},
            "Project": {"rich_text": {}},
            "Tags": {"rich_text": {}},
            "Notes": {"rich_text": {}},
            # Add other properties as needed
        }

        # Check for missing properties
        for prop_name, prop_data in expected_properties.items():
            if prop_name not in database_properties:
                missing_properties[prop_name] = prop_data
        
        # Add missing properties if any
        if missing_properties:
            update_url = f'https://api.notion.com/v1/databases/{database_id}'
            payload = {"properties": missing_properties}
            response = requests.patch(update_url, headers=self.notion_header, json=payload)
            if response.status_code == 200:
                print("Fehlende Spalten erfolgreich hinzugefügt.")
            else:
                print("Fehler beim Hinzufügen fehlender Spalten:", response.text)

    # edit page in notion database
    def parse_text_content(self, text_content, header_content=None):
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
    

    # create new entry to notion database
    def add_paper_to_database(self, author=None, year=None, title=None, summary=None, project_name=None, tags_list=None):
        """
        creates a new entry to a given notion database. The database ID is provided by settings.csv.
        The database is expected to have columns "Author", "Year", "Title", "Added" und "Tags".
        To work properly, make sure the properties of your Notion Database are correctly defined:
            Autor: Title (Aa)
            Year: Number (#)
            Title: Text (<lines symbol>)
            Added: Date (<calender symbol>)
            Project: Text (<lines symbol>)
            Tags: Text (<lines symbol>)
        If the columns are missing or of the wrong property, the code will create the columns automatically.
        """
        
        # check if paper_metrices is of the right format
        self.validate_paper_metrices()

        create_url = 'https://api.notion.com/v1/pages'

        # get paper metrices from self.paper_metrices and from settings
        author = author if author is not None else self.paper_metrices['author']
        year = year if year is not None else self.paper_metrices['year']
        title = title if title is not None else self.paper_metrices['title']
        added = date.today().isoformat()
        summary = summary if summary is not None else self.paper_metrices['summary']
        project_name = project_name if project_name is not None else self.paper_metrices['project_name']
        tags_list = tags_list if tags_list is not None else self.settings['Notion_Document_Tags']
        
        properties = {
            "Author": {"title": [{"text": {"content": author}}]},
            "Year": {"number": year},
            "Title": {"rich_text": [{"text": {"content": title}}]},
            "Added": {"date": {"start": added}}, 
            }
        
        # add project name and tags if provided
        if len(project_name) > 0: properties["Project"] = {"rich_text": [{"text": {"content": project_name}}]}
        if len(tags_list) > 0:
            tags = self.create_tags(summary, tags_list)
            properties["Tags"] = {"rich_text": [{"text": {"content": tags}}]}

        # parse summary (split it into paragraphs that fit into Notion block size)
        children = self.parse_text_content(summary, header_content=title)

        # push to Notion
        payload = {"parent": {"database_id": self.settings['Notion_Database_Id']}, "properties": properties, "children": children}
        response = requests.post(create_url, headers=self.notion_header, json=payload)
        if response.status_code == 200:
            print("Neue Seite erfolgreich in Notion erstellt.")
        else:
            print("Fehler beim Erstellen der neuen Seite in Notion:", response.text)


    # create tags
    def create_tags(self, summary=None, tags_list=None):
        """
        Assigns 1-3 tags to the created article summary based on the tags list provided in settings.csv.
        If no tags list is provided or if the assignment fails, the script will just save an empty string "" as tags
        """

        # read tags list from settings if not provided
        tags_list = tags_list if tags_list is not None else self.settings['Notion_Document_Tags']

        if len(tags_list) > 0:

            summary = summary if summary is not None else self.paper_metrices['summary']
            instruction = f'''Read the following text and assign 1-3 of the following labels to it. Please only provide labels that truely describe the text. If you find no label matches the text, return "none". Return the labels as a comma-seperated list.
            Tags: {tags_list}'''
            
            try:
                tags = self.client.chat.completions.create(
                    model = self.settings['GPT_Newsletter_Model'],
                    messages=[
                        {"role": "system", "content": instruction},
                        {"role": "user", "content": summary}
                    ]).choices[0].message.content
                
            except Exception as e:
                print(f"Error creating tags: {e}.\nNo tags saved.")
                tags = ""

            # add tags to paper metrices
            return tags
    