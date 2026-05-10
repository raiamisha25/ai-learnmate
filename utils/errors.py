class AppError(Exception):
    """Friendly error that can be shown safely on a page."""

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def friendly_ai_error(error_text):
    text = (error_text or "").lower()

    if "timeout" in text or "timed out" in text:
        return "Request timed out. Try again."
    if (
        "api key" in text
        or "expired" in text
        or "permission" in text
        or "unauthorized" in text
        or "authentication" in text
    ):
        return "AI service is temporarily unavailable. Please check your Gemini API key."
    if "quota" in text or "resource_exhausted" in text or "429" in text:
        return "AI service quota exceeded. Please try again later."
    if (
        "network" in text
        or "connection" in text
        or "connect" in text
        or "dns" in text
        or "resolve" in text
        or "ssl" in text
    ):
        return "Could not connect to AI service."

    return "AI service is temporarily unavailable. Please check your Gemini API key."

