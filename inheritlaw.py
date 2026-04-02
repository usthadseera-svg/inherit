import time
import streamlit as st
from google import genai
from google.genai import errors as genai_errors

# ── Models (current as of April 2026) ─────────────────────────────────────
# gemini-2.5-flash-lite  → fastest, cheapest, good free quota
# gemini-2.5-flash       → best price/performance balance
# gemini-2.5-pro         → most capable (lower free quota)
#
# DO NOT use: gemini-2.0-flash, gemini-1.5-flash, gemini-1.5-pro
# These are deprecated / restricted to existing users only.
MODELS      = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro"]
MAX_RETRIES = 3
RETRY_WAIT  = 15   # seconds to wait on 429 before retrying


# ── Secure API key ─────────────────────────────────────────────────────────
def get_api_key() -> str:
    """Load key from Streamlit secrets — never hardcode it."""
    try:
        key = st.secrets["GEMINI_API_KEY"]
    except (KeyError, FileNotFoundError):
        st.error(
            "⚠️ **API key not found.**\n\n"
            "- **Streamlit Cloud:** go to *Settings → Secrets* and add:\n"
            "  ```\n  GEMINI_API_KEY = \"AIza...\"\n  ```\n"
            "- **Local:** create `.streamlit/secrets.toml` with the same line."
        )
        st.stop()
    if not key or not key.startswith("AIza"):
        st.error("⚠️ API key looks invalid. Check your Streamlit secrets.")
        st.stop()
    return key


@st.cache_resource
def get_client() -> genai.Client:
    return genai.Client(api_key=get_api_key())


# ── System prompt ──────────────────────────────────────────────────────────
def get_system_prompt() -> str:
    return (
        "You are a helpful legal assistant specialising in inheritance law. "
        "Provide clear, structured answers. Always remind users to consult a "
        "qualified lawyer for advice specific to their situation."
    )


# ── Retry delay parser ─────────────────────────────────────────────────────
def _parse_retry_delay(error_text: str) -> int | None:
    import re
    match = re.search(r"retry[^\d]*(\d+)", error_text, re.IGNORECASE)
    return int(match.group(1)) + 2 if match else None


# ── Send with retry + model fallback ──────────────────────────────────────
def send_message(history: list[dict], user_input: str) -> str:
    client   = get_client()
    contents = history + [{"role": "user", "parts": [{"text": user_input}]}]

    for model in MODELS:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config={"system_instruction": get_system_prompt()},
                )
                return response.text   # ✅ success

            except genai_errors.ClientError as e:
                status = getattr(e, "status_code", None) or getattr(e, "code", None)

                # 429 — quota / rate limit: wait then retry
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
                    break   # next model

                # 404 — model deprecated / not available: skip immediately
                elif status == 404:
                    st.warning(f"⚠️ Model `{model}` not available (404), trying fallback…")
                    break   # next model

                # Other errors: surface immediately
                else:
                    st.error(f"Gemini API error ({model}): {e}")
                    st.stop()

    # All models failed
    st.error(
        "🚫 **No working model found.** Try:\n"
        "1. Check available models at [ai.google.dev/gemini-api/docs/models](https://ai.google.dev/gemini-api/docs/models)\n"
        "2. Enable billing → [aistudio.google.com](https://aistudio.google.com)\n"
        "3. Wait ~1 min for quota reset and retry"
    )
    st.stop()


# ── Streamlit UI ───────────────────────────────────────────────────────────
st.set_page_config(page_title="Inheritance Law Assistant", page_icon="⚖️")
st.title("⚖️ Inheritance Law Assistant")

with st.sidebar:
    st.markdown("### ⚙️ Model Info")
    st.caption(f"**Primary:** `{MODELS[0]}`")
    st.caption(f"**Fallbacks:** {', '.join(f'`{m}`' for m in MODELS[1:])}")
    st.divider()
    st.markdown(
        "Models update frequently. Check the latest at "
        "[ai.google.dev](https://ai.google.dev/gemini-api/docs/models)."
    )
    if st.button("🗑️ Clear chat"):
        st.session_state.messages = []
        st.rerun()

# Initialise chat history
if "messages" not in st.session_state:
    st.session_state.messages: list[dict] = []

# Render history
for msg in st.session_state.messages:
    role = "user" if msg["role"] == "user" else "assistant"
    with st.chat_message(role):
        st.markdown(msg["parts"][0]["text"])

# Chat input
if user_input := st.chat_input("Ask about inheritance law…"):
    with st.chat_message("user"):
        st.markdown(user_input)

    st.session_state.messages.append(
        {"role": "user", "parts": [{"text": user_input}]}
    )

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            answer = send_message(st.session_state.messages[:-1], user_input)
        st.markdown(answer)

    st.session_state.messages.append(
        {"role": "model", "parts": [{"text": answer}]}
    )
