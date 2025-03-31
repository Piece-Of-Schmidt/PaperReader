import glob
import os
import logging
import unicodedata
from openai import OpenAI
# from groq import Groq
from paperreader import PaperSummarizer, NotionManager, RichPaper, MailHandler, read_settings

# read setting
settings = read_settings()

# init llm client
# client = Groq(api_key=settings.get('Groq_API_Key'))
client = OpenAI(api_key=settings.get('OpenAI_API_Key'))

# init paper summarizer
PaperSummarizer.initialize(settings, client)

# function for file name processing
def process_file_name(file):
    # remove file endings
    base_name = os.path.splitext(file)[0]
    # normalize Unicode and convert to ASCII
    normalized_name = unicodedata.normalize('NFKD', base_name).encode('ASCII', 'ignore').decode()
    # return base name
    return os.path.basename(normalized_name)

# read variables
def str_to_bool(value):
    return str(value).lower() in ['true', '1', 'yes']

filedir = settings.get("File_Directory", "./Papers")
destdir = settings.get("Destination_Directory", "./output")
create_summary = str_to_bool(settings.get("create_summary", "false"))
create_audio = str_to_bool(settings.get("create_audio", "false"))
include_notion = str_to_bool(settings.get("include_notion", "false"))
unlink = str_to_bool(settings.get("remove_pdfs_after_process", "false"))
sendmail = str_to_bool(settings.get("send_email", "false"))

# read all files in directory
files_to_read = glob.glob(os.path.join(filedir, '*.pdf'))

# loop over all files
for file_path in files_to_read:

    # extract file name
    root_name = process_file_name(file_path)

    # init RichPaper object and read paper
    logging.info(f'Read PDF file: {file_path}')
    obj = RichPaper(path=file_path)
    obj.get_paper_and_metrices()

    # create summary
    if create_summary:
        logging.info('Create summary')
        filename = os.path.join(destdir, root_name)
        obj.create_summary(filename=filename+'_summary')
        logging.info(f'Succesfully created | {PaperSummarizer.generation_costs = }')

    # create audio from summary
    if create_summary and create_audio:
        logging.info('Create audio from summary')
        obj.create_audio_from_summary(filename=filename) # text export currently not supported by OpenAI
        logging.info(f'Succesfully created | {PaperSummarizer.generation_costs = }')

    # add summary to Notion Database if activated
    if include_notion:
        logging.info('Add paper to Notion Database')
        noti = NotionManager(paper_metrices=obj.paper_metrices, paper_summary=obj.summary)
        noti.check_and_add_missing_properties()
        noti.add_paper_to_database()
        logging.info(f'{PaperSummarizer.generation_costs = }')

    # remove pdf after processing if activated
    if unlink:
        logging.info('Remove PDF after processing')
        os.remove(file_path)

# send mail with all audio files if activated
if sendmail:
    mailer = MailHandler()
    mp3files = [f"{process_file_name(file)}.{settings.get('Audio_Format', 'mp3')}" for file in files_to_read]
    filenames = [os.path.join(destdir, file) for file in mp3files]
    mailer.send_email(filenames)
