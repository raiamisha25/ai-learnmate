import os
import time

from dotenv import load_dotenv
from groq import Groq

from utils.errors import friendly_ai_error


load_dotenv()

GROQ_MODEL = os.getenv("GROQ_MODEL", "llama3-70b-8192")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()


def mask_api_key(api_key):
    if not api_key:
        return "missing"

    return f"{api_key[:6]}******"


print(f"GROQ_API_KEY loaded: {mask_api_key(GROQ_API_KEY)}")

try:
    client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
    if client:
        print("Groq client initialized successfully.")
    else:
        print("Groq client not initialized because GROQ_API_KEY is missing.")
except Exception as exc:
    print(f"Groq initialization failed: {exc}")
    client = None


def safe_groq_generate(system_prompt, user_prompt, timeout_seconds=25, max_tokens=1800):
    """Call Groq safely and return (text, error_message)."""
    from utils.topic_validator import logger

    if not client or not GROQ_API_KEY:
        return None, "Invalid Groq API key. Please check your GROQ_API_KEY."

    last_error = None

    for attempt in range(1, 4):
        try:
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=max_tokens,
                timeout=timeout_seconds,
            )
            text = response.choices[0].message.content

            if text and text.strip():
                logger.info(f"[AI RESPONSE] Received response (length: {len(text)}):\n{text}")
                return text, None

            last_error = "Empty AI response"
            print(f"Groq call attempt {attempt} failed: {last_error}")
        except Exception as exc:
            last_error = str(exc)
            print(f"Groq call attempt {attempt} failed: {exc}")

        if attempt < 3:
            time.sleep(0.5 * attempt)

    return None, friendly_ai_error(last_error)


def check_groq_startup():
    if not GROQ_API_KEY:
        print("[ERROR] Groq API key missing")
        return

    response_text, error = safe_groq_generate(
        "Reply with exactly OK.",
        "Say OK.",
        timeout_seconds=8,
        max_tokens=10,
    )

    if error:
        print(f"[ERROR] Groq startup check failed: {error}")
    elif response_text:
        print("[OK] Groq connected")
