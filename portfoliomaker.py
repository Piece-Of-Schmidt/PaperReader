import os
import logging
from fpdf import FPDF, XPos, YPos
from datetime import datetime

# Konfiguration des Logging-Moduls
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')


class PortfolioMaker(FPDF):
    """
    Eine Klasse zur Erstellung eines PDF-Portfolios basierend auf bereitgestellten Dateien und Zusammenfassungen.
    """
    def __init__(self, settings, files_to_read=None, summaries=None):
        super().__init__()
        self.files_to_read = files_to_read
        self.summaries = summaries
        self.settings = settings
        self.metrices_list = []

        
        # Größere Seitenränder festlegen (in Millimetern)
        self.set_margins(left=30, top=30, right=30)
        self.set_auto_page_break(auto=True, margin=25)

        # Pfad zum Schriftartenordner
        font_path = self.settings.get('Font_Directory', '')

        # Hinzufügen der Schriftarten
        try:
            self.add_font('DejaVu', '', os.path.join(font_path, 'DejaVuSans.ttf'), uni=True)
            self.add_font('DejaVu', 'B', os.path.join(font_path, 'DejaVuSans-Bold.ttf'), uni=True)
            self.add_font('DejaVu', 'I', os.path.join(font_path, 'DejaVuSans-Oblique.ttf'), uni=True)
        except Exception as e:
            logging.error(f"Fehler beim Laden der Schriftarten: {e}")

    def header(self):
        """
        Erstellt den Header für jede Seite des PDF-Dokuments.
        """
        self.set_font('DejaVu', 'B', 10)
        self.set_text_color(0, 51, 102)  # Dunkelblau
        self.cell(0, 10, 'Portfolio', new_x=XPos.LEFT, new_y=YPos.NEXT, align='C')
        self.line(25, 20, self.w - 25, 20)  # Linie an neue Ränder angepasst
        self.ln(10)

    def footer(self):
        """
        Erstellt die Fußzeile für jede Seite des PDF-Dokuments.
        """
        self.set_y(-25)
        self.set_font('DejaVu', 'I', 8)
        self.set_text_color(128)  # Grau
        self.cell(0, 10, f'Seite {self.page_no()}', new_x=XPos.LEFT, new_y=YPos.TOP, align='C')

    def chapter_title(self, title):
        """
        Fügt einen Kapiteltitel zum PDF-Dokument hinzu.
        """
        self.set_font('DejaVu', 'B', 14)
        self.set_fill_color(240, 240, 240)  # Hellgrau
        self.set_text_color(0, 51, 102)  # Dunkelblau
        self.cell(0, 15, title, new_x=XPos.LEFT, new_y=YPos.NEXT, align='L', fill=True)
        self.ln(10)

    def chapter_body(self, body, doi_link=None):
        """
        Fügt den Inhalt eines Kapitels zum PDF-Dokument hinzu.
        """
        self.set_font('DejaVu', '', 10)
        self.set_text_color(0)
        self.multi_cell(0, 6, body)
        self.ln(10)

        if doi_link:
            self.set_font('DejaVu', 'I', 11)
            self.set_text_color(0, 0, 255)  # Blau für Links
            self.cell(0, 10, 'URL to Paper', link=doi_link, ln=True)
            self.ln(10)
        else:
            self.ln(10)

    def add_toc(self):
        """
        Fügt ein Inhaltsverzeichnis zum PDF-Dokument hinzu.
        """
        self.add_page()
        self.set_font('DejaVu', 'B', 14)
        self.cell(0, 10, 'Inhaltsverzeichnis', new_x=XPos.LEFT, new_y=YPos.NEXT, align='C')
        self.ln(10)
        self.set_font('DejaVu', '', 10)
        for i, title in enumerate(self.files_to_read, start=1):
            self.cell(0, 10, f'{i}. {os.path.basename(title)}', new_x=XPos.LEFT, new_y=YPos.NEXT, align='L')
            self.ln(5)

    def build_pdf_portfolio(self):
        """
        Baut das PDF-Portfolio auf, indem es durch die bereitgestellten Dateien und Zusammenfassungen iteriert.
        """
        if not self.files_to_read or not self.summaries:
            logging.warning("Keine Dateien oder Zusammenfassungen zum Verarbeiten.")
            return

        # Deckblatt hinzufügen
        self.add_page()
        self.set_font('DejaVu', 'B', 20)
        self.cell(0, 20, 'Portfolio', new_x=XPos.LEFT, new_y=YPos.NEXT, align='C')
        self.ln(20)
        self.set_font('DejaVu', 'I', 10)
        self.cell(0, 10, f'Erstellt am {datetime.now().strftime("%d.%m.%Y")}', new_x=XPos.LEFT, new_y=YPos.NEXT, align='C')

        # Inhaltsverzeichnis hinzufügen
        self.add_toc()

        # Kapitel hinzufügen
        for title, body, metrices in zip(self.files_to_read, self.summaries, self.metrices_list):
            self.add_page()
            self.chapter_title(os.path.basename(title))
            self.chapter_body(body, doi_link=metrices.get('doi_link'))

        # PDF speichern
        output_path = os.path.join(self.settings['Destination_Directory'], 'Portfolio.pdf')
        try:
            self.output(output_path)
            logging.info(f"PDF erfolgreich erstellt: {output_path}")
        except Exception as e:
            logging.error(f"Fehler beim Erstellen des PDF-Portfolios: {e}")
