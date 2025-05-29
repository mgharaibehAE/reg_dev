import streamlit as st
import openai
import requests
import google.generativeai as genai
from docx import Document
from pdf2image import convert_from_bytes
import pytesseract
import time
import io

# Load API keys from Streamlit secrets
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
ASSISTANT_ID = st.secrets["ASSISTANT_ID"]
GROK_API_KEY = st.secrets["GROK_API_KEY"]
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

genai.configure(api_key=GEMINI_API_KEY)

with tab_upload:
    st.header("Upload and Chat with Document")

    ai_model = st.selectbox("Choose AI Model", ["OpenAI Assistant", "Grok", "Gemini"])

    uploaded_file = st.file_uploader("Upload a Word (.docx) or PDF (.pdf) file", type=["docx", "pdf"], accept_multiple_files=True)

    if uploaded_file:
        uploaded_file_names = [file.name for file in uploaded_file]
        if 'last_uploaded_file_name' not in st.session_state or st.session_state.last_uploaded_file_name != uploaded_file_names:
            st.session_state.file_chat_messages = []
            st.session_state.file_thread_id = None
            st.session_state.last_uploaded_file_name = uploaded_file_names

        file_text = ""
        if ai_model != "Gemini":
            for file in uploaded_file:
                file_bytes = file.read()
                if file.type == "application/pdf":
                    images = convert_from_bytes(file_bytes)
                    for image in images:
                        text = pytesseract.image_to_string(image)
                        file_text += text + "\n"
                else:
                    doc = Document(file)
                    file_text += "\n".join(paragraph.text for paragraph in doc.paragraphs) + "\n"

        if "file_thread_id" not in st.session_state or st.session_state.file_thread_id is None:
            if ai_model == "OpenAI Assistant":
                openai.api_key = OPENAI_API_KEY
                file_thread = openai.beta.threads.create()
                st.session_state.file_thread_id = file_thread.id
                openai.beta.threads.messages.create(
                    thread_id=st.session_state.file_thread_id,
                    role="user",
                    content=f"The following document content is provided for context:\n\n{file_text}"
                )
            else:
                st.session_state.file_chat_context = file_text

        for message in st.session_state.file_chat_messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        user_input = st.chat_input("Ask questions about the uploaded document(s)...")

        if user_input:
            st.session_state.file_chat_messages.append({"role": "user", "content": user_input})
            response = ""

            with st.spinner("Assistant is typing..."):
                if ai_model == "OpenAI Assistant":
                    openai.api_key = OPENAI_API_KEY
                    openai.beta.threads.messages.create(
                        thread_id=st.session_state.file_thread_id,
                        role="user",
                        content=user_input
                    )
                    run = openai.beta.threads.runs.create(
                        thread_id=st.session_state.file_thread_id,
                        assistant_id=ASSISTANT_ID
                    )
                    while run.status not in ("completed", "failed"):
                        time.sleep(1)
                        run = openai.beta.threads.runs.retrieve(
                            thread_id=st.session_state.file_thread_id,
                            run_id=run.id
                        )
                    if run.status == "completed":
                        messages = openai.beta.threads.messages.list(thread_id=st.session_state.file_thread_id)
                        response = next((msg.content[0].text.value for msg in messages.data if msg.role == "assistant"), "")
                    else:
                        response = "Assistant failed to respond. Please retry."

                elif ai_model == "Grok":
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {GROK_API_KEY}"
                    }
                    data = {
                        "messages": [
                            {"role": "system", "content": "You are an assistant helping with document queries."},
                            {"role": "user", "content": st.session_state.file_chat_context + "\n" + user_input}
                        ],
                        "model": "grok-3-latest",
                        "stream": False,
                        "temperature": 0
                    }
                    grok_response = requests.post("https://api.x.ai/v1/chat/completions", headers=headers, json=data)
                    response = grok_response.json()['choices'][0]['message']['content']

                elif ai_model == "Gemini":
                    uploaded_files = []
                    for file in uploaded_file:
                        file_data = file.read()
                        uploaded_files.append(genai.upload_file(file_data, mime_type=file.type))

                    model = genai.GenerativeModel('gemini-1.5-flash')
                    chat = model.start_chat(history=[
                        {"role": "user", "parts": uploaded_files},
                    ])
                    gemini_response = chat.send_message(user_input)
                    response = gemini_response.text

            st.session_state.file_chat_messages.append({"role": "assistant", "content": response})

            with st.chat_message("assistant"):
                st.markdown(response)
