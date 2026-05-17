import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError

from dotenv import load_dotenv
from google import genai

from utils.errors import friendly_ai_error


load_dotenv()

GEMINI_MODEL = "gemini-1.5-flash"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()


def mask_api_key(api_key):
    if not api_key:
        return "missing"

    return f"{api_key[:6]}******"


print(f"GEMINI_API_KEY loaded: {mask_api_key(GEMINI_API_KEY)}")

try:
    client = genai.Client(api_key=GEMINI_API_KEY)
    print("Gemini client initialized successfully.")
except Exception as exc:
    print(f"Gemini initialization failed: {exc}")
    client = None


def safe_generate(prompt, timeout_seconds=20):
    """Call Gemini safely and return (text, error_message)."""
    if not client or not GEMINI_API_KEY:
        return None, "Invalid Gemini API key. Please check your GEMINI_API_KEY."

    def call_gemini():
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        return response.text

    last_error = None

    for attempt in range(1, 4):
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(call_gemini)

        try:
            response_text = future.result(timeout=timeout_seconds)

            if not response_text or not response_text.strip():
                last_error = "Empty AI response"
                print(f"Gemini call attempt {attempt} failed: {last_error}")
            else:
                return response_text, None
        except TimeoutError:
            future.cancel()
            last_error = "Gemini request timed out"
            print(f"Gemini call attempt {attempt} failed: {last_error}")
        except Exception as exc:
            last_error = str(exc)
            print(f"Gemini call attempt {attempt} failed: {exc}")
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        if attempt < 3:
            time.sleep(0.5 * attempt)

    return None, friendly_ai_error(last_error)


def check_gemini_startup():
    if not GEMINI_API_KEY:
        print("[ERROR] Gemini API key missing")
        return

    response_text, error = safe_generate("Say OK.", timeout_seconds=8)

    if error:
        print(f"[ERROR] Gemini startup check failed: {error}")
    elif response_text:
        print("[OK] Gemini connected")


def clean_json_text(text):
    text = (text or "").strip()

    if text.startswith("```"):
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"^```\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    start = text.find("[")
    end = text.rfind("]")

    if start != -1 and end != -1:
        return text[start : end + 1]

    return text


def clean_json_object_text(text):
    text = (text or "").strip()

    if text.startswith("```"):
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"^```\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1:
        return text[start : end + 1]

    return text
