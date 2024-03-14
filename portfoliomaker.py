import os
from fpdf import FPDF, XPos, YPos


class PortfolioMaker(FPDF):
    def __init__(self, settings, files_to_read=None, summaries=None):
        super().__init__()
        self.files_to_read = files_to_read
        self.summaries = summaries
        self.settings = settings

    def header(self):
        self.set_font('helvetica', 'B', 12)
        self.cell(0, 10, 'Portfolio', new_x=XPos.LEFT, new_y=YPos.NEXT, align='C')

    def footer(self):
        self.set_y(-15)
        self.set_font('helvetica', 'I', 8)
        self.cell(0, 10, f'Seite {self.page_no()}', new_x=XPos.LEFT, new_y=YPos.TOP, align='C')

    def chapter_title(self, title):
        self.set_font('helvetica', 'B', 14)
        self.cell(0, 10, title, new_x=XPos.LEFT, new_y=YPos.NEXT, align='L')
        self.ln(10)

    def chapter_body(self, body):
        self.set_font('helvetica', '', 12)
        self.multi_cell(0, 10, body)
        self.ln()

    def build_pdf_portfolio(self):
        if not self.files_to_read or not self.summaries:
            print("No files or summaries to process.")
            return
        
        for title, body in zip(self.files_to_read, self.summaries):

            self.add_page()
            self.set_margins(10, 10, 10)

            self.chapter_title(os.path.basename(title))
            self.chapter_body(body)
        
        self.output(os.path.join(self.settings['Destination_Directory'], 'Portfolio.pdf'))
