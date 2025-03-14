import glob
import os
import logging
import unicodedata
from openai import OpenAI
from paperreader import PaperSummarizer, NotionManager, RichPaper, MailHandler, read_settings

# read setting
settings = read_settings()

# init llm client
client = OpenAI(api_key=settings.get('OpenAI_API_Key'))

# init paper summarizer
PaperSummarizer.initialize(settings, client)

# read all files in directory
files_to_read = glob.glob(os.path.join(settings["File_Directory"], '*.pdf'))

# read variables
destdir = settings.get("Destination_Directory", "./output")
create_summary = settings.get("create_summary", "false")
create_audio = settings.get("create_audio", "false")
include_notion = settings.get("include_notion", "false")
sendmail = settings.get("send_email", "false")
unlink = settings.get("remove_pdfs_after_process", "false")

# loop over all files
for file_path in files_to_read:

    # extract file name
    file = os.path.basename(file_path)
    root_name = unicodedata.normalize('NFKD', os.path.splitext(file)[0]).encode('ASCII', 'ignore').decode()

    # init RichPaper object and read paper
    logging.info(f'Read PDF file: {file}')
    obj = RichPaper(path=file_path)
    obj.get_paper_and_metrices()

    # create summary
    if create_summary:
        logging.info('Create summary')
        obj.create_summary()
        logging.info(f'Succesfully created | {PaperSummarizer.generation_costs = }')

        # save summary on disk
        logging.info('Save summary on disk')
        filename = os.path.join(destdir, root_name + ".txt")
        obj.save_summary(filename=filename)

    # create audio from summary
    if create_summary and create_audio:
        logging.info('Create audio from summary')
        filename = os.path.join(destdir, root_name)
        obj.create_audio_from_summary(filename=filename)
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

mailer = MailHandler()
mailer.send_email()
