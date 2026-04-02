import streamlit as st
from google import genai
from docx import Document

API_KEY = "AIzaSyDIVQqKWrGiuyGAV61R3gxym3Q791X_-8U"
MODEL   = "gemini-2.5-flash"
KB_FILE = "Islamic Law of Inheritance.docx"

@st.cache_data
def load_kb():
    document = Document(KB_FILE)
    kb = ""
    for para in document.paragraphs:
        kb += para.text + "\n"
    return kb

def get_system_prompt():
    kb = load_kb()
    return f"""You are MISHKATH HELP executive. Your job is to provide answers to the customers. You should answer them in polite.
If there is any question out of the KB say you did not have that info. Only refer the KB and provide the response.
Knowledge Base:
{kb}"""

def send_message(history, user_input):
    client = genai.Client(api_key=API_KEY)

    messages = []
    for msg in history:
        # FIX: map "assistant" → "model" for Gemini API
        role = "model" if msg["role"] == "assistant" else "user"
        messages.append({"role": role, "parts": [{"text": msg["content"]}]})
    messages.append({"role": "user", "parts": [{"text": user_input}]})

    response = client.models.generate_content(
        model=MODEL,
        contents=messages,
        config={"system_instruction": get_system_prompt()},
    )
    return response.text

# ── UI ────────────────────────────────────────────────────────────────────────

st.title("MISHKATH HELP Chatbot")
st.caption("Ask me anything about Islamic Law of Inheritance")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if user_input := st.chat_input("Type your question here..."):
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            answer = send_message(st.session_state.messages[:-1], user_input)
        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
