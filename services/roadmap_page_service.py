"""Builds the data model for the dedicated Learning Journey (roadmap) page.

This module only derives presentation data (difficulty, time estimates,
interview importance, ordering) from an already-enriched learning goal.
It does not touch quiz generation, dashboard aggregation, or persistence.
"""

# Topics that are commonly asked about in technical interviews get a bump
# in "interview importance" regardless of their position in the roadmap.
HIGH_IMPORTANCE_KEYWORDS = (
    "algorithm", "data structure", "system design", "sql", "database",
    "decision tree", "random forest", "gradient boosting", "xgboost",
    "neural network", "statistics", "probability", "api", "authentication",
    "supervised learning", "unsupervised learning", "model evaluation",
)

MEDIUM_IMPORTANCE_KEYWORDS = (
    "entropy", "data cleaning", "data visualization", "pandas", "control flow",
    "functions", "error handling", "cryptography", "networks", "operating system",
)


def _difficulty_for(order, total):
    """Beginner -> Intermediate -> Advanced across the length of the roadmap."""
    if total <= 1:
        return "Beginner"

    position = order / total
    if position <= 1 / 3:
        return "Beginner"
    if position <= 2 / 3:
        return "Intermediate"
    return "Advanced"


def _estimated_minutes_for(order, difficulty):
    base = {"Beginner": 45, "Intermediate": 75, "Advanced": 110}.get(difficulty, 60)
    # Slight ramp so later topics in the same tier feel a little heavier.
    return base + (order % 3) * 10


def _format_minutes(total_minutes):
    hours, minutes = divmod(int(total_minutes), 60)
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"


def _interview_importance_for(topic_name):
    lowered = topic_name.lower()
    if any(keyword in lowered for keyword in HIGH_IMPORTANCE_KEYWORDS):
        return "High"
    if any(keyword in lowered for keyword in MEDIUM_IMPORTANCE_KEYWORDS):
        return "Medium"
    return "Medium"


def build_learning_journey(goal):
    """Transform an enriched goal (from database.db.enrich_goal) into the
    vertical topic chain and summary card needed by the Learning Journey page.
    """
    topics = sorted(goal["progress"]["topics"], key=lambda item: item.get("order", 0))
    total = len(topics)

    journey_topics = []
    current_seen = False
    current_order = None

    for item in topics:
        order = item.get("order", 0)
        difficulty = _difficulty_for(order, total)
        estimated_minutes = _estimated_minutes_for(order, difficulty)

        if item["status"] == "Mastered":
            journey_status = "Completed"
        elif not current_seen:
            journey_status = "Current"
            current_seen = True
            current_order = order
        else:
            journey_status = "Locked"

        journey_topics.append(
            {
                "topic": item["topic"],
                "order": order,
                "journey_status": journey_status,
                "difficulty": difficulty,
                "estimated_time": _format_minutes(estimated_minutes),
                "estimated_minutes": estimated_minutes,
                "why": item.get("why") or f"{item['topic']} is next in your roadmap.",
                "prerequisites": item.get("prerequisites") or [],
                "interview_importance": _interview_importance_for(item["topic"]),
            }
        )

    if not current_seen:
        current_order = topics[-1]["order"] + 1 if topics else 0

    current_topic = next(
        (item for item in journey_topics if item["journey_status"] == "Current"), None
    )
    locked_topics = [item for item in journey_topics if item["journey_status"] == "Locked"]
    recommended_next = locked_topics[0] if locked_topics else None

    remaining_minutes = sum(
        item["estimated_minutes"]
        for item in journey_topics
        if item["journey_status"] in ("Current", "Locked")
    )

    return {
        "goal_id": goal.get("id"),
        "roadmap_name": goal.get("title"),
        "completion_percentage": goal.get("completion_percentage", 0),
        "completed_topics": goal["progress"].get("completed_topics", 0),
        "total_topics": goal["progress"].get("total_topics", total),
        "estimated_remaining_time": _format_minutes(remaining_minutes) if remaining_minutes else "0m",
        "current_topic": current_topic,
        "recommended_next": recommended_next,
        "locked_topics": locked_topics,
        "topics": journey_topics,
        "is_complete": current_topic is None and not locked_topics and total > 0,
    }
