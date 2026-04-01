import streamlit as st
from google import genai
from docx import Document
import traceback

# ── Secure API key loading ────────────────────────────────────────────────────
# NEVER hardcode your API key in source code.
#
# HOW TO SET YOUR KEY (pick one):
#
# Option A — Streamlit Cloud (recommended for deployment):
#   Go to App Settings → Secrets, then add:
#       GEMINI_API_KEY = "AIzaSyAos8tFpVwhKw6IhE12TgKz7xPSASIxvLE"
#
# Option B — Local development:
#   Create a file at  .streamlit/secrets.toml  containing:
#       GEMINI_API_KEY = "AIzaSyAos8tFpVwhKw6IhE12TgKz7xPSASIxvLE"
#
# Option C — Environment variable (e.g. Docker / server):
#   export GEMINI_API_KEY="AIzaSyAos8tFpVwhKw6IhE12TgKz7xPSASIxvLE"
#   The os.environ fallback below handles this automatically.

import os

def load_api_key() -> str:
    # 1. Try Streamlit Secrets (cloud / local secrets.toml)
    try:
        key = st.secrets["AIzaSyAos8tFpVwhKw6IhE12TgKz7xPSASIxvLE"]
        if key:
            return key
    except (KeyError, FileNotFoundError):
        pass

    # 2. Fall back to OS environment variable
    key = os.environ.get("AIzaSyAos8tFpVwhKw6IhE12TgKz7xPSASIxvLE", "")
    if key:
        return key

    # 3. No key found — stop with a clear message
    st.error(
        "⚠️ **Gemini API key not found.**\n\n"
        "Add it to `.streamlit/secrets.toml`:\n"
        "```toml\nGEMINI_API_KEY = \"your-key-here\"\n```\n"
        "or set the environment variable `GEMINI_API_KEY`."
    )
    st.stop()

API_KEY = load_api_key()
MODEL   = "gemini-2.0-flash"
KB_FILE = "Islamic Law of Inheritance.docx"

# ── Knowledge base ────────────────────────────────────────────────────────────
@st.cache_data
def load_kb():
    try:
        document = Document(KB_FILE)
        kb = "\n".join(para.text for para in document.paragraphs)
        return kb, None
    except FileNotFoundError:
        return None, f"❌ File not found: '{KB_FILE}'. Make sure it is committed to your repo."
    except Exception:
        return None, f"❌ Error reading KB:\n```\n{traceback.format_exc()}\n```"

def get_system_prompt(kb: str) -> str:
    return (
        "You are MISHKATH HELP executive. Your job is to provide answers to the customers. "
        "You should answer them politely. "
        "If there is any question outside the Knowledge Base, say you do not have that information. "
        "Only refer to the Knowledge Base and provide the response.\n\n"
        f"Knowledge Base:\n{kb}"
    )

# ── Chat ──────────────────────────────────────────────────────────────────────
def send_message(history: list, user_input: str, kb: str):
    try:
        client = genai.Client(api_key=API_KEY)

        messages = []
        for msg in history:
            role = "model" if msg["role"] == "assistant" else "user"
            messages.append({"role": role, "parts": [{"text": msg["content"]}]})
        messages.append({"role": "user", "parts": [{"text": user_input}]})

        response = client.models.generate_content(
            model=MODEL,
            contents=messages,
            config={"system_instruction": get_system_prompt(kb)},
        )
        return response.text, None
    except Exception:
        return None, traceback.format_exc()

# ── UI ────────────────────────────────────────────────────────────────────────
st.title("MISHKATH HELP Chatbot")
st.caption("Ask me anything about Islamic Law of Inheritance")

# Safe sidebar info — shows only that a key is loaded, never the key itself
st.sidebar.markdown("**API Key:** `****` *(loaded securely)*")
st.sidebar.markdown(f"**Model:** `{MODEL}`")

kb, kb_error = load_kb()
if kb_error:
    st.error(kb_error)
    st.stop()
else:
    st.sidebar.success(f"✅ KB loaded ({len(kb):,} chars)")

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
            answer, err = send_message(
                st.session_state.messages[:-1], user_input, kb
            )
        if err:
            st.error(f"**Error:**\n```\n{err}\n```")
        else:
            st.markdown(answer)
            st.session_state.messages.append(
                {"role": "assistant", "content": answer}
            )