import csv
import os
from paperreader import PaperReader
from notionmanager import NotionManager
from portfoliomaker import PortfolioMaker
from openai import OpenAI


# ----


# read settings file
def read_settings(path='settings.csv'):
    """
    Reads the function settings from CSV file.
    """
    try:
        with open(path, mode='r', encoding = 'utf-8') as csv_file:
            csv_reader = csv.DictReader(csv_file)
            settings = {row["Setting"]: row["Value"] for row in csv_reader}
        return settings
    except FileNotFoundError:
        print(f"Did not find file {path}.")
    except Exception as e:
        print(f"Error: {e}")

# set wd
script_directory = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_directory)

# read settings
settings = read_settings('settings.csv')

# init OpenAI Client
OpenAIclient = OpenAI(api_key = settings['API_Key'])


# ----


# init Class
assi = PaperReader(settings, OpenAIclient)

# dim vars
destdir = settings["Destination_Directory"]
create_audio = settings["create_audio"].lower() == 'true'
include_notion = settings["include_notion"].lower() == 'true'
build_portfolio = settings["build_portfolio"].lower() == 'true'
create_newsletter = settings["create_newsletter"].lower() == 'true'
sendmail = settings["send_email"].lower() == 'true'
unlink = settings["remove_pdfs_after_process"].lower() == 'true'


# ----


# create destdir if it does not exist
if not os.path.exists(destdir):
    os.makedirs(destdir)

# call NotionManager - and check if all required columns exist. If not: add those missing columns
if include_notion:
    noti = NotionManager(settings, OpenAIclient)
    noti.check_and_add_missing_properties()

# call portfolio maker
if build_portfolio:
    pdf = PortfolioMaker(settings, assi.files_to_read, assi.all_summaries)


# ----


# loop through all pdf files in folder
for file_path in assi.files_to_read:
    
    # get file name
    file = os.path.basename(file_path)
    root_name = os.path.splitext(file)[0]
    
    # read PDF file
    print('read PDF file:', file)
    assi.read_pdf(path = file_path)

    # create summary
    if create_summary:
        print('create summary')
        assi.create_summary()

        # save summary locally
        print('save summary locally')
        filename = os.path.join(destdir, root_name + ".txt")
        assi.save_summary(filename = filename)

    # create audio from summary
    if create_summary and create_audio:
        print('create audio file')
        filename = os.path.join(destdir, root_name)
        assi.create_audio_from_summary(filename = filename)

    # create audio from summary
    if create_audio:
        print('create audio file')
        filename = os.path.join(destdir, root_name)
        assi.create_audio_from_summary(filename = filename)

    # add summary to notion page
    if include_notion:
        print('append Notion page')
        noti.paper_metrices = assi.paper_metrices
        noti.add_paper_to_database()
    
    # remove file from folder
    if unlink:
        print('remove file')
        os.remove(file_path)

# post-loop: create newsletter text based on all created summaries
if create_newsletter and (len(assi.all_summaries)>0):
    print('create newsletter')
    newsletter_text = assi.create_newsletter_text()
    assi.settings['Email_Body'] = newsletter_text

# post-loop: create pdf portfolio based on all created summaries and save locally
if build_portfolio and (len(assi.all_summaries)>0):
    print('build pdf portfolio')
    pdf.build_pdf_portfolio()

# post-loop: send email
if sendmail:
    print('send mail')
    assi.send_email(include_pdf_portfolio=build_portfolio)

