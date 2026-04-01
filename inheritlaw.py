import streamlit as st
from google import genai
from docx import Document
import traceback
import os

# ── SECURE API KEY HANDLING ────────────────────────────────────────────────
# Priority:
# 1. Streamlit Secrets (for deployment)
# 2. Environment Variable (for local use)
# 3. Fallback (disabled intentionally)

def get_api_key():
    try:
        # Streamlit Cloud तरीका
        return st.secrets["AIzaSyAos8tFpVwhKw6IhE12TgKz7xPSASIxvLE"]
    except Exception:
        # Local environment तरीका
        return os.getenv("AIzaSyAos8tFpVwhKw6IhE12TgKz7xPSASIxvLE")

API_KEY = get_api_key()

if not API_KEY:
    st.error("❌ API Key not found. Please set it in Streamlit Secrets or Environment Variables.")
    st.stop()

# ── CONFIG ────────────────────────────────────────────────────────────────
MODEL   = "gemini-2.0-flash"
KB_FILE = "Islamic Law of Inheritance.docx"

# ── LOAD KNOWLEDGE BASE ───────────────────────────────────────────────────
@st.cache_data
def load_kb():
    try:
        document = Document(KB_FILE)
        kb = "\n".join([para.text for para in document.paragraphs])
        return kb, None
    except FileNotFoundError:
        return None, f"❌ File not found: '{KB_FILE}'. Make sure it is in your repo."
    except Exception:
        return None, f"❌ Error reading KB:\n```\n{traceback.format_exc()}\n```"

# ── SYSTEM PROMPT ─────────────────────────────────────────────────────────
def get_system_prompt(kb):
    return f"""You are MISHKATH HELP executive. Your job is to provide answers to the customers politely.
If a question is outside the KB, say you don't have that information.
Only refer to the KB.

Knowledge Base:
{kb}"""

# ── SEND MESSAGE ──────────────────────────────────────────────────────────
def send_message(history, user_input, kb):
    try:
        client = genai.Client(api_key=API_KEY)

        messages = []
        for msg in history:
            role = "model" if msg["role"] == "assistant" else "user"
            messages.append({
                "role": role,
                "parts": [{"text": msg["content"]}]
            })

        messages.append({
            "role": "user",
            "parts": [{"text": user_input}]
        })

        response = client.models.generate_content(
            model=MODEL,
            contents=messages,
            config={
                "system_instruction": get_system_prompt(kb)
            },
        )

        return response.text, None

    except Exception:
        return None, traceback.format_exc()

# ── UI ────────────────────────────────────────────────────────────────────
st.title("MISHKATH HELP Chatbot")
st.caption("Ask me anything about Islamic Law of Inheritance")

# Show SAFE API status (not actual key)
st.sidebar.markdown("🔐 **API Key Loaded:** ✅")
st.sidebar.markdown(f"**Model:** `{MODEL}`")

kb, kb_error = load_kb()
if kb_error:
    st.error(kb_error)
    st.stop()
else:
    st.sidebar.success(f"✅ KB loaded ({len(kb)} chars)")

# Chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Input
if user_input := st.chat_input("Type your question here..."):
    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            answer, err = send_message(
                st.session_state.messages[:-1],
                user_input,
                kb
            )

        if err:
            st.error(f"**Error:**\n```\n{err}\n```")
        else:
            st.markdown(answer)
            st.session_state.messages.append({
                "role": "assistant",
                "content": answer
            })