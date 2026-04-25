import os

import fitz
from flask import Flask, render_template, request
from google import genai
from werkzeug.utils import secure_filename


app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def extract_text_from_pdf(filepath):
    text = ""

    with fitz.open(filepath) as doc:
        for page in doc:
            text += page.get_text()

    return text.strip()


def summarize_text(text):
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        return "GEMINI_API_KEY is missing. Please add your Gemini API key to your environment variables."

    client = genai.Client(api_key=api_key)
    prompt = f"""
Summarize the following PDF text in simple terms.
Use short paragraphs and bullet points where helpful.

PDF text:
{text[:8000]}
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )

    return response.text or "Gemini did not return a summary. Please try again."


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/upload", methods=["GET", "POST"])
def upload():
    summary = None
    error = None

    if request.method == "POST":
        uploaded_file = request.files.get("file")

        if not uploaded_file or not uploaded_file.filename:
            error = "Please choose a PDF file first."
        elif not uploaded_file.filename.lower().endswith(".pdf"):
            error = "Please upload a PDF file."
        else:
            filename = secure_filename(uploaded_file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            uploaded_file.save(filepath)

            try:
                text = extract_text_from_pdf(filepath)

                if not text:
                    error = "No readable text was found in this PDF."
                else:
                    summary = summarize_text(text)
            except Exception as exc:
                error = f"Something went wrong: {exc}"

    return render_template("upload.html", summary=summary, error=error)


if __name__ == "__main__":
    app.run(debug=True)
