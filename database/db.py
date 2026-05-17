import os
import sqlite3
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash


DATABASE_FOLDER = "database"
DATABASE_PATH = os.path.join(DATABASE_FOLDER, "learnmate.db")


def get_connection():
    os.makedirs(DATABASE_FOLDER, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def run_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    with get_connection() as connection:
        cursor = connection.execute(query, params)

        if commit:
            connection.commit()

        if fetchone:
            return cursor.fetchone()

        if fetchall:
            return cursor.fetchall()

        return cursor


def init_db():
    """Create the SQLite tables used by user accounts and progress tracking."""
    os.makedirs(DATABASE_FOLDER, exist_ok=True)

    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS learning_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                topic TEXT,
                details TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS uploaded_pdfs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                topic TEXT,
                summary TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS saved_topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                topic TEXT NOT NULL,
                summary TEXT,
                before_topics TEXT,
                after_topics TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, topic),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS quiz_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                topic TEXT NOT NULL,
                score INTEGER NOT NULL,
                total INTEGER NOT NULL,
                accuracy REAL NOT NULL,
                difficulty TEXT NOT NULL,
                weak_topics TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS user_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                topic TEXT NOT NULL,
                status TEXT NOT NULL,
                unlocked_next INTEGER DEFAULT 0,
                last_score REAL DEFAULT 0,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, topic),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS topic_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                topic TEXT NOT NULL,
                average_score REAL NOT NULL,
                attempts INTEGER NOT NULL,
                strength TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, topic),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            """
        )


def now_text():
    return datetime.utcnow().isoformat(timespec="seconds")


def create_user(username, email, password):
    password_hash = generate_password_hash(password)
    run_query(
        """
        INSERT INTO users (username, email, password_hash, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (username, email, password_hash, now_text()),
        commit=True,
    )


def find_user_by_email(email):
    return run_query(
        "SELECT * FROM users WHERE lower(email) = lower(?)",
        (email,),
        fetchone=True,
    )


def find_user_by_id(user_id):
    return run_query(
        "SELECT * FROM users WHERE id = ?",
        (user_id,),
        fetchone=True,
    )


def add_history(user_id, action_type, topic=None, details=None):
    if not user_id:
        return

    run_query(
        """
        INSERT INTO learning_history (user_id, action_type, topic, details, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, action_type, topic, details, now_text()),
        commit=True,
    )


def save_study_plan(user_id, result):
    if not user_id or not result:
        return

    run_query(
        """
        INSERT INTO saved_topics
            (user_id, topic, summary, before_topics, after_topics, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, topic) DO UPDATE SET
            summary = excluded.summary,
            before_topics = excluded.before_topics,
            after_topics = excluded.after_topics,
            created_at = excluded.created_at
        """,
        (
            user_id,
            result.get("topic"),
            result.get("summary"),
            "\n".join(result.get("before", [])),
            "\n".join(result.get("after", [])),
            now_text(),
        ),
        commit=True,
    )


def save_uploaded_pdf(user_id, filename, result):
    if not user_id:
        return

    run_query(
        """
        INSERT INTO uploaded_pdfs (user_id, filename, topic, summary, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            user_id,
            filename,
            result.get("topic"),
            result.get("summary"),
            now_text(),
        ),
        commit=True,
    )


def save_quiz_attempt(user_id, topic, score, total, difficulty, weak_topics):
    accuracy = round((score / total) * 100, 2) if total else 0
    created_at = now_text()

    run_query(
        """
        INSERT INTO quiz_attempts
            (user_id, topic, score, total, accuracy, difficulty, weak_topics, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            topic,
            score,
            total,
            accuracy,
            difficulty,
            "\n".join(weak_topics),
            created_at,
        ),
        commit=True,
    )

    if accuracy >= 80:
        status = "completed"
        unlocked_next = 1
    elif accuracy < 50:
        status = "needs_revision"
        unlocked_next = 0
    else:
        status = "practicing"
        unlocked_next = 0

    run_query(
        """
        INSERT INTO user_progress (user_id, topic, status, unlocked_next, last_score, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, topic) DO UPDATE SET
            status = excluded.status,
            unlocked_next = excluded.unlocked_next,
            last_score = excluded.last_score,
            updated_at = excluded.updated_at
        """,
        (user_id, topic, status, unlocked_next, accuracy, created_at),
        commit=True,
    )

    old_score = run_query(
        "SELECT average_score, attempts FROM topic_scores WHERE user_id = ? AND topic = ?",
        (user_id, topic),
        fetchone=True,
    )

    if old_score:
        attempts = old_score["attempts"] + 1
        average = round(((old_score["average_score"] * old_score["attempts"]) + accuracy) / attempts, 2)
    else:
        attempts = 1
        average = accuracy

    strength = "strong" if average >= 80 else "weak" if average < 50 else "growing"

    run_query(
        """
        INSERT INTO topic_scores (user_id, topic, average_score, attempts, strength, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, topic) DO UPDATE SET
            average_score = excluded.average_score,
            attempts = excluded.attempts,
            strength = excluded.strength,
            updated_at = excluded.updated_at
        """,
        (user_id, topic, average, attempts, strength, created_at),
        commit=True,
    )

    add_history(user_id, "quiz_attempted", topic, f"Scored {score}/{total} ({accuracy}%)")

    return {
        "accuracy": accuracy,
        "status": status,
        "unlocked_next": bool(unlocked_next),
    }


def dashboard_data(user_id):
    topic_count = run_query(
        "SELECT COUNT(*) AS total FROM saved_topics WHERE user_id = ?",
        (user_id,),
        fetchone=True,
    )
    saved_topics = run_query(
        "SELECT * FROM saved_topics WHERE user_id = ? ORDER BY created_at DESC LIMIT 6",
        (user_id,),
        fetchall=True,
    )
    recent_history = run_query(
        "SELECT * FROM learning_history WHERE user_id = ? ORDER BY created_at DESC LIMIT 8",
        (user_id,),
        fetchall=True,
    )
    quiz_attempts = run_query(
        "SELECT * FROM quiz_attempts WHERE user_id = ? ORDER BY created_at DESC LIMIT 6",
        (user_id,),
        fetchall=True,
    )
    topic_scores = run_query(
        "SELECT * FROM topic_scores WHERE user_id = ? ORDER BY updated_at DESC",
        (user_id,),
        fetchall=True,
    )
    progress = run_query(
        "SELECT * FROM user_progress WHERE user_id = ? ORDER BY updated_at DESC",
        (user_id,),
        fetchall=True,
    )

    total_topics = topic_count["total"] if topic_count else 0
    completed = len([item for item in progress if item["status"] == "completed"])
    average_accuracy = 0

    if quiz_attempts:
        average_accuracy = round(
            sum(item["accuracy"] for item in quiz_attempts) / len(quiz_attempts),
            1,
        )

    weak_topics = [item for item in topic_scores if item["strength"] == "weak"][:5]
    strong_topics = [item for item in topic_scores if item["strength"] == "strong"][:5]
    recommended = []

    for topic in saved_topics:
        for next_topic in (topic["after_topics"] or "").splitlines():
            if next_topic and next_topic not in recommended:
                recommended.append(next_topic)

    return {
        "saved_topics": saved_topics,
        "recent_history": recent_history,
        "quiz_attempts": quiz_attempts,
        "topic_scores": topic_scores,
        "progress": progress,
        "total_topics": total_topics,
        "completed": completed,
        "average_accuracy": average_accuracy,
        "weak_topics": weak_topics,
        "strong_topics": strong_topics,
        "recommended": recommended[:5],
        "streak": learning_streak(user_id),
    }


def learning_streak(user_id):
    rows = run_query(
        "SELECT date(created_at) AS activity_date FROM learning_history WHERE user_id = ? GROUP BY date(created_at)",
        (user_id,),
        fetchall=True,
    )
    active_days = {row["activity_date"] for row in rows}
    streak = 0
    day = datetime.utcnow().date()

    while day.isoformat() in active_days:
        streak += 1
        day -= timedelta(days=1)

    return streak


def leaderboard(limit=10):
    return run_query(
        """
        SELECT users.username, quiz_attempts.topic, quiz_attempts.accuracy, quiz_attempts.created_at
        FROM quiz_attempts
        JOIN users ON users.id = quiz_attempts.user_id
        ORDER BY quiz_attempts.accuracy DESC, quiz_attempts.created_at DESC
        LIMIT ?
        """,
        (limit,),
        fetchall=True,
    )
