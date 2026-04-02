import streamlit as st
from google import genai

# ── 1. Secure API key loading ──────────────────────────────────────────────
# On Streamlit Cloud: set GEMINI_API_KEY in App Settings → Secrets
# Locally: add to .streamlit/secrets.toml  →  GEMINI_API_KEY = "AIza..."
# NEVER hardcode the key in this file.

def get_api_key() -> str:
    """Load API key from Streamlit secrets with a clear error if missing."""
    try:
        key = st.secrets["GEMINI_API_KEY"]
    except (KeyError, FileNotFoundError):
        st.error(
            "⚠️ **API key not found.** "
            "Add `GEMINI_API_KEY = \"your-key\"` to your Streamlit secrets."
        )
        st.stop()

    if not key or not key.startswith("AIza"):
        st.error("⚠️ **API key looks invalid.** Check your Streamlit secrets.")
        st.stop()

    return key


# ── 2. Gemini client (created once per session) ────────────────────────────
@st.cache_resource
def get_client() -> genai.Client:
    return genai.Client(api_key=get_api_key())


MODEL = "gemini-2.0-flash"   # change to gemini-1.5-pro etc. as needed


# ── 3. System prompt ───────────────────────────────────────────────────────
def get_system_prompt() -> str:
    return (
        "You are a helpful legal assistant specialising in inheritance law. "
        "Provide clear, structured answers. Always remind users to consult a "
        "qualified lawyer for advice specific to their situation."
    )


# ── 4. Chat helper ─────────────────────────────────────────────────────────
def send_message(history: list[dict], user_input: str) -> str:
    """
    Build a contents list from history + new user message and call Gemini.
    history = [{"role": "user"|"model", "parts": [{"text": "..."}]}, ...]
    """
    client = get_client()

    # Append the new user turn
    contents = history + [{"role": "user", "parts": [{"text": user_input}]}]

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config={"system_instruction": get_system_prompt()},
        )
        return response.text

    except genai.errors.ClientError as e:
        # Surface the real error message in the UI (safe — secrets are not in it)
        st.error(f"Gemini API error: {e}")
        st.stop()


# ── 5. Streamlit UI ────────────────────────────────────────────────────────
st.set_page_config(page_title="Inheritance Law Assistant", page_icon="⚖️")
st.title("⚖️ Inheritance Law Assistant")

# Initialise chat history in session state
if "messages" not in st.session_state:
    st.session_state.messages: list[dict] = []

# Render existing messages
for msg in st.session_state.messages:
    role = "user" if msg["role"] == "user" else "assistant"
    with st.chat_message(role):
        st.markdown(msg["parts"][0]["text"])

# Chat input
if user_input := st.chat_input("Ask about inheritance law…"):
    # Show user message immediately
    with st.chat_message("user"):
        st.markdown(user_input)

    # Store user turn (before sending so history is complete)
    st.session_state.messages.append(
        {"role": "user", "parts": [{"text": user_input}]}
    )

    # Get model response (pass history EXCLUDING the turn we just added,
    # because send_message appends it internally)
    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            answer = send_message(st.session_state.messages[:-1], user_input)
        st.markdown(answer)

    # Store model turn
    st.session_state.messages.append(
        {"role": "model", "parts": [{"text": answer}]}
    )