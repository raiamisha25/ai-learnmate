import os
import sqlite3
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash


DATABASE_FOLDER = "database"
DATABASE_PATH = os.path.join(DATABASE_FOLDER, "learnmate.db")

PROGRESS_NOT_STARTED = "Not Started"
PROGRESS_LEARNING = "Learning"
PROGRESS_PRACTICING = "Practicing"
PROGRESS_MASTERED = "Mastered"

STATUS_RANK = {
    PROGRESS_NOT_STARTED: 0,
    PROGRESS_LEARNING: 1,
    PROGRESS_PRACTICING: 2,
    PROGRESS_MASTERED: 3,
}


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

            CREATE TABLE IF NOT EXISTS user_quiz_levels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                topic TEXT NOT NULL,
                highest_level TEXT,
                highest_score REAL DEFAULT 0,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, topic),
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
        ensure_column(connection, "quiz_attempts", "level", "TEXT")
        ensure_column(connection, "quiz_attempts", "questions_attempted", "INTEGER DEFAULT 0")
        ensure_column(connection, "quiz_attempts", "correct_answers", "INTEGER DEFAULT 0")
        ensure_column(connection, "quiz_attempts", "duration", "INTEGER DEFAULT 0")
        ensure_column(connection, "quiz_attempts", "funny_comment", "TEXT")
        ensure_column(connection, "quiz_attempts", "motivational_comment", "TEXT")
        ensure_column(connection, "quiz_attempts", "topic_joke", "TEXT")
        ensure_column(connection, "user_progress", "roadmap_total", "INTEGER DEFAULT 1")
        ensure_column(connection, "user_progress", "roadmap_completed", "INTEGER DEFAULT 0")
        ensure_column(connection, "user_progress", "completion_percentage", "REAL DEFAULT 0")
        migrate_progress_statuses(connection)


def ensure_column(connection, table_name, column_name, column_type):
    columns = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    existing = {column["name"] for column in columns}

    if column_name not in existing:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def now_text():
    return datetime.utcnow().isoformat(timespec="seconds")


def migrate_progress_statuses(connection):
    """Keep old progress rows readable after the app moves to student-friendly states."""
    rows = connection.execute("SELECT id, status, last_score FROM user_progress").fetchall()

    for row in rows:
        new_status = normalize_progress_status(row["status"], row["last_score"])
        if row["status"] != new_status:
            connection.execute(
                "UPDATE user_progress SET status = ? WHERE id = ?",
                (new_status, row["id"]),
            )


def normalize_progress_status(status, score=0):
    old_status = (status or "").strip().lower()

    if old_status == PROGRESS_MASTERED.lower():
        return PROGRESS_MASTERED
    if old_status in ("completed", "strong"):
        return PROGRESS_MASTERED
    if old_status in ("practicing", "needs_revision", "failed", "weak"):
        return PROGRESS_PRACTICING
    if old_status in ("learning", "in_progress", "started"):
        return PROGRESS_LEARNING
    if old_status == PROGRESS_NOT_STARTED.lower():
        return PROGRESS_NOT_STARTED

    if score >= 85:
        return PROGRESS_MASTERED
    if score > 0:
        return PROGRESS_PRACTICING
    return PROGRESS_NOT_STARTED


def status_from_accuracy(accuracy):
    if accuracy >= 85:
        return PROGRESS_MASTERED
    if accuracy >= 50:
        return PROGRESS_PRACTICING
    return PROGRESS_LEARNING


def choose_progress_status(current_status, next_status):
    current_rank = STATUS_RANK.get(normalize_progress_status(current_status), 0)
    next_rank = STATUS_RANK.get(normalize_progress_status(next_status), 0)

    if current_rank == STATUS_RANK[PROGRESS_MASTERED]:
        return PROGRESS_MASTERED

    return next_status if next_rank >= current_rank else normalize_progress_status(current_status)


def roadmap_percentage(status, accuracy=0):
    status = normalize_progress_status(status, accuracy)

    if status == PROGRESS_MASTERED:
        return 100
    if status == PROGRESS_PRACTICING:
        return max(60, min(84, round(accuracy)))
    if status == PROGRESS_LEARNING:
        return max(25, min(59, round(accuracy)))
    return 0


def upsert_topic_progress(user_id, topic, status=PROGRESS_LEARNING, score=0):
    if not user_id or not topic:
        return

    existing = run_query(
        "SELECT status, last_score FROM user_progress WHERE user_id = ? AND topic = ?",
        (user_id, topic),
        fetchone=True,
    )
    final_status = choose_progress_status(existing["status"], status) if existing else status
    best_score = max(float(existing["last_score"] or 0), float(score or 0)) if existing else float(score or 0)
    completed = 1 if final_status == PROGRESS_MASTERED else 0
    percentage = roadmap_percentage(final_status, best_score)

    run_query(
        """
        INSERT INTO user_progress
            (
                user_id, topic, status, unlocked_next, last_score,
                roadmap_total, roadmap_completed, completion_percentage, updated_at
            )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, topic) DO UPDATE SET
            status = excluded.status,
            unlocked_next = excluded.unlocked_next,
            last_score = excluded.last_score,
            roadmap_total = excluded.roadmap_total,
            roadmap_completed = excluded.roadmap_completed,
            completion_percentage = excluded.completion_percentage,
            updated_at = excluded.updated_at
        """,
        (
            user_id,
            topic,
            final_status,
            1 if final_status == PROGRESS_MASTERED else 0,
            best_score,
            1,
            completed,
            percentage,
            now_text(),
        ),
        commit=True,
    )


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

    def topic_lines(items):
        lines = []
        for item in items or []:
            if isinstance(item, dict):
                lines.append(item.get("topic", ""))
            else:
                lines.append(str(item))
        return "\n".join(line for line in lines if line)

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
            topic_lines(result.get("before", [])),
            topic_lines(result.get("after", [])),
            now_text(),
        ),
        commit=True,
    )
    upsert_topic_progress(user_id, result.get("topic"), PROGRESS_LEARNING, score=0)


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


def save_quiz_attempt(
    user_id,
    topic,
    score,
    total,
    difficulty,
    weak_topics,
    level=None,
    duration=0,
    comments=None,
):
    accuracy = round((score / total) * 100, 2) if total else 0
    created_at = now_text()
    comments = comments or {}

    run_query(
        """
        INSERT INTO quiz_attempts
            (
                user_id, topic, score, total, accuracy, difficulty, weak_topics,
                level, questions_attempted, correct_answers, duration,
                funny_comment, motivational_comment, topic_joke, created_at
            )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            topic,
            score,
            total,
            accuracy,
            difficulty,
            "\n".join(weak_topics),
            level,
            total,
            score,
            duration,
            comments.get("funny_comment"),
            comments.get("motivational_comment"),
            comments.get("topic_joke"),
            created_at,
        ),
        commit=True,
    )

    status = status_from_accuracy(accuracy)
    unlocked_next = 1 if status == PROGRESS_MASTERED else 0

    upsert_topic_progress(user_id, topic, status, score=accuracy)

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

    old_level = run_query(
        "SELECT highest_score FROM user_quiz_levels WHERE user_id = ? AND topic = ?",
        (user_id, topic),
        fetchone=True,
    )

    if not old_level or accuracy >= old_level["highest_score"]:
        run_query(
            """
            INSERT INTO user_quiz_levels (user_id, topic, highest_level, highest_score, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, topic) DO UPDATE SET
                highest_level = excluded.highest_level,
                highest_score = excluded.highest_score,
                updated_at = excluded.updated_at
            """,
            (user_id, topic, level, accuracy, created_at),
            commit=True,
        )

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

    normalized_progress = []
    for item in progress:
        normalized_progress.append(
            {
                **dict(item),
                "status": normalize_progress_status(item["status"], item["last_score"]),
                "completion_percentage": item["completion_percentage"]
                if "completion_percentage" in item.keys()
                else roadmap_percentage(item["status"], item["last_score"]),
            }
        )

    total_topics = topic_count["total"] if topic_count else 0
    tracked_topics = len(normalized_progress)
    completed = len([item for item in normalized_progress if item["status"] == PROGRESS_MASTERED])
    average_accuracy = 0

    if quiz_attempts:
        average_accuracy = round(
            sum(item["accuracy"] for item in quiz_attempts) / len(quiz_attempts),
            1,
        )

    weak_topics = [item for item in topic_scores if item["strength"] == "weak"][:5]
    strong_topics = [item for item in topic_scores if item["strength"] == "strong"][:5]
    continue_learning = [
        item
        for item in normalized_progress
        if item["status"] in (PROGRESS_LEARNING, PROGRESS_PRACTICING)
    ][:5]
    recently_studied = normalized_progress[:5]
    mastered_topics = [
        item for item in normalized_progress if item["status"] == PROGRESS_MASTERED
    ][:5]
    failed_topics = [
        item
        for item in normalized_progress
        if item["status"] != PROGRESS_MASTERED and float(item.get("last_score") or 0) < 50
    ][:5]
    recommended = []
    roadmap_completion = 0

    if normalized_progress:
        roadmap_completion = round(
            sum(float(item.get("completion_percentage") or 0) for item in normalized_progress)
            / len(normalized_progress),
            1,
        )

    for topic in saved_topics:
        for next_topic in (topic["after_topics"] or "").splitlines():
            if next_topic and next_topic not in recommended:
                recommended.append(next_topic)

    return {
        "saved_topics": saved_topics,
        "recent_history": recent_history,
        "quiz_attempts": quiz_attempts,
        "topic_scores": topic_scores,
        "progress": normalized_progress,
        "total_topics": total_topics,
        "tracked_topics": tracked_topics,
        "completed": completed,
        "roadmap_completion": roadmap_completion,
        "average_accuracy": average_accuracy,
        "weak_topics": weak_topics,
        "failed_topics": failed_topics,
        "strong_topics": strong_topics,
        "continue_learning": continue_learning,
        "recently_studied": recently_studied,
        "mastered_topics": mastered_topics,
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
