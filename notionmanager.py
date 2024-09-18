import re
import logging
from datetime import date
import requests


class NotionManager:
    def __init__(self, settings, OpenAIclient=None, paper_metrices=None):
        """
        Initialisiert den NotionManager mit den gegebenen Einstellungen und dem OpenAI-Client.
        """
        self.settings = settings
        self.client = OpenAIclient
        self.notion_header = self.build_header()
        self.paper_metrices = paper_metrices

    def build_header(self):
        """
        Baut den Header für Notion-API-Aufrufe basierend auf den Einstellungen.
        """
        return {
            "Authorization": "Bearer " + self.settings.get('Notion_Token', ''),
            "Content-Type": "application/json",
            "Notion-Version": self.settings.get('Notion_Version', '2021-08-16')
        }

    def validate_paper_metrices(self):
        """
        Überprüft, ob die erforderlichen Schlüssel in paper_metrices vorhanden sind und gültig sind.
        """
        required_keys = ['author', 'year', 'title', 'summary']
        missing_keys = [key for key in required_keys if not self.paper_metrices.get(key)]

        for key in missing_keys:
            self.paper_metrices[key] = 'not provided'

        # Sicherstellen, dass 'year' ein Integer ist
        try:
            self.paper_metrices['year'] = int(self.paper_metrices['year'])
        except (ValueError, TypeError):
            logging.error("Der 'year'-Wert in paper_metrices muss ein Integer sein.")
            raise ValueError("The 'year' in paper_metrices must be an integer.")

        logging.info("paper_metrices validation passed.")

    def check_and_add_missing_properties(self):
        """
        Überprüft auf fehlende Eigenschaften in der Notion-Datenbank und fügt sie hinzu, falls sie fehlen.
        """
        database_id = self.settings.get('Notion_Database_Id', '')
        get_url = f'https://api.notion.com/v1/databases/{database_id}'

        # Abrufen des aktuellen Datenbankschemas
        response = requests.get(get_url, headers=self.notion_header)
        if response.status_code != 200:
            logging.error(f"Fehler beim Abrufen der Datenbankinformationen: {response.text}")
            return

        database_properties = response.json().get('properties', {})
        missing_properties = {}

        # Erwartete Eigenschaften definieren
        expected_properties = {
            "Author": {"title": {}},
            "Year": {"number": {}},
            "Title": {"rich_text": {}},
            "Added": {"date": {}},
            "Project": {"rich_text": {}},
            "Abstract": {"rich_text": {}},
            "Tags": {"rich_text": {}},
            "Notes": {"rich_text": {}},
            # Weitere Eigenschaften können hier hinzugefügt werden
        }

        # Überprüfen auf fehlende Eigenschaften
        for prop_name, prop_data in expected_properties.items():
            if prop_name not in database_properties:
                missing_properties[prop_name] = prop_data

        # Fehlende Eigenschaften hinzufügen
        if missing_properties:
            update_url = f'https://api.notion.com/v1/databases/{database_id}'
            payload = {"properties": missing_properties}
            response = requests.patch(update_url, headers=self.notion_header, json=payload)
            if response.status_code == 200:
                logging.info("Fehlende Spalten erfolgreich hinzugefügt.")
            else:
                logging.error(f"Fehler beim Hinzufügen fehlender Spalten: {response.text}")

    def parse_text_content(self, text_content, title=None):
        """
        Transformiert die Zusammenfassung in das korrekte Format für Notion-Blöcke.
        """
        blocks = []

        # Überschrift hinzufügen
        if title:
            header = {
                'object': 'block',
                'type': 'heading_3',
                'heading_3': {
                    'rich_text': [
                        {
                            'type': 'text',
                            'text': {'content': title},
                            'annotations': {'bold': True}
                        }
                    ]
                }
            }
            blocks.append(header)

        # Textinhalt in Absätze aufteilen (aufgrund von Größenbeschränkungen pro Block)
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

        # Leerzeile hinzufügen
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

    def add_paper_to_database(self, author=None, year=None, title=None, summary=None, project_name=None, abstract=None, tags_list=None):
        """
        Erstellt einen neuen Eintrag in der angegebenen Notion-Datenbank.
        """
        # Überprüfen, ob paper_metrices das richtige Format hat
        self.validate_paper_metrices()

        create_url = 'https://api.notion.com/v1/pages'

        # Paper-Metriken aus self.paper_metrices und settings abrufen
        author = author if author is not None else self.paper_metrices.get('author', 'Unknown')
        year = year if year is not None else self.paper_metrices.get('year', 0)
        title = title if title is not None else self.paper_metrices.get('title', 'Untitled')
        added = date.today().isoformat()
        summary = summary if summary is not None else self.paper_metrices.get('summary', '')
        project_name = project_name if project_name is not None else self.paper_metrices.get('project_name', '')
        abstract = abstract if abstract is not None else self.paper_metrices.get('abstract', '')
        tags_list = tags_list if tags_list is not None else self.settings.get('Notion_Document_Tags', '')

        properties = {
            "Author": {"title": [{"text": {"content": author}}]},
            "Year": {"number": year},
            "Title": {"rich_text": [{"text": {"content": title}}]},
            "Added": {"date": {"start": added}},
            "Abstract": {"rich_text": [{"text": {"content": abstract}}]},
        }

        # Projektname und Tags hinzufügen, falls vorhanden
        if project_name:
            properties["Project"] = {"rich_text": [{"text": {"content": project_name}}]}
        if tags_list:
            tags = self.create_tags(summary, tags_list)
            properties["Tags"] = {"rich_text": [{"text": {"content": tags}}]}

        # Zusammenfassung in Notion-Blöcke aufteilen
        children = self.parse_text_content(summary, title=title)

        # Daten an Notion senden
        payload = {
            "parent": {"database_id": self.settings.get('Notion_Database_Id', '')},
            "properties": properties,
            "children": children
        }
        response = requests.post(create_url, headers=self.notion_header, json=payload)
        if response.status_code == 200:
            logging.info("Neue Seite erfolgreich in Notion erstellt.")
        else:
            logging.error(f"Fehler beim Erstellen der neuen Seite in Notion: {response.text}")

    def create_tags(self, summary=None, tags_list=None):
        """
        Weist der erstellten Artikelzusammenfassung 1-3 Tags basierend auf der in settings.csv bereitgestellten Tags-Liste zu.
        """
        # Tags-Liste aus Einstellungen abrufen, falls nicht bereitgestellt
        tags_list = tags_list if tags_list is not None else self.settings.get('Notion_Document_Tags', '')

        if tags_list:
            summary = summary if summary is not None else self.paper_metrices.get('summary', '')
            instruction = (
                f"Read the following text and assign 1-3 of the following labels to it. "
                f"Please only provide labels that truly describe the text. "
                f"If you find no label matches the text, return 'none'. "
                f"Return the labels as a comma-separated list.\nTags: {tags_list}"
            )

            try:
                response = self.client.chat.completions.create(
                    model=self.settings.get('GPT_Newsletter_Model', ''),
                    messages=[
                        {"role": "system", "content": instruction},
                        {"role": "user", "content": summary}
                    ]
                )
                tags = response.choices[0].message.content.strip()
            except Exception as e:
                logging.error(f"Fehler beim Erstellen der Tags: {e}. Keine Tags gespeichert.")
                tags = ""
            return tags
        else:
            logging.warning("Keine Tags-Liste verfügbar.")
            return ""
