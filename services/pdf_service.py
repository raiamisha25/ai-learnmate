import fitz

from utils.errors import AppError


def extract_text_from_pdf(filepath):
    """Extract readable text from a PDF file."""
    try:
        text = ""
        with fitz.open(filepath) as doc:
            for page in doc:
                text += page.get_text()
    except Exception as exc:
        raise AppError("This PDF could not be read. Please try another file.") from exc

    text = text.strip()

    if not text:
        raise AppError("No readable text was found in this PDF.")

    return text

