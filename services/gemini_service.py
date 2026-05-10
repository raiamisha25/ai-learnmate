import os
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError

from dotenv import load_dotenv
from google import genai

from utils.errors import friendly_ai_error


load_dotenv()

GEMINI_MODEL = "gemini-1.5-flash"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY missing")
else:
    print("AI LearnMate startup: GEMINI_API_KEY loaded")

try:
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
except Exception:
    client = None


def safe_generate(prompt, timeout_seconds=20):
    """Call Gemini safely and return (text, error_message)."""
    if not client or not GEMINI_API_KEY:
        return None, "AI service is temporarily unavailable. Please check your Gemini API key."

    def call_gemini():
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        return response.text

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(call_gemini)

    try:
        return future.result(timeout=timeout_seconds), None
    except TimeoutError:
        future.cancel()
        return None, "Request timed out. Try again."
    except Exception as exc:
        return None, friendly_ai_error(str(exc))
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def check_gemini_startup():
    if not GEMINI_API_KEY:
        return

    response_text, error = safe_generate("Say OK.", timeout_seconds=8)

    if error:
        print(f"Gemini startup check failed: {error}")
    elif response_text:
        print("Gemini connection successful")


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

