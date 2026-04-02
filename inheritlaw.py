import io
import time
import requests
import streamlit as st
from docx import Document
from google import genai
from google.genai import errors as genai_errors

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

# 🔧 Replace with your actual GitHub raw URL, e.g.:
# https://github.com/usthadseera-svg/inherit/blob/main/Islamic%20Law%20of%20Inheritance.docx
DOCX_GITHUB_URL = "https://github.com/usthadseera-svg/inherit/blob/main/Islamic%20Law%20of%20Inheritance.docx"

# Current Gemini models (April 2026) — ordered by quota availability
MODELS      = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro"]
MAX_RETRIES = 3
RETRY_WAIT  = 15   # seconds to wait on 429


# ══════════════════════════════════════════════════════════════════════════════
# SECURE API KEY
# ══════════════════════════════════════════════════════════════════════════════

def get_api_key() -> str:
    """Load key from Streamlit secrets — never hardcode."""
    try:
        key = st.secrets["GEMINI_API_KEY"]
    except (KeyError, FileNotFoundError):
        st.error(
            "⚠️ **API key not found.**\n\n"
            "Add to Streamlit secrets:\n```\nGEMINI_API_KEY = \"AIza...\"\n```"
        )
        st.stop()
    if not key or not key.startswith("AIza"):
        st.error("⚠️ API key looks invalid. Check your Streamlit secrets.")
        st.stop()
    return key


@st.cache_resource
def get_client() -> genai.Client:
    return genai.Client(api_key=get_api_key())


# ══════════════════════════════════════════════════════════════════════════════
# LOAD DOCUMENT FROM GITHUB  (cached so it's only fetched once per session)
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner="📖 Loading knowledge base from GitHub…")
def load_document_text() -> str:
    """
    Download the .docx from GitHub and extract all paragraph text.
    Raises a clear error if the file cannot be fetched.
    """
    try:
        response = requests.get(DOCX_GITHUB_URL, timeout=30)
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        st.error(
            f"❌ Could not fetch the document from GitHub ({e}).\n\n"
            "Check that `DOCX_GITHUB_URL` is correct and the file is publicly accessible."
        )
        st.stop()
    except requests.exceptions.RequestException as e:
        st.error(f"❌ Network error while fetching document: {e}")
        st.stop()

    doc  = Document(io.BytesIO(response.content))
    text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    if not text:
        st.error("❌ The document was fetched but contains no readable text.")
        st.stop()

    return text


# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT  — answers ONLY from the document
# ══════════════════════════════════════════════════════════════════════════════

def get_system_prompt(doc_text: str) -> str:
    return f"""You are an Islamic Inheritance Law assistant.

STRICT RULES:
1. You MUST answer ONLY using the document content provided below.
2. Do NOT use any outside knowledge, general legal knowledge, or personal opinions.
3. If the answer is NOT found in the document, respond exactly with:
   "I'm sorry, this topic is not covered in the provided Islamic Law of Inheritance document."
4. Always cite or reference the relevant section/heading from the document when answering.
5. Keep answers clear, structured, and professional.
6. Always remind users to consult a qualified Islamic scholar or lawyer for personal legal matters.

════════════════════════════════════════
DOCUMENT CONTENT (Islamic Law of Inheritance):
════════════════════════════════════════
{doc_text}
════════════════════════════════════════
"""


# ══════════════════════════════════════════════════════════════════════════════
# SEND MESSAGE  — with retry + model fallback
# ══════════════════════════════════════════════════════════════════════════════

def _parse_retry_delay(error_text: str) -> int | None:
    import re
    match = re.search(r"retry[^\d]*(\d+)", error_text, re.IGNORECASE)
    return int(match.group(1)) + 2 if match else None


def send_message(history: list[dict], user_input: str, doc_text: str) -> str:
    client   = get_client()
    contents = history + [{"role": "user", "parts": [{"text": user_input}]}]

    for model in MODELS:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config={"system_instruction": get_system_prompt(doc_text)},
                )
                return response.text   # ✅ success

            except genai_errors.ClientError as e:
                status = getattr(e, "status_code", None) or getattr(e, "code", None)

                if status == 429:
                    wait = _parse_retry_delay(str(e)) or RETRY_WAIT
                    if attempt < MAX_RETRIES:
                        st.warning(
                            f"⏳ Rate limit on `{model}` "
                            f"(attempt {attempt}/{MAX_RETRIES}). "
                            f"Retrying in {wait}s…"
                        )
                        time.sleep(wait)
                        continue
                    st.warning(f"⚠️ Quota exhausted on `{model}`, trying fallback…")
                    break

                elif status == 404:
                    st.warning(f"⚠️ Model `{model}` unavailable (404), trying fallback…")
                    break

                else:
                    st.error(f"Gemini API error ({model}): {e}")
                    st.stop()

    st.error(
        "🚫 **All models failed.** Try:\n"
        "1. Enable billing → [aistudio.google.com](https://aistudio.google.com)\n"
        "2. Wait ~1 min for quota reset\n"
        "3. Check models → [ai.google.dev/gemini-api/docs/models](https://ai.google.dev/gemini-api/docs/models)"
    )
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# STREAMLIT UI
# ══════════════════════════════════════════════════════════════════════════════

st.set_page_config(page_title="Islamic Inheritance Law Assistant", page_icon="☪️")
st.title("☪️ Islamic Law of Inheritance Assistant")
st.caption("Answers are based exclusively on the *Islamic Law of Inheritance* document.")

# Load document once
doc_text = load_document_text()

# Sidebar
with st.sidebar:
    st.markdown("### 📄 Knowledge Base")
    st.success("✅ Document loaded from GitHub")
    st.caption(f"**Characters loaded:** {len(doc_text):,}")
    st.markdown("---")
    st.markdown("### ⚙️ Models")
    st.caption(f"**Primary:** `{MODELS[0]}`")
    st.caption(f"**Fallbacks:** {', '.join(f'`{m}`' for m in MODELS[1:])}")
    st.markdown("---")
    st.warning(
        "⚠️ This chatbot only answers from the loaded document. "
        "For personal legal matters, consult a qualified Islamic scholar or lawyer."
    )
    if st.button("🗑️ Clear chat"):
        st.session_state.messages = []
        st.rerun()

# Init chat history
if "messages" not in st.session_state:
    st.session_state.messages: list[dict] = []

# Render history
for msg in st.session_state.messages:
    role = "user" if msg["role"] == "user" else "assistant"
    with st.chat_message(role):
        st.markdown(msg["parts"][0]["text"])

# Chat input
if user_input := st.chat_input("Ask about Islamic inheritance law…"):
    with st.chat_message("user"):
        st.markdown(user_input)

    st.session_state.messages.append(
        {"role": "user", "parts": [{"text": user_input}]}
    )

    with st.chat_message("assistant"):
        with st.spinner("Searching document…"):
            answer = send_message(
                st.session_state.messages[:-1],
                user_input,
                doc_text,
            )
        st.markdown(answer)

    st.session_state.messages.append(
        {"role": "model", "parts": [{"text": answer}]}
    )
