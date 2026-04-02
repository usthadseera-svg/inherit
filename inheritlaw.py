import io
import re
import time
import requests
import streamlit as st
from docx import Document
from docx.oxml.ns import qn
from google import genai
from google.genai import errors as genai_errors

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

DOCX_GITHUB_URL = "https://raw.githubusercontent.com/usthadseera-svg/inherit/main/Islamic%20Law%20of%20Inheritance.docx"

MODELS      = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]
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
# DOCUMENT EXTRACTION  — paragraphs + tables + headings preserved
# ══════════════════════════════════════════════════════════════════════════════

def extract_table_as_markdown(table) -> str:
    """Convert a docx table into a clean markdown table string."""
    rows = []
    for i, row in enumerate(table.rows):
        cells = []
        for cell in row.cells:
            # Clean up cell text: collapse whitespace, strip newlines
            text = " ".join(cell.text.split())
            cells.append(text)
        rows.append("| " + " | ".join(cells) + " |")
        # Add separator after header row
        if i == 0:
            rows.append("|" + "|".join([" --- " for _ in cells]) + "|")
    return "\n".join(rows)


def extract_full_document(doc: Document) -> str:
    """
    Extract all content from a docx in reading order:
    - Headings are marked with # symbols
    - Paragraphs are preserved as-is
    - Tables are converted to clean markdown tables
    - Empty lines are collapsed
    """
    parts = []

    # Walk the document body in XML order so tables and paragraphs
    # stay in their correct reading positions
    body = doc.element.body
    for child in body.iterchildren():

        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

        # ── Paragraph ─────────────────────────────────────────────────────
        if tag == "p":
            from docx.text.paragraph import Paragraph as DocxParagraph
            para = DocxParagraph(child, doc)
            text = para.text.strip()
            if not text:
                continue

            style = para.style.name if para.style else ""

            # Mark headings with markdown # for clear structure
            if "Heading 1" in style:
                parts.append(f"\n# {text}\n")
            elif "Heading 2" in style:
                parts.append(f"\n## {text}\n")
            elif "Heading 3" in style:
                parts.append(f"\n### {text}\n")
            else:
                parts.append(text)

        # ── Table ──────────────────────────────────────────────────────────
        elif tag == "tbl":
            from docx.table import Table as DocxTable
            table = DocxTable(child, doc)
            md_table = extract_table_as_markdown(table)
            parts.append(f"\n[TABLE]\n{md_table}\n[/TABLE]\n")

    return "\n".join(parts)


@st.cache_resource(show_spinner="📖 Loading knowledge base from GitHub…")
def load_document_text() -> str:
    """Download .docx from GitHub and extract full structured text."""

    # Validate URL
    if "YOUR_USERNAME" in DOCX_GITHUB_URL or "YOUR_REPO" in DOCX_GITHUB_URL:
        st.error("❌ Replace `DOCX_GITHUB_URL` with your actual raw GitHub URL.")
        st.stop()

    if "github.com" in DOCX_GITHUB_URL and "raw.githubusercontent.com" not in DOCX_GITHUB_URL:
        fixed = DOCX_GITHUB_URL.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
        st.error(
            f"❌ Wrong URL type. Use the raw URL instead:\n\n`{fixed}`"
        )
        st.stop()

    # Fetch file
    try:
        response = requests.get(DOCX_GITHUB_URL, timeout=30)
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        st.error(f"❌ GitHub error: {e}\n\nCheck the URL and that the repo is public.")
        st.stop()
    except requests.exceptions.RequestException as e:
        st.error(f"❌ Network error: {e}")
        st.stop()

    # Validate it's actually a ZIP/docx (starts with PK)
    if response.content[:4] != b"PK\x03\x04":
        snippet = response.content[:200].decode("utf-8", errors="replace")
        st.error(
            f"❌ URL returned HTML instead of a .docx file.\n\n"
            f"Use the raw URL (starts with `raw.githubusercontent.com`).\n\n"
            f"First bytes: `{snippet[:80]}`"
        )
        st.stop()

    # Parse and extract
    try:
        doc  = Document(io.BytesIO(response.content))
        text = extract_full_document(doc)
    except Exception as e:
        st.error(f"❌ Failed to parse .docx: {e}")
        st.stop()

    if not text.strip():
        st.error("❌ Document loaded but contains no readable text.")
        st.stop()

    return text


# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT  — structured reasoning + calculation instructions
# ══════════════════════════════════════════════════════════════════════════════

def get_system_prompt(doc_text: str) -> str:
    return f"""You are an expert Islamic Inheritance Law assistant with deep knowledge of Fara'id (Islamic inheritance law).

════════════════════════════════════════════════════════
KNOWLEDGE SOURCE
════════════════════════════════════════════════════════
You must answer ONLY from the document below.
Do NOT use outside knowledge. If a topic is not in the document, say:
"This topic is not covered in the provided Islamic Law of Inheritance document."

════════════════════════════════════════════════════════
HOW TO HANDLE COMPLEX QUESTIONS
════════════════════════════════════════════════════════

1. IDENTIFYING HEIRS
   - List which heirs are present in the scenario
   - State whether they are Quranic sharers (Ashabul Furud) or residuaries (Asaba)
   - Note any heirs who are blocked (mahjub) and by whom

2. READING TABLES FROM THE DOCUMENT
   - Tables in the document are marked [TABLE]...[/TABLE]
   - Read them carefully — they contain heir shares under different conditions
   - Cross-reference the correct column based on who else is present

3. SHARE CALCULATIONS — follow these steps:
   STEP 1: Identify each heir's fractional share from the document tables
   STEP 2: Find the lowest common denominator (LCD) of all shares
   STEP 3: Convert each share to the LCD
   STEP 4: Check if shares add up to the estate (= 1 whole):
           - If they equal 1 → distribute normally
           - If less than 1 → remainder goes to residuary (Asaba)
           - If more than 1 → apply Awl (proportional reduction)
   STEP 5: Calculate each heir's amount from the total estate value
   STEP 6: Show the full working clearly

4. SHOW YOUR REASONING
   - Always show step-by-step working for calculations
   - Present results in a clear table:
     | Heir | Relation | Share | Fraction | Amount |
   - State the rule or condition from the document that applies
   - If Awl or Radd applies, explain why and recalculate

5. FORMATTING
   - Use clear section headers
   - Show fractions as: 1/2, 1/4, 1/6, 1/8 etc.
   - Show calculations explicitly: e.g. "1/6 of 90,000 = 15,000"
   - Always remind users to consult a qualified Islamic scholar for personal matters

════════════════════════════════════════════════════════
DOCUMENT CONTENT
════════════════════════════════════════════════════════
{doc_text}
════════════════════════════════════════════════════════
"""


# ══════════════════════════════════════════════════════════════════════════════
# SEND MESSAGE  — retry + fallback
# ══════════════════════════════════════════════════════════════════════════════

def _parse_retry_delay(error_text: str) -> int | None:
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
                    config={
                        "system_instruction": get_system_prompt(doc_text),
                        # Higher token limit for complex calculation responses
                        "max_output_tokens": 4096,
                    },
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
                    st.warning(f"⚠️ Model `{model}` unavailable, trying fallback…")
                    break

                else:
                    st.error(f"Gemini API error ({model}): {e}")
                    st.stop()

    st.error(
        "🚫 All models failed.\n"
        "1. Enable billing → [aistudio.google.com](https://aistudio.google.com)\n"
        "2. Wait ~1 min and retry"
    )
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# STREAMLIT UI
# ══════════════════════════════════════════════════════════════════════════════

st.set_page_config(page_title="Islamic Inheritance Law Assistant", page_icon="☪️")
st.title("☪️ Islamic Law of Inheritance Assistant")
st.caption("Answers and calculations based exclusively on the *Islamic Law of Inheritance* document.")

# Load document
doc_text = load_document_text()

# Count tables extracted
table_count = doc_text.count("[TABLE]")

# Sidebar
with st.sidebar:
    st.markdown("### 📄 Knowledge Base")
    st.success("✅ Document loaded")
    st.caption(f"**Characters:** {len(doc_text):,}")
    st.caption(f"**Tables extracted:** {table_count}")
    st.markdown("---")
    st.markdown("### 💡 Example questions")
    examples = [
        "Who are the Quranic sharers (Ashabul Furud)?",
        "A man dies leaving a wife, 2 daughters and a father. Estate is $90,000. Calculate each share.",
        "What is Awl and when does it apply?",
        "A woman dies leaving a husband, mother, and 2 full brothers. How is the estate divided?",
        "What share does a grandmother get?",
        "Explain the rule of Hajb (blocking) with examples.",
    ]
    for ex in examples:
        if st.button(ex, use_container_width=True, key=ex):
            st.session_state.pending_input = ex
    st.markdown("---")
    st.warning("For personal legal matters, consult a qualified Islamic scholar.")
    if st.button("🗑️ Clear chat"):
        st.session_state.messages = []
        st.rerun()

# Init state
if "messages" not in st.session_state:
    st.session_state.messages: list[dict] = []
if "pending_input" not in st.session_state:
    st.session_state.pending_input = None

# Render history
for msg in st.session_state.messages:
    role = "user" if msg["role"] == "user" else "assistant"
    with st.chat_message(role):
        st.markdown(msg["parts"][0]["text"])

# Handle sidebar button click OR typed input
user_input = st.chat_input("Ask about Islamic inheritance law or enter a calculation scenario…")

if st.session_state.pending_input:
    user_input = st.session_state.pending_input
    st.session_state.pending_input = None

if user_input:
    with st.chat_message("user"):
        st.markdown(user_input)

    st.session_state.messages.append(
        {"role": "user", "parts": [{"text": user_input}]}
    )

    with st.chat_message("assistant"):
        with st.spinner("Analysing document and calculating…"):
            answer = send_message(
                st.session_state.messages[:-1],
                user_input,
                doc_text,
            )
        st.markdown(answer)

    st.session_state.messages.append(
        {"role": "model", "parts": [{"text": answer}]}
    )
