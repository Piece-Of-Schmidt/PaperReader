# Research Paper to Audio Summarizer

## Overview
This project is a Python-based tool designed to automatically convert PDF formatted research articles into summarized audio files. It reads PDF files, generates summaries using OpenAI's GPT-4o-mini model (default), converts these summaries into a nice audio, saves summary and abstract of the document in a Notion database (if desired) and then sends audio and text via email. It's particularly useful for processing research papers or documents where quick audio summaries are beneficial.<br><br>For demonstration purposes, there is already one paper located in the *Papers* folder and the created summary in *Outputs*.

## Features
- **PDF Reading**: Extracts text from PDF files.
- **Text Summarization**: Uses OpenAI's GPT-4o-mini model (default) to generate concise summaries.
- **Text-to-Speech**: Converts summaries into audio files using 4o-mini-audio-preview (default).
- **Email Integration**: Sends the generated audio files via email.
- **Notion Integration**: Uploads all summaries to a pre defined Notion Database (optional, has to be set to true in `settings.json`).

## Installation

Before running the script, ensure you have installed all required dependencies:

```bash
pip install -r requirements.txt
```

## Usage

1. **Download/Clone Respository**
2. **Set Keys**: Replace `api_key` and all other placeholders in `settings.json` with your own keys (i.e. OpenAI API, Notion Key, email settings etc.). The latter ones are only required when the respective values in settings (include_notion, send_email) are set to true.
3. **"Upload" Papers**: Place the papers that you wish to get summarized in the *Papers* folder. This is the default folder the script reads from. You can change the directory to any other folder in the `settings.json`.
4. **Notion Integration**: If you want to make use of the Notion integration, enable it in `settings.json` (see 1.) and prepare your Notion Database that your summarized papers shall be stored in (see below for more information).
5. **Start process**: Run the `main.py` script or execute `read_paper.bat` to start the process.


## How it Works

- The script iterates over each PDF file located in *Papers*, extracts its text.
- The text is then summarized using OpenAI's GPT-4o-mini model (default model, can be changed in settings).
- These summaries are converted to audio files using OpenAI's 4o-mini-audio-preview and saved in a specified output directory.
- If activated, the script sends the summaries to a Notion database. By default, a new entry is created for every paper in the *Papers* folder. The script automatically extracts the information about author(s), publishing year, and title from the file name. If the file name does not contain these information, the script sends an API call to the OpenAI Model specified in settings which then tries to extract these information from the first 1000 chars of the paper being processed. The script will also try to extract the abstract from the paper based on a simple regex search.
- Finally, it sends the text summaries along with the audio files to one or several specified email account(s) (probably your own).
- Many settings (such as the output language, the OpenAI model, your API Keys, the audio voice, the LLM prompts, Notion connection etc.) can be modified in `settings.json`.

## Notion integration
The app allows an upload of all summaries to a Notion Database. To use this integration, you need to provide your Notion Secret key along with the ID of the target Database. 

### get those keys
Learn how to get both keys [here](https://developers.notion.com/docs/create-a-notion-integration).

## Requirements

- Python 3.x
- Packages listed in requirements.txt
- OpenAI API key
- For Notion integration: Notion key and database ID
- Internet connection for API access

## Note

- It is recommended to use meaningful file names for the pdf files you wish to get summarised, like "author (year) title" or "author et al. (year) title".
- In theory, you can also use models different from the OpenAI model. The easiest way is probably to use a groq API key and select a free of charge model (like mixtral 8x22b). For the lack of a good open source TTS model, however, this integration is currently disabled. Check out the code to see where and how the necessary information (keys) can be integrated manually.
- Ensure you have the necessary permissions to use and share the content of the PDFs you are processing.
- Handle your API keys and email credentials securely.
