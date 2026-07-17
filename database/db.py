import os
import json
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

WEAK_SCORE_THRESHOLD = 50
STRONG_SCORE_THRESHOLD = 80
REPEATED_WEAK_ATTEMPTS = 2
ADAPTIVE_RECOMMENDATION_LIMIT = 5


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

            CREATE TABLE IF NOT EXISTS performance_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                quiz_attempt_id INTEGER,
                topic TEXT NOT NULL,
                accuracy REAL NOT NULL,
                strength TEXT NOT NULL,
                trend TEXT NOT NULL,
                low_score_streak INTEGER NOT NULL,
                revision_recommended INTEGER DEFAULT 0,
                details TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (quiz_attempt_id) REFERENCES quiz_attempts(id)
            );

            CREATE TABLE IF NOT EXISTS learning_goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                roadmap TEXT NOT NULL,
                progress TEXT,
                completion_percentage REAL DEFAULT 0,
                recommended_next_topic TEXT,
                status TEXT NOT NULL DEFAULT 'Active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
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
        ensure_column(connection, "topic_scores", "trend", "TEXT DEFAULT 'Stable'")
        ensure_column(connection, "topic_scores", "low_score_streak", "INTEGER DEFAULT 0")
        ensure_column(connection, "topic_scores", "revision_recommended", "INTEGER DEFAULT 0")
        ensure_column(connection, "learning_goals", "progress", "TEXT")
        ensure_column(connection, "learning_goals", "completion_percentage", "REAL DEFAULT 0")
        ensure_column(connection, "learning_goals", "recommended_next_topic", "TEXT")
        ensure_column(connection, "learning_goals", "status", "TEXT NOT NULL DEFAULT 'Active'")
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


def calculate_performance_trend(attempts):
    """Compare recent quiz attempts to show whether a topic is improving."""
    scores = [float(item["accuracy"]) for item in attempts]

    if len(scores) < 2:
        return "Stable"

    newest = scores[0]
    previous = scores[1]

    if newest >= previous + 5:
        return "Improving"
    if newest <= previous - 5:
        return "Declining"
    return "Stable"


def low_score_streak(attempts):
    streak = 0

    for item in attempts:
        if float(item["accuracy"]) < WEAK_SCORE_THRESHOLD:
            streak += 1
        else:
            break

    return streak


def topic_performance_summary(user_id, topic):
    attempts = run_query(
        """
        SELECT accuracy
        FROM quiz_attempts
        WHERE user_id = ? AND topic = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 5
        """,
        (user_id, topic),
        fetchall=True,
    )
    streak = low_score_streak(attempts)
    trend = calculate_performance_trend(attempts)
    revision_recommended = streak >= REPEATED_WEAK_ATTEMPTS

    return {
        "trend": trend,
        "low_score_streak": streak,
        "revision_recommended": revision_recommended,
    }


def topic_key(topic):
    return (topic or "").strip().lower()


def split_topic_lines(text):
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def progress_is_mastered(item):
    return normalize_progress_status(item["status"], item["last_score"]) == PROGRESS_MASTERED


def roadmap_item(
    topic,
    source=None,
    reason=None,
    score=None,
    trend="Stable",
    status="Ready To Learn",
    estimated_time="45m",
    difficulty="Beginner",
    prerequisites_completed=None,
):
    return {
        "topic": topic,
        "source": source,
        "reason": reason or "Prerequisites are clear for this topic.",
        "score": score,
        "trend": trend or "Stable",
        "status": status,
        "why": reason or "Prerequisites are clear for this topic.",
        "estimated_time": estimated_time,
        "difficulty": difficulty,
        "prerequisites_completed": prerequisites_completed or [],
    }


def goal_topic_progress(topic_name, progress_by_key, score_by_key):
    progress = progress_by_key.get(topic_key(topic_name))
    score = score_by_key.get(topic_key(topic_name))
    status = PROGRESS_NOT_STARTED
    completion = 0

    if progress:
        status = normalize_progress_status(progress["status"], progress["last_score"])
        completion = float(progress.get("completion_percentage") or roadmap_percentage(status, progress["last_score"]))

    if score and (score["strength"] == "weak" or bool(score["revision_recommended"])):
        status = "Needs Revision"
    elif score and score["strength"] == "strong":
        status = PROGRESS_MASTERED
        completion = 100

    return {
        "status": status,
        "completion_percentage": round(completion, 1),
        "score": float(score["average_score"]) if score else None,
        "trend": score["trend"] if score else "Stable",
        "needs_revision": bool(score["revision_recommended"]) if score else False,
    }


def enrich_goal(goal, normalized_progress, topic_scores):
    roadmap = json.loads(goal["roadmap"] or "{}")
    topics = roadmap.get("topics", [])
    progress_by_key = {topic_key(item["topic"]): item for item in normalized_progress}
    score_by_key = {topic_key(item["topic"]): item for item in topic_scores}
    mastered_keys = {
        topic_key(item["topic"])
        for item in normalized_progress
        if progress_is_mastered(item)
    }
    mastered_keys.update(topic_key(item["topic"]) for item in topic_scores if item["strength"] == "strong")
    enriched_topics = []
    recommended_next = None

    for item in topics:
        topic_name = item.get("topic")
        topic_progress = goal_topic_progress(topic_name, progress_by_key, score_by_key)
        prerequisites = item.get("prerequisites", [])
        missing_prerequisites = [
            prereq for prereq in prerequisites if topic_key(prereq) not in mastered_keys
        ]
        is_available = not missing_prerequisites

        enriched_item = {
            **item,
            **topic_progress,
            "available": is_available,
            "missing_prerequisites": missing_prerequisites,
        }
        enriched_topics.append(enriched_item)

        if not recommended_next and is_available and topic_progress["status"] != PROGRESS_MASTERED:
            recommended_next = topic_name

    if enriched_topics:
        completion = round(
            sum(item["completion_percentage"] for item in enriched_topics) / len(enriched_topics),
            1,
        )
    else:
        completion = 0

    progress_payload = {
        "topics": enriched_topics,
        "completed_topics": len([item for item in enriched_topics if item["status"] == PROGRESS_MASTERED]),
        "total_topics": len(enriched_topics),
    }
    status = "Completed" if completion >= 100 and enriched_topics else "Active"

    return {
        **dict(goal),
        "roadmap": roadmap,
        "progress": progress_payload,
        "completion_percentage": completion,
        "recommended_next_topic": recommended_next,
        "status": status,
    }


def refresh_goal_progress(goal, enriched_goal):
    run_query(
        """
        UPDATE learning_goals
        SET progress = ?, completion_percentage = ?, recommended_next_topic = ?,
            status = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            json.dumps(enriched_goal["progress"]),
            enriched_goal["completion_percentage"],
            enriched_goal["recommended_next_topic"],
            enriched_goal["status"],
            now_text(),
            goal["id"],
        ),
        commit=True,
    )


def create_learning_goal(user_id, title, roadmap):
    if not user_id or not title or not roadmap:
        return None

    created_at = now_text()
    cursor = run_query(
        """
        INSERT INTO learning_goals
            (
                user_id, title, roadmap, progress, completion_percentage,
                recommended_next_topic, status, created_at, updated_at
            )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            title,
            json.dumps(roadmap),
            json.dumps({"topics": [], "completed_topics": 0, "total_topics": 0}),
            0,
            None,
            "Active",
            created_at,
            created_at,
        ),
        commit=True,
    )

    for item in roadmap.get("topics", []):
        upsert_topic_progress(user_id, item.get("topic"), PROGRESS_NOT_STARTED, score=0)

    add_history(user_id, "goal_created", title, "Created a learning goal")
    return cursor.lastrowid


def goal_topic_names(goal):
    roadmap = json.loads(goal["roadmap"] or "{}")
    return [
        item.get("topic")
        for item in roadmap.get("topics", [])
        if item.get("topic")
    ]


def reset_goal_topic_data(user_id, topics):
    topics = [topic for topic in topics if topic]
    if not topics:
        return

    placeholders = ",".join("?" for _ in topics)
    params = (user_id, *topics)

    run_query(
        f"DELETE FROM performance_history WHERE user_id = ? AND topic IN ({placeholders})",
        params,
        commit=True,
    )
    run_query(
        f"DELETE FROM quiz_attempts WHERE user_id = ? AND topic IN ({placeholders})",
        params,
        commit=True,
    )
    run_query(
        f"DELETE FROM topic_scores WHERE user_id = ? AND topic IN ({placeholders})",
        params,
        commit=True,
    )
    run_query(
        f"DELETE FROM user_quiz_levels WHERE user_id = ? AND topic IN ({placeholders})",
        params,
        commit=True,
    )
    run_query(
        f"DELETE FROM user_progress WHERE user_id = ? AND topic IN ({placeholders})",
        params,
        commit=True,
    )
    run_query(
        f"DELETE FROM learning_history WHERE user_id = ? AND topic IN ({placeholders})",
        params,
        commit=True,
    )


def reset_learning_goal(user_id, goal_id):
    goal = run_query(
        "SELECT * FROM learning_goals WHERE id = ? AND user_id = ?",
        (goal_id, user_id),
        fetchone=True,
    )

    if not goal:
        return False

    topics = goal_topic_names(goal)
    reset_goal_topic_data(user_id, topics)
    run_query(
        "DELETE FROM learning_history WHERE user_id = ? AND topic = ?",
        (user_id, goal["title"]),
        commit=True,
    )

    for topic in topics:
        upsert_topic_progress(user_id, topic, PROGRESS_NOT_STARTED, score=0)

    run_query(
        """
        UPDATE learning_goals
        SET progress = ?, completion_percentage = ?, recommended_next_topic = ?,
            status = ?, updated_at = ?
        WHERE id = ? AND user_id = ?
        """,
        (
            json.dumps({"topics": [], "completed_topics": 0, "total_topics": 0}),
            0,
            None,
            "Active",
            now_text(),
            goal_id,
            user_id,
        ),
        commit=True,
    )
    add_history(user_id, "goal_reset", goal["title"], "Reset learning goal")
    return True


def delete_learning_goal(user_id, goal_id):
    goal = run_query(
        "SELECT * FROM learning_goals WHERE id = ? AND user_id = ?",
        (goal_id, user_id),
        fetchone=True,
    )

    if not goal:
        return False

    reset_goal_topic_data(user_id, goal_topic_names(goal))
    run_query(
        "DELETE FROM learning_history WHERE user_id = ? AND topic = ?",
        (user_id, goal["title"]),
        commit=True,
    )
    run_query(
        "DELETE FROM learning_goals WHERE id = ? AND user_id = ?",
        (goal_id, user_id),
        commit=True,
    )
    return True


def user_goals(user_id, normalized_progress=None, topic_scores=None, limit=None):
    query = "SELECT * FROM learning_goals WHERE user_id = ? ORDER BY updated_at DESC"
    params = [user_id]

    if limit:
        query += " LIMIT ?"
        params.append(limit)

    rows = run_query(query, tuple(params), fetchall=True)
    normalized_progress = normalized_progress if normalized_progress is not None else []
    topic_scores = topic_scores if topic_scores is not None else []
    goals = []

    for row in rows:
        enriched = enrich_goal(row, normalized_progress, topic_scores)
        refresh_goal_progress(row, enriched)
        goals.append(enriched)

    return goals


IMPORTANT_TOPIC_KEYWORDS = (
    "algorithm", "array", "binary tree", "database", "decision tree", "dynamic programming",
    "graph", "hash", "heap", "machine learning", "neural network", "operating system",
    "queue", "random forest", "recursion", "regression", "search", "sorting", "stack",
    "statistics", "tree",
)


def recommendation_difficulty(topic_name, completed_count, prerequisite_count):
    lowered = topic_name.lower()

    if prerequisite_count >= 3 or any(word in lowered for word in ("advanced", "neural", "random forest")):
        return "Advanced"
    if completed_count >= 1 or any(word in lowered for word in ("tree", "graph", "database", "regression")):
        return "Intermediate"
    return "Beginner"


def recommendation_estimated_time(difficulty, weak=False):
    minutes = {"Beginner": 45, "Intermediate": 75, "Advanced": 110}.get(difficulty, 60)
    if weak:
        minutes += 20

    hours, remainder = divmod(minutes, 60)
    if hours and remainder:
        return f"{hours}h {remainder}m"
    if hours:
        return f"{hours}h"
    return f"{remainder}m"


def topic_importance_score(topic_name):
    lowered = topic_name.lower()
    return 25 if any(keyword in lowered for keyword in IMPORTANT_TOPIC_KEYWORDS) else 10


def recommendation_reason(topic, completed_prerequisites, missing_prerequisites, score, is_weak, source):
    reasons = []

    if completed_prerequisites:
        reasons.append(f"{len(completed_prerequisites)} prerequisite(s) completed")
    if missing_prerequisites:
        reasons.append(f"{len(missing_prerequisites)} prerequisite(s) still pending")
    if is_weak:
        reasons.append("recent quiz performance shows this needs revision")
    elif score:
        reasons.append(f"quiz average is {round(float(score['average_score']), 1)}%")
    if source:
        reasons.append(f"unlocked from {source}")
    if topic_importance_score(topic) > 10:
        reasons.append("high-value topic for the roadmap")

    return "; ".join(reasons) or "Recommended from your learning progress."


def adaptive_roadmap_data(saved_topics, normalized_progress, topic_scores):
    """Build personalized roadmap lanes from progress, weak topics, and prerequisites."""
    saved_by_key = {topic_key(item["topic"]): item for item in saved_topics}
    progress_by_key = {topic_key(item["topic"]): item for item in normalized_progress}
    score_by_key = {topic_key(item["topic"]): item for item in topic_scores}
    mastered_keys = {
        topic_key(item["topic"])
        for item in normalized_progress
        if progress_is_mastered(item)
    }
    mastered_keys.update(
        topic_key(item["topic"]) for item in topic_scores if item["strength"] == "strong"
    )
    weak_keys = {
        topic_key(item["topic"])
        for item in topic_scores
        if item["strength"] == "weak" or bool(item["revision_recommended"])
    }

    def prerequisites_for(topic_name):
        saved = saved_by_key.get(topic_key(topic_name))
        return split_topic_lines(saved["before_topics"]) if saved else []

    def missing_prerequisites(topic_name):
        return [
            prereq
            for prereq in prerequisites_for(topic_name)
            if topic_key(prereq) not in mastered_keys
        ]

    history_order = {
        topic_key(item["topic"]): index
        for index, item in enumerate(saved_topics)
        if item["topic"]
    }

    def is_ready(topic_name):
        key = topic_key(topic_name)
        return key not in mastered_keys and key not in weak_keys and not missing_prerequisites(topic_name)

    def completed_prerequisites(topic_name):
        return [
            prereq
            for prereq in prerequisites_for(topic_name)
            if topic_key(prereq) in mastered_keys
        ]

    def candidate_score(topic_name, source=None):
        key = topic_key(topic_name)
        progress = progress_by_key.get(key)
        score = score_by_key.get(key)
        prerequisites = prerequisites_for(topic_name)
        completed = completed_prerequisites(topic_name)
        missing = missing_prerequisites(topic_name)
        is_weak = key in weak_keys
        difficulty = recommendation_difficulty(topic_name, len(completed), len(prerequisites))
        difficulty_score = {"Beginner": 18, "Intermediate": 12, "Advanced": 6}.get(difficulty, 10)
        quiz_score = 0

        if score:
            average = float(score["average_score"])
            if average < WEAK_SCORE_THRESHOLD:
                quiz_score += 20
            elif average < STRONG_SCORE_THRESHOLD:
                quiz_score += 12
            else:
                quiz_score -= 20

        return (
            (len(completed) * 30)
            - (len(missing) * 25)
            + topic_importance_score(topic_name)
            + difficulty_score
            + max(0, 10 - history_order.get(key, 10))
            + quiz_score
            + (25 if is_weak else 0)
            - (100 if key in mastered_keys else 0)
            + (8 if progress and normalize_progress_status(progress["status"], progress["last_score"]) == PROGRESS_LEARNING else 0)
            + (6 if source and topic_key(source) in mastered_keys else 0)
        )

    def ranked_item(topic_name, source=None, status="Recommended Next"):
        key = topic_key(topic_name)
        score = score_by_key.get(key)
        completed = completed_prerequisites(topic_name)
        missing = missing_prerequisites(topic_name)
        is_weak = key in weak_keys
        difficulty = recommendation_difficulty(topic_name, len(completed), len(prerequisites_for(topic_name)))
        return roadmap_item(
            topic_name,
            source=source,
            score=float(score["average_score"]) if score else None,
            trend=score["trend"] if score else "Stable",
            reason=recommendation_reason(topic_name, completed, missing, score, is_weak, source),
            status=status,
            estimated_time=recommendation_estimated_time(difficulty, weak=is_weak),
            difficulty=difficulty,
            prerequisites_completed=completed,
        )

    ready_candidates = {}
    recommendation_candidates = {}

    for topic in saved_topics:
        topic_name = topic["topic"]
        key = topic_key(topic_name)

        if is_ready(topic_name):
            ready_candidates[key] = (candidate_score(topic_name), ranked_item(topic_name, status="Ready To Learn"))
        elif key in weak_keys and key not in mastered_keys:
            ready_candidates[key] = (candidate_score(topic_name), ranked_item(topic_name, status="Needs Revision"))

    for topic in saved_topics:
        source_topic = topic["topic"]

        for next_topic in split_topic_lines(topic["after_topics"]):
            key = topic_key(next_topic)
            if key in mastered_keys:
                continue

            item = ranked_item(next_topic, source=source_topic)
            score_value = candidate_score(next_topic, source=source_topic)
            previous = recommendation_candidates.get(key)

            if not previous or score_value > previous[0]:
                recommendation_candidates[key] = (score_value, item)

    for key, (score_value, item) in ready_candidates.items():
        previous = recommendation_candidates.get(key)
        recommended_item = {**item, "status": "Recommended Next"}
        if not previous or score_value > previous[0]:
            recommendation_candidates[key] = (score_value, recommended_item)

    ready_to_learn = [
        item
        for _score, item in sorted(ready_candidates.values(), key=lambda pair: pair[0], reverse=True)
    ][:ADAPTIVE_RECOMMENDATION_LIMIT]
    recommended_next = [
        item
        for _score, item in sorted(recommendation_candidates.values(), key=lambda pair: pair[0], reverse=True)
    ][:ADAPTIVE_RECOMMENDATION_LIMIT]

    return {
        "ready_to_learn": ready_to_learn,
        "recommended_next": recommended_next,
    }


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

    attempt_cursor = run_query(
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
    attempt_id = attempt_cursor.lastrowid

    status = status_from_accuracy(accuracy)
    unlocked_next = 1 if status == PROGRESS_MASTERED else 0

    upsert_topic_progress(user_id, topic, status, score=accuracy)

    old_score = run_query(
        "SELECT average_score, attempts FROM topic_scores WHERE user_id = ? AND topic = ?",
        (user_id, topic),
        fetchone=True,
    )

    performance = topic_performance_summary(user_id, topic)

    if old_score:
        attempts = old_score["attempts"] + 1
        average = round(((old_score["average_score"] * old_score["attempts"]) + accuracy) / attempts, 2)
    else:
        attempts = 1
        average = accuracy

    if performance["revision_recommended"] or average < WEAK_SCORE_THRESHOLD:
        strength = "weak"
    elif average >= STRONG_SCORE_THRESHOLD:
        strength = "strong"
    else:
        strength = "growing"

    run_query(
        """
        INSERT INTO topic_scores
            (
                user_id, topic, average_score, attempts, strength,
                trend, low_score_streak, revision_recommended, updated_at
            )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, topic) DO UPDATE SET
            average_score = excluded.average_score,
            attempts = excluded.attempts,
            strength = excluded.strength,
            trend = excluded.trend,
            low_score_streak = excluded.low_score_streak,
            revision_recommended = excluded.revision_recommended,
            updated_at = excluded.updated_at
        """,
        (
            user_id,
            topic,
            average,
            attempts,
            strength,
            performance["trend"],
            performance["low_score_streak"],
            1 if performance["revision_recommended"] else 0,
            created_at,
        ),
        commit=True,
    )

    if performance["revision_recommended"]:
        details = (
            f"Needs Revision: {performance['low_score_streak']} recent attempts below "
            f"{WEAK_SCORE_THRESHOLD}%."
        )
    elif strength == "strong":
        details = f"Strong topic: average score is {average}%."
    else:
        details = f"Current average score is {average}%."

    run_query(
        """
        INSERT INTO performance_history
            (
                user_id, quiz_attempt_id, topic, accuracy, strength, trend,
                low_score_streak, revision_recommended, details, created_at
            )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            attempt_id,
            topic,
            accuracy,
            strength,
            performance["trend"],
            performance["low_score_streak"],
            1 if performance["revision_recommended"] else 0,
            details,
            created_at,
        ),
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
        "strength": strength,
        "trend": performance["trend"],
        "low_score_streak": performance["low_score_streak"],
        "revision_recommended": performance["revision_recommended"],
    }


def dashboard_data(user_id, include_adaptive_sections=True):
    topic_count = run_query(
        "SELECT COUNT(*) AS total FROM saved_topics WHERE user_id = ?",
        (user_id,),
        fetchone=True,
    )
    saved_topics = run_query(
        "SELECT * FROM saved_topics WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
        fetchall=True,
    )
    recent_history = []
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
    performance_history = []
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
    completed = len([item for item in normalized_progress if item["status"] == PROGRESS_MASTERED])
    average_accuracy = 0

    if quiz_attempts:
        average_accuracy = round(
            sum(item["accuracy"] for item in quiz_attempts) / len(quiz_attempts),
            1,
        )

    needs_revision = []
    revision_quizzes = []
    continue_learning = [
        item
        for item in normalized_progress
        if item["status"] in (PROGRESS_LEARNING, PROGRESS_PRACTICING)
    ][:5]
    goals = user_goals(user_id, normalized_progress, topic_scores)
    active_goals = [goal for goal in goals if goal["status"] == "Active"][:5]
    goal_completion = round(
        sum(float(goal.get("completion_percentage") or 0) for goal in goals) / len(goals),
        1,
    ) if goals else 0
    progress_topic_keys = {topic_key(item["topic"]) for item in normalized_progress}
    score_topic_keys = {topic_key(item["topic"]) for item in topic_scores}
    tracked_topic_keys = progress_topic_keys | score_topic_keys
    needs_revision_keys = {
        topic_key(item["topic"])
        for item in topic_scores
        if item["strength"] == "weak" or bool(item["revision_recommended"])
    }
    mastered_keys = {
        topic_key(item["topic"])
        for item in normalized_progress
        if item["status"] == PROGRESS_MASTERED
    }
    mastered_keys.update(
        topic_key(item["topic"]) for item in topic_scores if item["strength"] == "strong"
    )
    mastered_keys = mastered_keys & tracked_topic_keys
    needs_revision_keys = needs_revision_keys & tracked_topic_keys
    learning_keys = tracked_topic_keys - mastered_keys - needs_revision_keys
    progress_total = len(tracked_topic_keys)
    mastered_count = len(mastered_keys)
    learning_count = len(learning_keys)
    needs_revision_count = len(needs_revision_keys)
    progress_stats = {
        "mastered": mastered_count,
        "learning": learning_count,
        "needs_revision": needs_revision_count,
        "total": progress_total,
        "mastered_percentage": round((mastered_count / progress_total) * 100, 1) if progress_total else 0,
        "learning_percentage": round((learning_count / progress_total) * 100, 1) if progress_total else 0,
        "needs_revision_percentage": round((needs_revision_count / progress_total) * 100, 1) if progress_total else 0,
    }
    recommended = []
    roadmap_completion = 0
    ready_to_learn = []
    recommended_next = []

    if include_adaptive_sections:
        recent_history = run_query(
            "SELECT * FROM learning_history WHERE user_id = ? ORDER BY created_at DESC LIMIT 8",
            (user_id,),
            fetchall=True,
        )
        performance_history = run_query(
            """
            SELECT *
            FROM performance_history
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 10
            """,
            (user_id,),
            fetchall=True,
        )
        needs_revision = [
            item
            for item in topic_scores
            if item["strength"] == "weak" or bool(item["revision_recommended"])
        ][:5]
        revision_quizzes = [
            {
                "topic": item["topic"],
                "average_score": item["average_score"],
                "trend": item["trend"],
                "low_score_streak": item["low_score_streak"],
                "difficulty": "easy" if float(item["average_score"]) < 50 else "medium",
                "duration": 3,
            }
            for item in needs_revision
        ]
        adaptive_roadmap = adaptive_roadmap_data(saved_topics, normalized_progress, topic_scores)
        ready_to_learn = adaptive_roadmap["ready_to_learn"]
        recommended_next = adaptive_roadmap["recommended_next"]

    if normalized_progress:
        roadmap_completion = round(
            sum(float(item.get("completion_percentage") or 0) for item in normalized_progress)
            / len(normalized_progress),
            1,
        )

    if include_adaptive_sections:
        for topic in saved_topics:
            for next_topic in (topic["after_topics"] or "").splitlines():
                if next_topic and next_topic not in recommended:
                    recommended.append(next_topic)

    return {
        "saved_topics": saved_topics,
        "recent_history": recent_history,
        "quiz_attempts": quiz_attempts,
        "topic_scores": topic_scores,
        "performance_history": performance_history,
        "progress": normalized_progress,
        "total_topics": total_topics,
        "completed": completed,
        "roadmap_completion": roadmap_completion,
        "average_accuracy": average_accuracy,
        "needs_revision": needs_revision,
        "revision_quizzes": revision_quizzes,
        "continue_learning": continue_learning,
        "goals": goals,
        "active_goals": active_goals,
        "goal_completion": goal_completion,
        "goal_remaining": round(100 - goal_completion, 1) if goals else 0,
        "progress_stats": progress_stats,
        "ready_to_learn": ready_to_learn,
        "recommended_next": recommended_next,
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
