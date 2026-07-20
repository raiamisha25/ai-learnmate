"""
study_service.py

Responsible ONLY for orchestrating the learning workflow:
- Coordinating roadmap generation
- Lazy on-demand lecture generation & application-level caching
- Coordinating recommendation engine and quiz service
"""

import json

from models.state import latest_quiz, latest_result
from services.groq_service import safe_groq_generate
from services.neo4j_service import fetch_raw_suggestions_from_neo4j
from services.prompt_builders import build_topic_lecture_prompt
from services.quiz_service import generate_quiz
from services.recommendation_service import rank_recommendations
from services.roadmap_service import get_or_create_roadmap
from utils.topic_validator import canonicalize_concept_name, logger


# Application-level cache for expensive 300-700 word university professor lectures
LECTURE_CACHE = {}


def clean_json_text(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()
    start = text.find("{")
    end = text.rfind("}")
    return text[start : end + 1] if start != -1 and end != -1 else text


def get_or_create_topic_lecture(topic):
    clean_t = canonicalize_concept_name(topic)
    cache_key = clean_t.lower()

    if cache_key in LECTURE_CACHE:
        logger.info(f"[VALIDATION] Retrieved lecture for '{clean_t}' from application-level cache.")
        return LECTURE_CACHE[cache_key]

    system_prompt, user_prompt = build_topic_lecture_prompt(clean_t)
    response_text, error = safe_groq_generate(system_prompt, user_prompt, max_tokens=2500)

    if error:
        logger.error(f"[AI RESPONSE] Topic lecture generation failed for '{clean_t}': {error}")
        lecture_data = generate_fallback_lecture(clean_t)
        LECTURE_CACHE[cache_key] = lecture_data
        return lecture_data

    try:
        logger.info(f"[JSON PARSING] Parsing JSON for university professor lecture on '{clean_t}'...")
        lecture_data = json.loads(clean_json_text(response_text))
        logger.info(f"[JSON PARSING] Success parsing lecture JSON for '{clean_t}'.")
    except (json.JSONDecodeError, TypeError) as exc:
        logger.error(f"[JSON PARSING] Failed parsing lecture JSON for '{clean_t}': {exc}")
        lecture_data = generate_fallback_lecture(clean_t)
        LECTURE_CACHE[cache_key] = lecture_data
        return lecture_data

    formatted_explanation = format_rich_lecture_explanation(lecture_data)
    lecture_data["explanation"] = formatted_explanation
    LECTURE_CACHE[cache_key] = lecture_data

    return lecture_data


def generate_fallback_lecture(topic):
    clean_t = canonicalize_concept_name(topic)
    return {
        "topic": clean_t,
        "definition": f"{clean_t} is a fundamental educational concept in this domain.",
        "intuition": f"Think of {clean_t} as a building block that simplifies complex data operations.",
        "motivation": f"Computer scientists and engineers master {clean_t} to design efficient software systems.",
        "real_world_analogy": f"Using {clean_t} is like organizing tools in a labeled workshop drawer.",
        "step_by_step_explanation": f"1. Initialize {clean_t}.\n2. Execute core operations.\n3. Manage memory and resources.",
        "examples": f"Practical exercises demonstrating {clean_t} usage.",
        "applications": f"Production applications in databases, operating systems, and web services.",
        "advantages": "Fast lookups, modularity, and structured data handling.",
        "limitations": "Requires initial configuration and memory overhead.",
        "time_and_space_complexity": "Time Complexity: O(1) to O(N). Space Complexity: O(N).",
        "common_mistakes": "Forgetting boundary checks or ignoring resource deallocation.",
        "interview_questions": f"1. Explain how {clean_t} works.\n2. Compare {clean_t} with alternative data structures.",
        "revision_summary": f"{clean_t} organizes data efficiently and forms a core computer science foundation.",
        "learning_tips": "Implement a simple working example from scratch to build muscle memory.",
        "explanation": f"Definition: {clean_t} is a fundamental educational concept in this domain.",
    }


def format_rich_lecture_explanation(data):
    sections = [
        f"Simple Definition: {data.get('definition', '')}",
        f"Intuition & Mental Model: {data.get('intuition', '')}",
        f"Why It Matters: {data.get('motivation', '')}",
        f"Real-World Analogy: {data.get('real_world_analogy', '')}",
        f"Step-by-Step Working: {data.get('step_by_step_explanation', '')}",
        f"Example Breakdown: {data.get('examples', '')}",
        f"Industry Applications: {data.get('applications', '')}",
        f"Key Advantages: {data.get('advantages', '')}",
        f"Limitations & Drawbacks: {data.get('limitations', '')}",
        f"Time & Space Complexity: {data.get('time_and_space_complexity', '')}",
        f"Common Student Mistakes: {data.get('common_mistakes', '')}",
        f"Interview Questions: {data.get('interview_questions', '')}",
        f"Revision Summary: {data.get('revision_summary', '')}",
        f"Learning Tips: {data.get('learning_tips', '')}",
    ]
    return "\n\n".join(s for s in sections if len(s.split(": ", 1)[-1].strip()) > 0)


def infer_topic_from_text(text):
    system_prompt = "You extract one main educational topic. Return only the topic name."
    user_prompt = f"Identify the ONE main study topic from this text:\n\n{text[:4000]}"
    response_text, error = safe_groq_generate(system_prompt, user_prompt, max_tokens=80)

    if error:
        logger.error(f"[AI RESPONSE] Main topic inference failed: {error}")
        return "Uploaded PDF"

    return (response_text or "Uploaded PDF").strip().strip('"')


def process_input(topic=None, text=None):
    if text:
        topic = infer_topic_from_text(text)
        context_text = text
    else:
        context_text = topic or ""
        topic = topic or "Learning Topic"

    roadmap = get_or_create_roadmap(topic, context_text)
    lecture = get_or_create_topic_lecture(roadmap["topic"])

    # Collect raw candidates from roadmap tiers
    raw_before = [item for item in roadmap.get("prerequisites", [])]
    raw_after = [item for item in roadmap.get("next_topics", [])]
    raw_related = [item for item in roadmap.get("related_topics", [])]

    # Include roadmap intermediate/advanced topics as potential successor candidates if needed
    for item in roadmap.get("intermediate_topics", []) + roadmap.get("advanced_topics", []):
        if isinstance(item, dict) and item.get("topic"):
            raw_after.append({"topic": item["topic"], "relation": "NEXT_TOPIC", "why": item.get("why", "")})

    # Retrieve graph relationships from Neo4j
    neo4j_records = fetch_raw_suggestions_from_neo4j(roadmap["topic"])
    if neo4j_records:
        g_item = neo4j_records[0]
        raw_before.extend(g_item.get("before", []))
        raw_after.extend(g_item.get("after", []))

    # Rank recommendations via recommendation_service.py
    ranked_before = rank_recommendations(raw_before, roadmap["topic"], limit=5)
    ranked_after = rank_recommendations(raw_after, roadmap["topic"], limit=5)
    ranked_related = rank_recommendations(raw_related, roadmap["topic"], limit=5)

    quiz_context = "\n".join(
        [
            lecture.get("explanation", ""),
            lecture.get("real_world_analogy", ""),
            "Prerequisites: " + ", ".join(item["topic"] for item in ranked_before),
            "Next topics: " + ", ".join(item["topic"] for item in ranked_after),
        ]
    )

    quiz_data = generate_quiz(roadmap["topic"], quiz_context)
    latest_quiz.clear()
    latest_quiz.extend(quiz_data)

    result = {
        "topic": roadmap["topic"],
        "summary": lecture.get("explanation"),
        "analogy": lecture.get("real_world_analogy"),
        "definition": lecture.get("definition"),
        "why_it_matters": lecture.get("motivation") or lecture.get("why_it_matters"),
        "example": lecture.get("examples"),
        "difficulty": roadmap.get("difficulty"),
        "estimated_time": roadmap.get("estimated_study_time"),
        "before": ranked_before[:5],
        "after": ranked_after[:5],
        "related": ranked_related[:5],
        "quiz": quiz_data,
        "cached": roadmap.get("cached", False),
    }
    latest_result.clear()
    latest_result.update(result)

    return result
