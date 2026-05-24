from models.state import latest_quiz, latest_result
from services.groq_service import safe_groq_generate
from services.quiz_service import generate_quiz
from services.roadmap_service import get_or_create_roadmap


def infer_topic_from_text(text):
    system_prompt = "You extract one main educational topic. Return only the topic name."
    user_prompt = f"""
Read this study material and identify the ONE main educational topic.
Return a real study concept only, such as ArrayList, Binary Tree, Operating System, or Machine Learning.
Do not return random words like Elements, Initial, Specified, Size, or Creates.

Text:
{text[:5000]}
"""
    response_text, error = safe_groq_generate(system_prompt, user_prompt, max_tokens=80)

    if error:
        print(f"Main topic inference failed: {error}")
        return "Uploaded PDF"

    return (response_text or "Uploaded PDF").strip().strip('"')


def generate_topic_plan(topic, context_text=None):
    try:
        return get_or_create_roadmap(topic, context_text)
    except Exception as exc:
        print(f"Topic plan generation failed for '{topic}': {exc}")
        return get_or_create_roadmap(topic, context_text, force_refresh=True)


def process_input(topic=None, text=None):
    if text:
        topic = infer_topic_from_text(text)
        context_text = text
    else:
        context_text = topic or ""
        topic = topic or "Learning Topic"

    roadmap = get_or_create_roadmap(topic, context_text)
    before = roadmap.get("prerequisites", [])
    after = roadmap.get("next_topics", [])
    related = roadmap.get("related_topics", [])

    quiz_context = "\n".join(
        [
            roadmap.get("explanation", ""),
            roadmap.get("analogy", ""),
            "Prerequisites: " + ", ".join(item["topic"] for item in before),
            "Next topics: " + ", ".join(item["topic"] for item in after),
        ]
    )

    quiz_data = generate_quiz(roadmap["topic"], quiz_context)
    latest_quiz.clear()
    latest_quiz.extend(quiz_data)

    result = {
        "topic": roadmap["topic"],
        "summary": roadmap.get("explanation"),
        "analogy": roadmap.get("analogy"),
        "difficulty": roadmap.get("difficulty"),
        "estimated_time": roadmap.get("estimated_time"),
        "before": before[:5],
        "after": after[:5],
        "related": related[:5],
        "quiz": quiz_data,
        "cached": roadmap.get("cached", False),
    }
    latest_result.clear()
    latest_result.update(result)

    return result
