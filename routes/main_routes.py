import os

from flask import g, jsonify, redirect, render_template, request, session, url_for
from sqlite3 import IntegrityError
from werkzeug.utils import secure_filename

from auth.helpers import authenticate_user, login_required, login_user, logout_user
from database.db import (
    add_history,
    create_user,
    dashboard_data,
    leaderboard,
    save_quiz_attempt,
    save_study_plan,
    save_uploaded_pdf,
)
from models.state import latest_quiz, latest_result, neo4j_status
from services.ambiguity_service import check_topic_ambiguity
from services.neo4j_service import fetch_graph_from_neo4j, fetch_topic_suggestions
from services.pdf_service import extract_text_from_pdf
from services.quiz_service import calculate_level, generate_quiz, generate_quiz_comments
from services.study_service import process_input
from utils.errors import AppError


UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def register_routes(app):
    @app.route("/")
    def home():
        return render_template("home.html")

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            email = request.form.get("email", "").strip()
            password = request.form.get("password", "")

            if not username or not email or not password:
                return render_template(
                    "signup.html",
                    error="Please fill in all fields.",
                )

            if len(password) < 6:
                return render_template(
                    "signup.html",
                    error="Use a password with at least 6 characters.",
                )

            try:
                create_user(username, email, password)
            except IntegrityError:
                return render_template(
                    "signup.html",
                    error="That username or email is already registered.",
                )

            user = authenticate_user(email, password)
            login_user(user, remember=True)
            add_history(user["id"], "account_created", "Welcome", "Joined AI LearnMate")
            return redirect(url_for("dashboard"))

        return render_template("signup.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").strip()
            password = request.form.get("password", "")
            remember = request.form.get("remember") == "on"
            user = authenticate_user(email, password)

            if not user:
                return render_template(
                    "login.html",
                    error="Invalid email or password.",
                )

            login_user(user, remember=remember)
            add_history(user["id"], "logged_in", "Account", "Returned to AI LearnMate")
            next_url = request.args.get("next") or url_for("dashboard")
            if not next_url.startswith("/"):
                next_url = url_for("dashboard")
            return redirect(next_url)

        return render_template("login.html")

    @app.route("/logout")
    def logout():
        logout_user()
        return redirect(url_for("home"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        data = dashboard_data(g.user["id"])
        return render_template("dashboard.html", data=data)

    @app.route("/history")
    @login_required
    def history():
        data = dashboard_data(g.user["id"])
        return render_template("history.html", data=data)

    @app.route("/leaderboard")
    def leaderboard_page():
        return render_template("leaderboard.html", leaders=leaderboard())

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
                    if g.get("user"):
                        save_study_plan(g.user["id"], result)
                        save_uploaded_pdf(g.user["id"], uploaded_file.filename, result)
                        add_history(
                            g.user["id"],
                            "uploaded_pdf",
                            result.get("topic"),
                            uploaded_file.filename,
                        )
                    return render_template("result.html", result=result)
                except AppError as exc:
                    error = exc.message
                except Exception as exc:
                    print(f"PDF upload processing failed: {exc}")
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
                if g.get("user"):
                    save_study_plan(g.user["id"], result)
                    add_history(g.user["id"], "searched_topic", result.get("topic"), "Selected topic meaning")
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
            if g.get("user"):
                save_study_plan(g.user["id"], result)
                add_history(g.user["id"], "searched_topic", result.get("topic"), "Manual topic search")
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
    @login_required
    def quiz():
        topic = request.args.get("topic", latest_result.get("topic", ""))
        started = request.args.get("started") == "1"
        return render_template(
            "quiz.html",
            quiz=latest_quiz if started else [],
            setup_only=not started,
            topic=topic,
            difficulty=session.get("quiz_difficulty", "easy"),
            duration=session.get("quiz_duration", 3),
            leaderboard=leaderboard(5),
        )

    @app.route("/quiz/start", methods=["POST"])
    @login_required
    def start_quiz():
        topic = request.form.get("topic", "").strip()

        if not topic:
            return render_template(
                "quiz.html",
                quiz=[],
                topic="",
                difficulty="easy",
                duration=3,
                leaderboard=leaderboard(5),
                error="Please enter a topic to start a quiz.",
            )

        session["quiz_difficulty"] = request.form.get("difficulty", "easy")
        session["quiz_duration"] = int(request.form.get("duration", 3))
        quiz_questions = generate_quiz(
            topic,
            difficulty=session["quiz_difficulty"],
            duration_minutes=session["quiz_duration"],
        )
        latest_quiz.clear()
        latest_quiz.extend(quiz_questions)
        add_history(
            g.user["id"],
            "started_quiz",
            topic,
            f"{session['quiz_difficulty'].title()} quiz for {session['quiz_duration']} minutes",
        )
        return redirect(url_for("quiz", topic=topic, started=1))

    @app.route("/quiz/submit", methods=["POST"])
    @login_required
    def submit_quiz():
        data = request.get_json(silent=True) or {}
        topic = data.get("topic") or latest_result.get("topic") or "Learning Topic"
        answers = data.get("answers", [])
        difficulty = data.get("difficulty", "easy")
        duration = int(data.get("duration", session.get("quiz_duration", 3)))
        score = 0
        weak_topics = []
        attempted_questions = min(len(answers), len(latest_quiz))

        for index, selected in enumerate(answers[:attempted_questions]):
            question = latest_quiz[index]

            if selected == question.get("answer"):
                score += 1
            else:
                weak_topics.append(question.get("question", topic))

        accuracy = round((score / attempted_questions) * 100, 2) if attempted_questions else 0
        level, level_comment = calculate_level(difficulty, accuracy)
        comments = generate_quiz_comments(topic, difficulty, accuracy, level)
        progress = save_quiz_attempt(
            g.user["id"],
            topic,
            score,
            attempted_questions,
            difficulty,
            weak_topics,
            level=level,
            duration=duration,
            comments=comments,
        )
        session["last_quiz_result"] = {
            "topic": topic,
            "score": score,
            "total": attempted_questions,
            "questions_attempted": attempted_questions,
            "correct_answers": score,
            "duration": duration,
            "level": level,
            "level_comment": level_comment,
            "funny_comment": comments.get("funny_comment"),
            "motivational_comment": comments.get("motivational_comment"),
            "topic_joke": comments.get("topic_joke"),
            "weak_topics": weak_topics,
            **progress,
        }

        return jsonify(session["last_quiz_result"])
