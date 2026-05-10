import os

from flask import redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from models.state import latest_quiz, latest_result, neo4j_status
from services.ambiguity_service import check_topic_ambiguity
from services.neo4j_service import fetch_graph_from_neo4j, fetch_topic_suggestions
from services.pdf_service import extract_text_from_pdf
from services.study_service import process_input
from utils.errors import AppError


UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def register_routes(app):
    @app.route("/")
    def home():
        return render_template("home.html")

    @app.route("/upload", methods=["GET", "POST"])
    def upload():
        error = None

        if request.method == "POST":
            uploaded_file = request.files.get("file")

            if not uploaded_file or not uploaded_file.filename:
                error = "Please choose a PDF file first."
            elif not uploaded_file.filename.lower().endswith(".pdf"):
                error = "Please upload a PDF file."
            else:
                filepath = os.path.join(
                    UPLOAD_FOLDER,
                    secure_filename(uploaded_file.filename),
                )
                uploaded_file.save(filepath)

                try:
                    text = extract_text_from_pdf(filepath)
                    result = process_input(text=text)
                    return render_template("result.html", result=result)
                except AppError as exc:
                    error = exc.message
                except Exception:
                    error = "Something went wrong while processing the file. Please try again."

        return render_template(
            "upload.html",
            error=error,
            neo4j_status=neo4j_status,
        )

    @app.route("/topic", methods=["GET", "POST"])
    def topic():
        if request.method == "POST":
            user_topic = request.form.get("topic", "").strip()
            selected_topic = request.form.get("selected_topic", "").strip()

            if selected_topic:
                result = process_input(topic=selected_topic)
                return render_template("result.html", result=result)

            if not user_topic:
                return render_template(
                    "topic_input.html",
                    error="Please enter a topic.",
                )

            ambiguity = check_topic_ambiguity(user_topic)

            if ambiguity.get("ambiguous"):
                return render_template(
                    "topic_options.html",
                    topic=user_topic,
                    options=ambiguity["options"],
                )

            chosen_topic = ambiguity["options"][0] if ambiguity.get("options") else user_topic
            result = process_input(topic=chosen_topic)
            return render_template("result.html", result=result)

        return render_template("topic_input.html")

    @app.route("/study-path")
    def study_path():
        if latest_result:
            return render_template("result.html", result=latest_result)

        graph_data = fetch_graph_from_neo4j()
        suggestions = fetch_topic_suggestions()

        if graph_data.get("nodes") or suggestions:
            return render_template(
                "study_path.html",
                graph=graph_data,
                suggestions=suggestions,
                neo4j_status=neo4j_status,
            )

        return render_template("result_empty.html")

    @app.route("/graph")
    def graph():
        return redirect(url_for("study_path"))

    @app.route("/quiz")
    def quiz():
        return render_template("quiz.html", quiz=latest_quiz)

