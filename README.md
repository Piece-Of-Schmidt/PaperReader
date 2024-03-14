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
2. **Set Keys**: Replace `api_key` and all other placeholders in `settings.csv` with your own keys (i.e. OpenAI API, Notion Key, email settings etc.). The latter ones are only required when the respective values in settings (include_notion, send_email) are set to true.
3. **"Upload" Papers**: Place the papers that you wish to get summarized in the *Papers* folder. This is the default folder the script reads from. You can change the directory to any other folder in the `settings.csv`.
4. **"Notion Integration"**: If you want to make use of the Notion integration, prepare your Notion Database that your summarized papers shall be stored in (see below for more information).
5. **Start process**: Run the `main.py` script or execute `read_paper.bat` to start the process.


## How it Works

- The script iterates over each PDF file located in *Papers*, extracts its text, and removes any unwanted patterns or references.
- The text is then summarized using OpenAI's GPT-4 model (default model, can be changed in settings).
- These summaries are converted to audio files using OpenAI's TTS model and saved in a specified output directory.
- The text summaries are combined in a single PDF file with the file names used as titles.
- If activated, the script sends the summaries to a Notion database. By default, a new entry is created for every paper in the *Papers* folder. The script automatically extracts the information about author(s), publishing year, and title from the file name. If the file name does not contain these information, the script sends an API call to the OpenAI Model specified in `settings['GPT_Newsletter_Model"]` which then tries to extract these information from the first 1000 chars of the paper being processed. The code expects the columns *Author*, *Year*, *Title*, and *Added* in your Database. If these columns are missing, the code will automatically create them.
- If activated, the script calls OpenAI's GPT-3.5-Turbo model (default model, can be changed in settings) to create a newsletter text based on the created summaries. This will overwrite the default email body provided in the settings.
- Finally, it sends the PDF portfolio along with the audio files to a specified email account (probably your own).
- Many settings (such as the output language, the OpenAI model, your API Keys, the audio voice, the LLM prompts, Notion connection etc.) can be modified in `settings.csv`.

## Notion integration
The app allows an upload of all summaries to a Notion Database. To use this integration, you need to provide your Notion Secret key along with the ID of the target Database. 

### get those keys
Learn how to get both keys here:

https://developers.notion.com/docs/create-a-notion-integration

### column names
To make sure everything works fine, make sure the columns in your notion database are named *Author*, *Year*, *Title*, and *Added*. The expected properties are Title, Number, Text, and Date, respectively. <br>
If `Notion_Project_Name` and/or `Notion_Document_Tags` in `settings.csv` are non-empty strings, the code tries to add those values to the Database, too. The code creates these columns automatically if they do not exist.

### document tags
If you provide `Notion_Document_Tags` in `settings.csv`, the script calls ChatGPT to assign 1-3 out of the provided labels to the paper being processed. That is, it is benefitial to provide many different and distinct labels that the model can choose from. This feature may help keep your papers organized. Although the labels are provided in a single text string, it is possible to convert these to proper tags in Notion by simply changing the property of the column to *multi-select*. <br><br>
**Note:** When you change the properties of a column in Notion (i.e. from *text* to *number* or *multi-select*) the script will fail to find this column in future processings! To avoid this, you have to re-change the column property back to the original property that the script expects (the ones presented above). In future versions of this project it will be made easier to interact with Notion. (promise!)


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

