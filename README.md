# Research Paper to Audio Summarizer

## Overview
This project is a Python-based tool designed to automatically convert PDF documents into summarized audio files. It reads PDF files, generates summaries using OpenAI's GPT-4 model, converts these summaries into audio format, and then sends them via email. It's particularly useful for processing research papers or documents where quick audio summaries are beneficial.<br><br>For demonstration purposes, there is already one paper located in the *Papers* folder and the created summary in *Outputs*.

## Features
- **PDF Reading**: Extracts text from PDF files.
- **Text Summarization**: Uses OpenAI's GPT-4 model to generate concise summaries.
- **Text-to-Speech**: Converts summaries into audio files.
- **Email Integration**: Sends the generated audio files via email.

## Installation

Before running the script, ensure you have installed all required dependencies:

```bash
pip install -r requirements.txt
```

## Usage

1. **Download/Clone Respository**
2. **Set API Key**: Replace `api_key` in the script with your OpenAI API key.
3. **Configure Email Settings**: If `Send_Email` in `settings.csv` is set to True, make sure you have your email login, sending and receiving details added to the settings file.
4. **"Upload" Papers**: Place the Papers that you wish to get summarized in the *Papers* folder. This is the default folder the script reads from. You can change the directory to any other folder in the `settings.csv`.
5. **Start process**: Run the python script or execute `read_paper.bat` to start the process.


## How it Works

- The script iterates over each PDF file located in *Papers*, extracts its text, and removes any unwanted patterns or references.
- The text is then summarized using OpenAI's GPT-4 model.
- These summaries are converted to audio files and saved in a specified output directory.
- Finally, it sends these audio files as email attachments.
- By default, all PDF files located in *Papers* are removed afterwards.
- this setting as well as other settings (such as the output language, the OpenAI model, etc.) can be modified in `settings.csv`

## Notion integration
The app allows an upload of all summaries to a Notion Database. To use Notion automatically follow the followimg steps:

https://developers.notion.com/docs/create-a-notion-integration

## Requirements

- Python 3.x
- packages listed in requirements.txt
- OpenAI API key
- Internet connection for API access

## Note

- it is recommended to use meaningful file names for the pdf files you wish to get summarised. These file names are used as headlines in the PDF summary portfolio (and in Notion, if activated).
- Ensure you have the necessary permissions to use and share the content of the PDFs you are processing.
- Handle your OpenAI API key and email credentials securely.

