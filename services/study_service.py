"""
study_service.py

Responsible ONLY for orchestrating the learning workflow:
- Coordinating roadmap generation
- Lazy on-demand lecture generation & application-level caching
- Coordinating semantic recommendation categorization and quiz service
"""

import json

from models.state import latest_quiz, latest_result
from services.groq_service import safe_groq_generate
from services.neo4j_service import fetch_raw_suggestions_from_neo4j
from services.prompt_builders import build_topic_lecture_prompt
from services.quiz_service import generate_quiz
from services.recommendation_service import categorize_and_rank_recommendations
from services.roadmap_service import get_or_create_roadmap
from utils.topic_validator import canonicalize_concept_name, logger


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
        logger.info(f"[JSON PARSING] Parsing JSON for 14-section university professor lecture on '{clean_t}'...")
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
    fallback = {
        "topic": clean_t,
        "definition": f"{clean_t} is a fundamental educational concept in computer science and engineering.",
        "why_it_matters": f"Understanding {clean_t} solves key resource management and data organization challenges.",
        "intuition": f"Think of {clean_t} as a building block that simplifies complex operations.",
        "real_world_analogy": f"Using {clean_t} is like organizing tools in a labeled workshop drawer.",
        "step_by_step_explanation": f"1. Initialize {clean_t}.\n2. Perform core operations.\n3. Clean up resources.",
        "visual_thinking": f"Imagine structured nodes or boxes connected in sequence representing {clean_t}.",
        "simple_example": f"Walking through a basic scenario using {clean_t} step by step.",
        "code_example": f"// Simple demonstration of {clean_t}\n// Line 1: Initialize\n// Line 2: Execute",
        "advantages": "Fast execution, modularity, and structured data handling.",
        "limitations": "Initial setup overhead and memory constraints.",
        "common_mistakes": "Ignoring edge cases or boundary conditions.",
        "interview_perspective": f"Explain the core mechanism of {clean_t} and its time complexity.",
        "summary": f"{clean_t} forms a critical academic and practical foundation.",
        "what_to_learn_next": f"Explore advanced variations and applications of {clean_t}.",
    }
    fallback["explanation"] = format_rich_lecture_explanation(fallback)
    return fallback


def format_rich_lecture_explanation(data):
    sections = [
        f"### 1. Simple Definition\n{data.get('definition', '')}",
        f"### 2. Why Do We Need It?\n{data.get('why_it_matters') or data.get('motivation', '')}",
        f"### 3. Intuition & Mental Model\n{data.get('intuition', '')}",
        f"### 4. Real-Life Analogy\n{data.get('real_world_analogy', '')}",
        f"### 5. Step-by-Step Working\n{data.get('step_by_step_explanation', '')}",
        f"### 6. Visual Thinking\n{data.get('visual_thinking', '')}",
        f"### 7. Simple Example\n{data.get('simple_example') or data.get('examples', '')}",
        f"### 8. Code Example\n{data.get('code_example', '')}",
        f"### 9. Key Advantages\n{data.get('advantages', '')}",
        f"### 10. Limitations & Drawbacks\n{data.get('limitations', '')}",
        f"### 11. Common Beginner Mistakes\n{data.get('common_mistakes', '')}",
        f"### 12. Interview Perspective\n{data.get('interview_perspective') or data.get('interview_questions', '')}",
        f"### 13. Summary & Recap\n{data.get('summary') or data.get('revision_summary', '')}",
        f"### 14. What To Learn Next\n{data.get('what_to_learn_next') or data.get('learning_tips', '')}",
    ]
    return "\n\n".join(s for s in sections if len(s.split("\n", 1)[-1].strip()) > 0)


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

    # Collect raw candidates by source direction and relationship type
    raw_candidates_by_source = {
        "before": [],
        "after": [],
        "related": [],
    }

    # Populate from roadmap tiers
    for item in roadmap.get("prerequisites", []) + roadmap.get("foundation_topics", []) + roadmap.get("beginner_topics", []):
        if isinstance(item, dict) and item.get("topic"):
            raw_candidates_by_source["before"].append({"topic": item["topic"], "relation": "PREREQUISITE_OF", "why": item.get("why", "")})

    for item in roadmap.get("next_topics", []) + roadmap.get("intermediate_topics", []) + roadmap.get("advanced_topics", []):
        if isinstance(item, dict) and item.get("topic"):
            raw_candidates_by_source["after"].append({"topic": item["topic"], "relation": "BUILDS_ON", "why": item.get("why", "")})

    for item in roadmap.get("related_topics", []) + roadmap.get("optional_reading", []):
        if isinstance(item, dict) and item.get("topic"):
            raw_candidates_by_source["related"].append({"topic": item["topic"], "relation": "RELATED_TO", "why": item.get("why", "")})

    # Retrieve graph relationships from Neo4j
    neo4j_records = fetch_raw_suggestions_from_neo4j(roadmap["topic"])
    if neo4j_records:
        g_item = neo4j_records[0]
        raw_candidates_by_source["before"].extend(g_item.get("before", []))
        raw_candidates_by_source["after"].extend(g_item.get("after", []))

    # Categorize and rank recommendations into distinct sections with cross-section deduplication
    categorized = categorize_and_rank_recommendations(
        raw_candidates_by_source, roadmap["topic"], limit=5
    )

    ranked_before = categorized["before"]
    ranked_after = categorized["after"]
    ranked_related = categorized["related"]
    ranked_applications = categorized["applications"]

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
        "example": lecture.get("examples") or lecture.get("simple_example"),
        "difficulty": roadmap.get("difficulty"),
        "estimated_time": roadmap.get("estimated_study_time"),
        "before": ranked_before,
        "after": ranked_after,
        "related": ranked_related,
        "applications": ranked_applications,
        "quiz": quiz_data,
        "cached": roadmap.get("cached", False),
    }
    latest_result.clear()
    latest_result.update(result)

    return result
