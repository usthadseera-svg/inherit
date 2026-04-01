import streamlit as st
from google import genai
from docx import Document
import traceback

# ── Read API key from Streamlit Secrets (more secure & avoids key issues) ────
# In Streamlit Cloud: go to App Settings → Secrets and add:
#   GEMINI_API_KEY = "AIzaSyBmxAqsiBQ7AdRpi3OYCFqE9FRVKufm4fk"
# Fallback to hardcoded key if secret not set
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    API_KEY = "AIzaSyBmxAqsiBQ7AdRpi3OYCFqE9FRVKufm4fk"

MODEL   = "gemini-2.0-flash"   # changed from 2.5-flash (more widely available)
KB_FILE = "Islamic Law of Inheritance.docx"

@st.cache_data
def load_kb():
    try:
        document = Document(KB_FILE)
        kb = ""
        for para in document.paragraphs:
            kb += para.text + "\n"
        return kb, None
    except FileNotFoundError:
        return None, f"❌ File not found: '{KB_FILE}'. Make sure it is committed to your GitHub repo."
    except Exception:
        return None, f"❌ Error reading KB:\n```\n{traceback.format_exc()}\n```"

def get_system_prompt(kb):
    return f"""You are MISHKATH HELP executive. Your job is to provide answers to the customers. You should answer them in polite.
If there is any question out of the KB say you did not have that info. Only refer the KB and provide the response.
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
        return None, traceback.format_exc()   # show full real error in UI

# ── UI ────────────────────────────────────────────────────────────────────────

st.title("MISHKATH HELP Chatbot")
st.caption("Ask me anything about Islamic Law of Inheritance")

# Show API key status (first 8 chars only, safe to display)
st.sidebar.markdown(f"**API Key:** `{API_KEY[:8]}...`")
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
            st.error(f"**Real error (unredacted):**\n```\n{err}\n```")
        else:
            st.markdown(answer)
            st.session_state.messages.append({"role": "assistant", "content": answer})
