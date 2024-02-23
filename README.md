# Research Paper to Audio Summarizer

## Overview
This project is a Python-based tool designed to automatically convert PDF documents into summarized audio files. It reads PDF files, generates summaries using OpenAI's GPT-4 model, converts these summaries into audio format, and then sends them via email. It's particularly useful for processing research papers or documents where quick audio summaries are beneficial.<br><br>For demonstration purposes, there is already one paper located in the *Papers* folder and the created summary in *Outputs*.

## Features
- **PDF Reading**: Extracts text from PDF files.
- **Text Summarization**: Uses OpenAI's GPT-4 model to generate concise summaries.
- **Text-to-Speech**: Converts summaries into audio files.
- **Email Integration**: Sends the generated audio files via email.
- **Newsletter**: If activated, creates an automated Newsletter based on the created summaries and uses this newsletter as e-mail text.
- **Notion Integration**: Uploads all summaries to a pre defined Notion Database. 

## Installation

Before running the script, ensure you have installed all required dependencies:

```bash
pip install -r requirements.txt
```

## Usage

1. **Download/Clone Respository**
2. **Set API Key**: Replace `api_key` in `settings.csv` with your OpenAI API key.
3. **Configure Email Settings**: If `send_email` in `settings.csv` is set to True, make sure you have your email login, sending and receiving details added to the settings file.
4. **"Upload" Papers**: Place the papers that you wish to get summarized in the *Papers* folder. This is the default folder the script reads from. You can change the directory to any other folder in the `settings.csv`.
5. **Start process**: Run the python script or execute `read_paper.bat` to start the process.


## How it Works

- The script iterates over each PDF file located in *Papers*, extracts its text, and removes any unwanted patterns or references.
- The text is then summarized using OpenAI's GPT-4 model (default model, can be changed in settings).
- These summaries are converted to audio files using OpenAI's TTS model and saved in a specified output directory.
- The text summaries are combined in a single PDF file with the file names used as titles.
- If activated, the script sends the summaries to a Notion database. By default, a new entry is created for every paper in the "Papers" folder. The script automatically extracts the information about author(s), publishing year, and title from the file name. If the file name does not contain these information, the script sends an API call to the OpenAI Model specified in `settings['GPT_Newsletter_Model"]` which then tries to extract these information from the first 1000 chars of the paper being processed. The Notion database needs to contain the columns "autor", "year", and "title" for the script to work properly.
- If activated, the script calls OpenAI's GPT-3.5-Turbo model (default model, can be changed in settings) to create a newsletter text based on the created summaries. This will overwrite the default email body provided in the settings.
- Finally, it sends the PDF portfolio along with the audio files to a specified email account (probably your own).
- Many settings (such as the output language, the OpenAI model, your API Keys, the audio voice, the LLM prompts, Notion connection etc.) can be modified in `settings.csv`

## Notion integration
The app allows an upload of all summaries to a Notion Database. To use this integration, you need to provide your Notion Secret key along with the ID of the target database. Learn how to get both keys here:

https://developers.notion.com/docs/create-a-notion-integration
<br>
To make sure everything works fine, make sure the columns in your notion database are named "author", "year", and "title". If you need different or more than these columns, you will need to change the code. In future versions of this project it will be made easier to interact with notion.

## Requirements

- Python 3.x
- Packages listed in requirements.txt
- OpenAI API key
- For Notion integration: Notion key and database ID
- Internet connection for API access

## Note

- It is recommended to use meaningful file names for the pdf files you wish to get summarised. These file names are used as headlines in the PDF summary portfolio (and in Notion, if activated).
- Ensure you have the necessary permissions to use and share the content of the PDFs you are processing.
- Handle your API keys and email credentials securely.

