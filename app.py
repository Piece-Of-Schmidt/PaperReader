import streamlit as st
import os
import glob
import logging
import unicodedata
import tempfile
import time
import shutil
from openai import OpenAI
# from groq import Groq # Keep if you plan to add Groq later
from paperreader import PaperSummarizer, NotionManager, RichPaper, MailHandler, read_settings # Assuming paperreader.py is in the same directory

# --- Basic Page Configuration ---
st.set_page_config(
    page_title="Research Paper Summarizer",
    page_icon="📚",
    layout="wide"
)

# --- Logging Setup ---
# Streamlit handles basic logging display, but configure for consistency
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')

# --- Helper Functions ---
def str_to_bool(value):
    return str(value).lower() in ['true', '1', 'yes']

def get_default_settings():
    """Load defaults, useful for initializing state."""
    # In a real app, might load from a default config file
    # For now, use reasonable defaults or derive from settings.json structure
    return {
        "create_summary": True,
        "create_audio": True,
        "include_notion": False,
        "send_email": True,
        "remove_pdfs_after_process": False,
        "OpenAI_API_Key": "",
        "Summarizer_Model": "gpt-4o-mini",
        "Audio_Model": "gpt-4o-mini-audio-preview",
        "Text_Output_Language": "German",
        "Audio_Output_Language": "English",
        "TTS_Voice": "shuffle",
        "TTS_Speed": 1.1,
        "Audio_Format": "mp3",
        "Notion_Version": "2022-06-28",
        "Notion_Token": "",
        "Notion_Database_Id": "",
        "Notion_Project_Name": "",
        "SMTP_Host": "",
        "SMTP_Port": "587", # Common port for TLS
        "SMTP_User": "",
        "SMTP_Password": "",
        "Email_From": "",
        "Email_To": "",
        "Email_Subject": "New Summaries",
        "Email_Body": "Hey Bud,\n\nattached you find some awesome new paper summaries.\nEnjoy listening!\n\nBest,\nme"
    }

# --- Initialize Session State ---
# Store settings and results across reruns
if 'current_settings' not in st.session_state:
    st.session_state.current_settings = get_default_settings()
if 'processing_results' not in st.session_state:
    st.session_state.processing_results = [] # List to store results for each file
if 'total_cost' not in st.session_state:
    st.session_state.total_cost = {'input_tokens': 0, 'output_tokens': 0}

# --- UI: Sidebar for Configuration ---
st.sidebar.title("⚙️ Configuration")

settings = st.session_state.current_settings # Work with the state copy

# --- General Settings ---
st.sidebar.header("General")
settings["OpenAI_API_Key"] = st.sidebar.text_input(
    "OpenAI API Key",
    value=settings.get("OpenAI_API_Key", ""),
    type="password",
    help="Your OpenAI API key (e.g., sk-...)."
)
# settings["Groq_API_Key"] = st.sidebar.text_input("Groq API Key", value=settings.get("Groq_API_Key", ""), type="password", help="Optional: Your Groq API key.") # Add if needed

settings["remove_pdfs_after_process"] = st.sidebar.checkbox(
    "Delete original PDF after processing",
    value=settings.get("remove_pdfs_after_process", False)
)

# --- Summarization Settings ---
st.sidebar.header("📄 Summarization")
settings["create_summary"] = st.sidebar.checkbox(
    "Create Text Summary",
    value=settings.get("create_summary", True)
)
if settings["create_summary"]:
    # Model Selection (OpenAI only for now)
    summarizer_models = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]
    settings["Summarizer_Model"] = st.sidebar.selectbox(
        "Summarizer Model",
        options=summarizer_models,
        index=summarizer_models.index(settings.get("Summarizer_Model", "gpt-4o-mini"))
    )
    # Language Selection
    languages = ["English", "German", "French", "Spanish", "Italian", "Portuguese", "Chinese", "Japanese", "Korean"]
    settings["Text_Output_Language"] = st.sidebar.selectbox(
        "Summary Language",
        options=languages,
        index=languages.index(settings.get("Text_Output_Language", "English"))
    )

# --- Audio Settings ---
st.sidebar.header("🔊 Audio Generation")
settings["create_audio"] = st.sidebar.checkbox(
    "Create Audio from Summary",
    value=settings.get("create_audio", True)
)
if settings["create_audio"]:
    # Ensure summary is also created if audio is requested
    if not settings["create_summary"]:
        st.sidebar.warning("Audio creation requires summary creation to be enabled.")
        # Optional: force summary creation if audio is enabled
        # settings["create_summary"] = True

    # --- CORRECTED MODEL LIST AND SELECTION ---
    # Define available models, including the preview model and standard TTS
    audio_models = ["gpt-4o-mini-audio-preview", "tts-1", "tts-1-hd"]
    # Define the preferred default model
    default_audio_model = "gpt-4o-mini-audio-preview"
    # Get current setting from session state or use the default
    current_audio_model = settings.get("Audio_Model", default_audio_model)

    # Validate selection against available models
    if current_audio_model not in audio_models:
        st.sidebar.warning(f"Invalid audio model '{current_audio_model}' found. Defaulting to '{default_audio_model}'.")
        current_audio_model = default_audio_model
        settings["Audio_Model"] = current_audio_model # Update setting if corrected

    # Safely get the index for the selectbox
    try:
        audio_model_index = audio_models.index(current_audio_model)
    except ValueError:
        audio_model_index = audio_models.index(default_audio_model) # Fallback to default index

    # Display the selectbox for Audio Model
    settings["Audio_Model"] = st.sidebar.selectbox(
        "Audio Model", # More general label
        options=audio_models,
        index=audio_model_index,
        key="audio_model_selector",
        help="Select the model for audio generation. 'gpt-4o-mini-audio-preview' uses Chat Completions API, while 'tts-1' models use the dedicated TTS API."
    )
    # --- END CORRECTION ---

    # Language selection (remains the same)
    settings["Audio_Output_Language"] = st.sidebar.selectbox(
        "Audio Language",
        options=languages,
        index=languages.index(settings.get("Audio_Output_Language", "English"))
        # Note: Language primarily affects the prompt for 'audio-preview' models,
        # and is auto-detected but useful context for TTS models.
    )

    # Voice selection (remains the same, used by both model types in your code)
    voice_options = ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer', 'shuffle']
    current_voice = settings.get("TTS_Voice", "shuffle")
    if current_voice not in voice_options:
        current_voice = 'shuffle' # Default to shuffle if invalid
        settings["TTS_Voice"] = current_voice
    voice_index = voice_options.index(current_voice)
    settings["TTS_Voice"] = st.sidebar.selectbox(
        "TTS Voice",
        options=voice_options,
        index=voice_index,
        help="Select the voice for audio output. 'shuffle' picks randomly."
    )

    # Speed setting (primarily used by TTS models in your code)
    settings["TTS_Speed"] = st.sidebar.slider(
        "TTS Speed",
        min_value=0.25, max_value=4.0,
        value=float(settings.get("TTS_Speed", 1.0)),
        step=0.05,
        help="Adjust playback speed. Primarily affects 'tts-1' models."
    )

    # Audio format selection (remains the same)
    format_options = ["mp3", "opus", "aac", "flac"]
    current_format = settings.get("Audio_Format", "mp3")
    if current_format not in format_options:
        current_format = "mp3"
        settings["Audio_Format"] = current_format
    format_index = format_options.index(current_format)
    settings["Audio_Format"] = st.sidebar.selectbox(
        "Audio Format",
        options=format_options,
        index=format_index
    )


# --- Notion Settings ---
st.sidebar.header("📝 Notion Integration")
settings["include_notion"] = st.sidebar.checkbox(
    "Upload to Notion",
    value=settings.get("include_notion", False)
)
if settings["include_notion"]:
    settings["Notion_Token"] = st.sidebar.text_input(
        "Notion Integration Token",
        value=settings.get("Notion_Token", ""),
        type="password",
        help="Your Notion Internal Integration Token."
    )
    settings["Notion_Database_Id"] = st.sidebar.text_input(
        "Notion Database ID",
        value=settings.get("Notion_Database_Id", ""),
        help="The ID of the Notion database."
    )
    settings["Notion_Project_Name"] = st.sidebar.text_input(
        "Notion Project Name (Optional)",
        value=settings.get("Notion_Project_Name", "")
    )
    settings["Notion_Version"] = "2022-06-28" # Keep fixed or make selectable if needed

# --- Email Settings ---
st.sidebar.header("📧 Email Notification")
settings["send_email"] = st.sidebar.checkbox(
    "Send Results via Email",
    value=settings.get("send_email", True)
)
if settings["send_email"]:
    st.sidebar.subheader("Receiver")
    settings["Email_To"] = st.sidebar.text_input(
        "Recipient Email(s)",
        value=settings.get("Email_To", ""),
        help="Comma-separated list of email addresses."
    )
    settings["Email_Subject"] = st.sidebar.text_input(
        "Email Subject",
        value=settings.get("Email_Subject", "New Summaries")
    )
    # Use text_area for multi-line body editing
    settings["Email_Body"] = st.sidebar.text_area(
        "Email Body",
        value=settings.get("Email_Body", "Hey Bud,\n\nAttached you find some awesome new paper summaries.\nEnjoy listening!\n\nBest,\nme"),
        height=150
    )

    st.sidebar.subheader("Sender (SMTP Configuration)")
    settings["Email_From"] = st.sidebar.text_input(
        "Sender Email Address",
        value=settings.get("Email_From", "")
    )
    settings["SMTP_Host"] = st.sidebar.text_input(
        "SMTP Host",
        value=settings.get("SMTP_Host", ""),
        help="e.g., smtp.gmail.com or smtp.office365.com"
    )
    settings["SMTP_Port"] = st.sidebar.text_input(
        "SMTP Port",
        value=settings.get("SMTP_Port", "587"),
        help="e.g., 587 (TLS) or 465 (SSL)"
    )
    settings["SMTP_User"] = st.sidebar.text_input(
        "SMTP Username",
        value=settings.get("SMTP_User", ""),
        help="Usually your sender email address."
    )
    settings["SMTP_Password"] = st.sidebar.text_input(
        "SMTP Password/App Password",
        value=settings.get("SMTP_Password", ""),
        type="password",
        help="Your email account password or an app-specific password."
    )

# Update session state with potentially changed settings
st.session_state.current_settings = settings

# --- UI: Main Area ---
st.title("📚 Research Paper Summarizer")
st.markdown("Upload PDF research papers, get text summaries and audio versions, and optionally send them to Notion or via email.")

# --- File Upload ---
uploaded_files = st.file_uploader(
    "Drag and drop PDF files here",
    type="pdf",
    accept_multiple_files=True,
    help="Upload one or more research papers in PDF format."
)

# --- Processing Button ---
process_button = st.button("🚀 Process Uploaded Papers")

# Define a persistent temporary directory name
PERSISTENT_TEMP_DIR = "streamlit_temp_output"

# --- Processing Logic ---
if process_button and uploaded_files:
    # --- Validation ---
    if not settings.get("OpenAI_API_Key"):
        st.error("❌ Please enter your OpenAI API Key in the sidebar.")
        st.stop()
    if settings["include_notion"] and (not settings.get("Notion_Token") or not settings.get("Notion_Database_Id")):
        st.error("❌ Notion upload is enabled, but Token or Database ID is missing in the sidebar.")
        st.stop()
    if settings["send_email"] and (not settings.get("Email_To") or not settings.get("Email_From") or not settings.get("SMTP_Host") or not settings.get("SMTP_User") or not settings.get("SMTP_Password")):
        st.error("❌ Email sending is enabled, but one or more required fields (Recipient, Sender, SMTP details) are missing in the sidebar.")
        st.stop()

    # --- Initialization ---
    st.session_state.processing_results = [] # Clear previous results
    st.session_state.total_cost = {'input_tokens': 0, 'output_tokens': 0} # Reset costs

    # Clear the directory from previous runs if it exists
    if os.path.exists(PERSISTENT_TEMP_DIR):
        try:
            shutil.rmtree(PERSISTENT_TEMP_DIR)
            logging.info(f"Cleared previous temporary directory: {PERSISTENT_TEMP_DIR}")
        except OSError as e:
            st.error(f"Error clearing temporary directory {PERSISTENT_TEMP_DIR}: {e}")
            st.stop()
    # Create the directory for this run
    try:
        os.makedirs(PERSISTENT_TEMP_DIR, exist_ok=True)
        logging.info(f"Created temporary directory for this run: {PERSISTENT_TEMP_DIR}")
        st.session_state.output_dir = PERSISTENT_TEMP_DIR # Store the path in session state
    except OSError as e:
        st.error(f"Error creating temporary directory {PERSISTENT_TEMP_DIR}: {e}")
        st.stop()
    # Use this directory path
    temp_dir = st.session_state.output_dir

    try:
        # Initialize LLM Client (only OpenAI for now)
        client = OpenAI(api_key=settings["OpenAI_API_Key"])
        # Initialize PaperSummarizer with current settings and client
        PaperSummarizer.initialize(settings, client)
    except Exception as e:
        st.error(f"🚨 Failed to initialize OpenAI client: {e}")
        st.stop()

    # Create a temporary directory for processing and output files
    # with tempfile.TemporaryDirectory() as temp_dir:
    st.info(f"Processing {len(uploaded_files)} file(s)... Temporary directory: {temp_dir}")

    output_files_mapping = {} # To store output paths for download/email

    overall_progress = st.progress(0)
    start_time = time.time()

    for i, uploaded_file in enumerate(uploaded_files):
        file_result = {"original_filename": uploaded_file.name}
        try:
            # Save uploaded file temporarily
            temp_pdf_path = os.path.join(temp_dir, uploaded_file.name)
            with open(temp_pdf_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            logging.info(f"Processing file: {uploaded_file.name}")
            st.markdown(f"--- \n### Processing: `{uploaded_file.name}`")
            status_placeholder = st.empty()

            # --- Core Processing ---
            status_placeholder.info("📄 Reading PDF...")
            rich_paper = RichPaper(path=temp_pdf_path)
            rich_paper.get_paper_and_metrices() # Reads PDF, extracts metadata

            file_result["metrices"] = rich_paper.paper_metrices
            output_base_name = unicodedata.normalize('NFKD', os.path.splitext(uploaded_file.name)[0]).encode('ASCII', 'ignore').decode().replace(' ', '_')
            output_base_path = os.path.join(temp_dir, output_base_name) # Save outputs in temp dir

            if rich_paper.paper is None:
                status_placeholder.error("Failed to read PDF content.")
                file_result["error"] = "Failed to read PDF content."
                st.session_state.processing_results.append(file_result)
                continue # Skip to next file

            summary_text = None
            summary_file_path = None
            if settings["create_summary"]:
                with st.spinner("🧠 Generating summary..."):
                    status_placeholder.info("🧠 Generating summary...")
                    summary_filename_base = output_base_path + '_summary'
                    rich_paper.create_summary(filename=summary_filename_base)
                    summary_text = rich_paper.summary
                    summary_file_path = summary_filename_base + ".txt"
                    file_result["summary_text"] = summary_text
                    file_result["summary_file"] = summary_file_path
                    if os.path.exists(summary_file_path):
                        output_files_mapping[summary_file_path] = f"{output_base_name}_summary.txt"
                    else: # Handle case where create_summary might fail internally
                        file_result["error"] = file_result.get("error", "") + " Summary file not created."
                        st.warning(f"Summary text file not found at {summary_file_path}")

                    status_placeholder.success(f"✅ Summary created ({PaperSummarizer.generation_costs['output_tokens']:.4f}$ Output Cost)")

            audio_file_path = None
            if settings["create_audio"] and summary_text: # Need summary to create audio
                with st.spinner("🔊 Generating audio..."):
                    status_placeholder.info("🔊 Generating audio...")
                    audio_filename_base = output_base_path + '_audio'
                    # Use the dedicated TTS model logic within create_audio_from_summary
                    # We adjusted the settings to use 'tts-1'/'tts-1-hd', the method should handle it.
                    # Pass the base filename, the method adds the extension.
                    rich_paper.create_audio_from_summary(filename=audio_filename_base) # This now uses the selected TTS model via call_model
                    audio_file_path = f"{audio_filename_base}.{settings['Audio_Format']}"
                    file_result["audio_file"] = audio_file_path
                    if os.path.exists(audio_file_path):
                        output_files_mapping[audio_file_path] = f"{output_base_name}_audio.{settings['Audio_Format']}"
                    else:
                        file_result["error"] = file_result.get("error", "") + " Audio file not created."
                        st.warning(f"Audio file not found at {audio_file_path}")

                    status_placeholder.success(f"✅ Audio created ({PaperSummarizer.generation_costs['output_tokens']:.4f}$ Output Cost)") # Note: TTS cost calculation needs refinement based on characters.
            elif settings["create_audio"] and not summary_text:
                status_placeholder.warning("⚠️ Audio creation skipped (summary not available).")


            if settings["include_notion"] and summary_text:
                with st.spinner("📝 Uploading to Notion..."):
                    status_placeholder.info("📝 Uploading to Notion...")
                    # Ensure NotionManager uses the *current* settings and summary
                    noti = NotionManager(paper_metrices=rich_paper.paper_metrices, paper_summary=summary_text)
                    # NotionManager accesses settings via PaperSummarizer.settings
                    noti.check_and_add_missing_properties()
                    noti.add_paper_to_database()
                    status_placeholder.success("✅ Uploaded to Notion.")
            elif settings["include_notion"] and not summary_text:
                    status_placeholder.warning("⚠️ Notion upload skipped (summary not available).")

            # Remove original PDF if requested (from temp dir)
            if settings["remove_pdfs_after_process"]:
                try:
                    os.remove(temp_pdf_path)
                    logging.info(f"Removed temporary PDF: {temp_pdf_path}")
                except OSError as e:
                    logging.error(f"Error removing temporary PDF {temp_pdf_path}: {e}")

            # Update overall progress
            overall_progress.progress((i + 1) / len(uploaded_files))
            st.session_state.processing_results.append(file_result)


        except Exception as e:
            logging.exception(f"Error processing file {uploaded_file.name}: {e}")
            st.error(f"🚨 Error processing `{uploaded_file.name}`: {e}")
            file_result["error"] = str(e)
            st.session_state.processing_results.append(file_result)
            # Continue to next file

        # --- Post-Processing ---
        total_time = time.time() - start_time
        st.success(f"🎉 Processing complete in {total_time:.2f} seconds!")
        st.balloons()

        # Update total cost display (using the class variable accumulated during processing)
        st.session_state.total_cost = PaperSummarizer.generation_costs
        input_cost = st.session_state.total_cost.get('input_tokens', 0)
        output_cost = st.session_state.total_cost.get('output_tokens', 0)
        st.metric("💰 Estimated OpenAI Cost", f"${input_cost + output_cost:.4f}", f"Input: ${input_cost:.4f}, Output: ${output_cost:.4f}")


        # --- Email Sending ---
        if settings["send_email"] and st.session_state.processing_results:
            with st.spinner("✉️ Sending email..."):
                try:
                    # MailHandler needs the *current* settings
                    # It also reads PaperSummarizer.created_summaries, which should be populated
                    mailer = MailHandler() # It will use PaperSummarizer.settings

                    # Dynamically add paths to attachments from our temp dir
                    original_dest_dir = PaperSummarizer.settings.get("Destination_Directory")
                    PaperSummarizer.settings["Destination_Directory"] = temp_dir # Use the persistent temp dir path
                    PaperSummarizer.settings["Audio_Format"] = settings["Audio_Format"] # Ensure correct format

                    mailer.send_email() # Glob should work inside temp_dir

                    if original_dest_dir: # Restore original setting
                        PaperSummarizer.settings["Destination_Directory"] = original_dest_dir

                    st.success("✅ Email sent successfully!")
                except Exception as e:
                    st.error(f"🚨 Failed to send email: {e}")
                    logging.exception("Email sending failed.")

        # --- Display Results ---
        st.header("📊 Results")
        for result in st.session_state.processing_results:
            with st.expander(f"📄 {result['original_filename']}", expanded=True):
                if "error" in result:
                    st.error(f"🚨 Error: {result['error']}")

                if "metrices" in result:
                    meta = result["metrices"]
                    st.markdown(f"**Title:** {meta.get('title', 'N/A')}  \n"
                                f"**Author(s):** {meta.get('author', 'N/A')}  \n"
                                f"**Year:** {meta.get('year', 'N/A')}  \n"
                                f"**DOI:** {meta.get('doi_link', 'N/A')}")
                    if meta.get('abstract'):
                        with st.popover("Show Abstract"):
                            st.markdown(meta['abstract'])


                if "summary_text" in result:
                    st.subheader("Summary")
                    st.markdown(result["summary_text"])
                    if "summary_file" in result and os.path.exists(result["summary_file"]):
                         try:
                            with open(result["summary_file"], "rb") as fp:
                                st.download_button(
                                    label="⬇️ Download Summary (.txt)",
                                    data=fp,
                                    file_name=output_files_mapping[result["summary_file"]],
                                    mime="text/plain"
                                )
                         except Exception as e:
                            st.warning(f"Could not prepare summary download: {e}")


                if "audio_file" in result and os.path.exists(result["audio_file"]):
                    st.subheader("Audio")
                    try:
                        st.audio(result["audio_file"])
                        with open(result["audio_file"], "rb") as fp:
                            st.download_button(
                                label=f"⬇️ Download Audio (.{settings['Audio_Format']})",
                                data=fp,
                                file_name=output_files_mapping[result["audio_file"]],
                                mime=f"audio/{settings['Audio_Format']}"
                            )
                    except Exception as e:
                        st.warning(f"Could not load audio player or download button: {e}")

    # Temp directory is automatically cleaned up upon exiting the 'with' block

elif process_button and not uploaded_files:
    st.warning("⚠️ Please upload at least one PDF file.")

# --- Optional: Add Custom CSS ---
# Create a folder 'css' and a file 'style.css' inside it.
# Example style.css:
# /* Add rounded corners to buttons and inputs */
# .stButton>button, .stTextInput>div>div>input, .stFileUploader>div>div>button, .stSelectbox>div>div {
#     border-radius: 10px !important;
# }
# /* Style the file uploader */
# .stFileUploader {
#     border: 2px dashed #ccc;
#     border-radius: 10px;
#     padding: 20px;
#     text-align: center;
# }
# try:
#     with open("css/style.css") as f:
#         st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
# except FileNotFoundError:
#     pass # Ignore if CSS file doesn't exist
