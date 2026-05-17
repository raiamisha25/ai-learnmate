class AppError(Exception):
    """Friendly error that can be shown safely on a page."""

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def friendly_ai_error(error_text):
    text = (error_text or "").lower()

    if "timeout" in text or "timed out" in text:
        return "Network timeout while contacting Gemini. Please try again."
    if (
        "api key" in text
        or "expired" in text
        or "permission" in text
        or "unauthorized" in text
        or "authentication" in text
        or "invalid_argument" in text
        or "400" in text
        or "403" in text
    ):
        return "Invalid Gemini API key. Please check your GEMINI_API_KEY."
    if "quota" in text or "resource_exhausted" in text or "429" in text:
        return "Gemini quota exceeded. Please try again later."
    if (
        "network" in text
        or "connection" in text
        or "connect" in text
        or "dns" in text
        or "resolve" in text
        or "ssl" in text
    ):
        return "Could not connect to Gemini. Please check your internet connection."
    if "empty" in text or "none" in text:
        return "Gemini returned an empty response. Please try again."
    if "service unavailable" in text or "503" in text or "unavailable" in text:
        return "Gemini service is unavailable right now. Please try again soon."

    return "AI service unavailable. Please try again."
