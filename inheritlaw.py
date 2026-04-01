import streamlit as st
from google import genai
from docx import Document
import traceback

# ── Secure API Key Handling ───────────────────────────────────────────────
# Option 1: Streamlit Cloud Secrets (RECOMMENDED for deployment)
# Set this in: Streamlit Cloud → Your App → Settings → Secrets
# Format in secrets.toml or Secrets UI:
#   GEMINI_API_KEY = "your-actual-key-here"

# Option 2: Local development with .env file (NEVER commit .env to git)
# Create .env file with: GEMINI_API_KEY=your-actual-key-here
# Add .env to your .gitignore!

try:
    # Try Streamlit secrets first (production)
    API_KEY = st.secrets["AIzaSyAos8tFpVwhKw6IhE12TgKz7xPSASIxvLE"]
except (KeyError, FileNotFoundError):
    # Fallback for local development only
    import os
    API_KEY = os.getenv("GEMINI_API_KEY")
    
    if not API_KEY:
        st.error("⚠️ No API key found. Set GEMINI_API_KEY in Streamlit Secrets or environment variables.")
        st.stop()

MODEL   = "gemini-2.0-flash"
KB_FILE = "Islamic Law of Inheritance.docx"

@st.cache_data
def load_kb():
    try:
        document = Document(KB_FILE)
        kb = "\n".join([p.text for p in document.paragraphs])
        return kb, None
    except FileNotFoundError:
        return None, f"❌ File not found: '{KB_FILE}'. Ensure it's in your repo."
    except Exception:
        return None, f"❌ Error reading KB:\n```\n{traceback.format_exc()}\n```"

def get_system_prompt(kb):
    return f"""You are MISHKATH HELP executive. Provide polite, accurate answers based ONLY on the Knowledge Base below. If information is not in the KB, state clearly that you don't have that information.

Knowledge Base:
{kb}"""

def send_message(history, user_input, kb):
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

# ── UI ───────────────────────────────────────────────────────────────────────

st.title("MISHKATH HELP Chatbot")
st.caption("Ask me anything about Islamic Law of Inheritance")

# Safe status display (only shows key is configured, not the value)
key_status = "✅ Configured" if API_KEY else "❌ Missing"
st.sidebar.markdown(f"**API Key:** `{key_status}`")
st.sidebar.markdown(f"**Model:** `{MODEL}`")

kb, kb_error = load_kb()
if kb_error:
    st.error(kb_error)
    st.stop()
else:
    st.sidebar.success(f"✅ KB loaded ({len(kb)} chars)")

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
            answer, err = send_message(st.session_state.messages[:-1], user_input, kb)
        if err:
            st.error(f"**Error:**\n```\n{err}\n```")
        else:
            st.markdown(answer)
            st.session_state.messages.append({"role": "assistant", "content": answer})