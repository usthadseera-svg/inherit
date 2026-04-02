import io
import time
import requests
import streamlit as st
from docx import Document
from google import genai
from google.genai import errors as genai_errors

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION  —  ⚠️ Must be a RAW GitHub URL (not the normal page URL)
#
# ✅ CORRECT raw URL format:
#    https://raw.githubusercontent.com/usthadseera-svg/inherit/main/Islamic%20Law%20of%20Inheritance.docx
# 
# ❌ WRONG (normal GitHub page URL — returns HTML, not the file):
#    https://github.com/USERNAME/REPO/blob/main/filename.docx
#
# How to get the raw URL:
#   1. Open your repo on GitHub
#   2. Click the file "Islamic Law of Inheritance.docx"
#   3. Click the "Raw" button (or "Download raw file")
#   4. Copy the URL from your browser address bar
# ══════════════════════════════════════════════════════════════════════════════

DOCX_GITHUB_URL = "https://raw.githubusercontent.com/usthadseera-svg/inherit/main/Islamic%20Law%20of%20Inheritance.docx"

MODELS      = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro"]
MAX_RETRIES = 3
RETRY_WAIT  = 15


# ══════════════════════════════════════════════════════════════════════════════
# SECURE API KEY
# ══════════════════════════════════════════════════════════════════════════════

def get_api_key() -> str:
    try:
        key = st.secrets["GEMINI_API_KEY"]
    except (KeyError, FileNotFoundError):
        st.error("⚠️ Add `GEMINI_API_KEY` to your Streamlit secrets.")
        st.stop()
    if not key or not key.startswith("AIza"):
        st.error("⚠️ API key looks invalid.")
        st.stop()
    return key


@st.cache_resource
def get_client() -> genai.Client:
    return genai.Client(api_key=get_api_key())


# ══════════════════════════════════════════════════════════════════════════════
# LOAD DOCUMENT FROM GITHUB
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner="📖 Loading knowledge base from GitHub…")
def load_document_text() -> str:

    # ── Step 1: Catch placeholder URL ─────────────────────────────────────
    if "YOUR_USERNAME" in DOCX_GITHUB_URL or "YOUR_REPO" in DOCX_GITHUB_URL:
        st.error(
            "❌ **DOCX_GITHUB_URL is still a placeholder.**\n\n"
            "Open `inheritlaw.py` and replace `DOCX_GITHUB_URL` with your actual raw GitHub URL.\n\n"
            "**Correct format:**\n"
            "`https://raw.githubusercontent.com/USERNAME/REPO/BRANCH/Islamic%20Law%20of%20Inheritance.docx`"
        )
        st.stop()

    # ── Step 2: Catch wrong URL type (blob instead of raw) ─────────────────
    if "github.com" in DOCX_GITHUB_URL and "raw.githubusercontent.com" not in DOCX_GITHUB_URL:
        # Try to auto-fix it for the user
        fixed = (
            DOCX_GITHUB_URL
            .replace("github.com", "raw.githubusercontent.com")
            .replace("/blob/", "/")
        )
        st.error(
            "❌ **Wrong GitHub URL type.**\n\n"
            "You used the normal GitHub page URL. You need the **raw** URL.\n\n"
            f"**Your URL:** `{DOCX_GITHUB_URL}`\n\n"
            f"**Try this instead:** `{fixed}`\n\n"
            "Or: open the file on GitHub → click **Raw** → copy the URL."
        )
        st.stop()

    # ── Step 3: Fetch the file ─────────────────────────────────────────────
    try:
        response = requests.get(DOCX_GITHUB_URL, timeout=30)
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        st.error(
            f"❌ GitHub returned an error: **{e}**\n\n"
            "Check that:\n"
            "- The URL is correct\n"
            "- The repository is **public** (private repos need auth)\n"
            "- The branch name is correct (`main` vs `master`)\n"
            f"\nURL used: `{DOCX_GITHUB_URL}`"
        )
        st.stop()
    except requests.exceptions.RequestException as e:
        st.error(f"❌ Network error: {e}")
        st.stop()

    # ── Step 4: Validate we got a real .docx (ZIP), not HTML ──────────────
    content_type = response.headers.get("Content-Type", "")
    first_bytes  = response.content[:4]

    # .docx files are ZIP archives — they start with PK\x03\x04
    is_zip = first_bytes == b"PK\x03\x04"

    if not is_zip:
        # Decode a snippet to show the user what was actually returned
        snippet = response.content[:300].decode("utf-8", errors="replace")
        st.error(
            "❌ **The URL did not return a .docx file.**\n\n"
            f"Content-Type received: `{content_type}`\n\n"
            "The server returned HTML or something else instead of the document. "
            "This usually means the URL is the GitHub **page** URL, not the **raw** file URL.\n\n"
            "**How to fix:**\n"
            "1. Go to your file on GitHub\n"
            "2. Click the **Raw** button\n"
            "3. Copy the URL — it should start with `https://raw.githubusercontent.com/`\n\n"
            f"**First 300 bytes received:**\n```\n{snippet}\n```"
        )
        st.stop()

    # ── Step 5: Parse the .docx ────────────────────────────────────────────
    try:
        doc  = Document(io.BytesIO(response.content))
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        st.error(f"❌ Failed to parse the .docx file: {e}")
        st.stop()

    if not text.strip():
        st.error("❌ The document was loaded but contains no readable text.")
        st.stop()

    return text


# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT
# ══════════════════════════════════════════════════════════════════════════════

def get_system_prompt(doc_text: str) -> str:
    return f"""You are an Islamic Inheritance Law assistant.

STRICT RULES:
1. Answer ONLY using the document content provided below.
2. Do NOT use outside knowledge, general legal knowledge, or personal opinions.
3. If the answer is NOT in the document, respond exactly:
   "I'm sorry, this topic is not covered in the provided Islamic Law of Inheritance document."
4. Always reference the relevant section or heading from the document.
5. Keep answers clear, structured, and professional.
6. Always remind users to consult a qualified Islamic scholar or lawyer for personal matters.

════════════════════════════════════
DOCUMENT: Islamic Law of Inheritance
════════════════════════════════════
{doc_text}
════════════════════════════════════
"""


# ══════════════════════════════════════════════════════════════════════════════
# SEND MESSAGE  — retry + model fallback
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
                return response.text

            except genai_errors.ClientError as e:
                status = getattr(e, "status_code", None) or getattr(e, "code", None)

                if status == 429:
                    wait = _parse_retry_delay(str(e)) or RETRY_WAIT
                    if attempt < MAX_RETRIES:
                        st.warning(f"⏳ Rate limit on `{model}` (attempt {attempt}/{MAX_RETRIES}). Retrying in {wait}s…")
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
        "2. Wait ~1 min and retry\n"
        "3. Check models → [ai.google.dev/gemini-api/docs/models](https://ai.google.dev/gemini-api/docs/models)"
    )
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# STREAMLIT UI
# ══════════════════════════════════════════════════════════════════════════════

st.set_page_config(page_title="Islamic Inheritance Law Assistant", page_icon="☪️")
st.title("☪️ Islamic Law of Inheritance Assistant")
st.caption("Answers sourced exclusively from the *Islamic Law of Inheritance* document.")

doc_text = load_document_text()

with st.sidebar:
    st.markdown("### 📄 Knowledge Base")
    st.success("✅ Document loaded successfully")
    st.caption(f"**Characters:** {len(doc_text):,}")
    st.markdown("---")
    st.markdown("### ⚙️ Models")
    st.caption(f"**Primary:** `{MODELS[0]}`")
    st.caption(f"**Fallbacks:** {', '.join(f'`{m}`' for m in MODELS[1:])}")
    st.markdown("---")
    st.warning("For personal legal matters, consult a qualified Islamic scholar or lawyer.")
    if st.button("🗑️ Clear chat"):
        st.session_state.messages = []
        st.rerun()

if "messages" not in st.session_state:
    st.session_state.messages: list[dict] = []

for msg in st.session_state.messages:
    role = "user" if msg["role"] == "user" else "assistant"
    with st.chat_message(role):
        st.markdown(msg["parts"][0]["text"])

if user_input := st.chat_input("Ask about Islamic inheritance law…"):
    with st.chat_message("user"):
        st.markdown(user_input)

    st.session_state.messages.append(
        {"role": "user", "parts": [{"text": user_input}]}
    )

    with st.chat_message("assistant"):
        with st.spinner("Searching document…"):
            answer = send_message(st.session_state.messages[:-1], user_input, doc_text)
        st.markdown(answer)

    st.session_state.messages.append(
        {"role": "model", "parts": [{"text": answer}]}
    )
