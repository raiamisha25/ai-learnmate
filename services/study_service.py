import re

from models.state import knowledge_graph, latest_quiz, latest_result
from services.concept_service import (
    build_knowledge_graph,
    clean_concept_name,
    infer_main_topic,
)
from services.gemini_service import safe_generate
from services.neo4j_service import (
    clean_topic_list,
    fetch_suggestions_for_topic,
    save_graph_to_neo4j,
    save_topic_suggestions,
)
from services.quiz_service import generate_quiz


def summarize_text(text):
    prompt = f"""
Summarize the following PDF text in simple terms.
Use short paragraphs and bullet points where helpful.

PDF text:
{text[:8000]}
"""
    response_text, error = safe_generate(prompt)

    if error:
        print(f"Summary generation failed: {error}")
        return error

    if not response_text:
        print("Summary generation failed: Gemini returned an empty response.")
        return "Gemini returned an empty response. Please try again."

    return response_text


def generate_simple_explanation(topic, context_text=None):
    prompt = f"""
Explain "{topic}" in simple beginner-friendly language.
Keep it short, clear, and useful for revision.

Context:
{(context_text or topic)[:5000]}
"""
    response_text, error = safe_generate(prompt)

    if error:
        print(f"Simple explanation generation failed for '{topic}': {error}")
        return context_text or f"Study {topic} step by step."

    if not response_text:
        print(f"Simple explanation generation failed for '{topic}': empty AI response")
        return context_text or f"Study {topic} step by step."

    return response_text


def parse_ai_topic_suggestions(text):
    before = []
    after = []
    mode = None

    for line in (text or "").splitlines():
        clean_line = line.strip()
        lower_line = clean_line.lower()

        if "prerequisite" in lower_line or "before" in lower_line:
            mode = "before"
        elif "next" in lower_line or "after" in lower_line:
            mode = "after"
        elif clean_line.startswith(("-", "*")) and mode:
            topic_name = clean_line.lstrip("-* ").strip()
            topic_name = re.sub(r"^\d+[\).\s]+", "", topic_name).strip()

            if topic_name:
                if mode == "before":
                    before.append(clean_concept_name(topic_name))
                elif mode == "after":
                    after.append(clean_concept_name(topic_name))

    return clean_topic_list(before)[:5], clean_topic_list(after)[:5]


def generate_topic_suggestions_with_ai(topic):
    prompt = f"""
For the topic "{topic}", give:
1. Prerequisites (topics to learn before)
2. Next topics (what to learn after)

Keep answers short (max 5 each).
Use bullet points under headings "Before" and "After".
"""
    response_text, error = safe_generate(prompt)

    if error:
        print(f"Topic suggestions generation failed for '{topic}': {error}")
        return [], []

    if not response_text:
        print(f"Topic suggestions generation failed for '{topic}': empty AI response")
        return [], []

    return parse_ai_topic_suggestions(response_text or "")


def generate_topic_plan(topic, context_text=None):
    """Generate the main parts of a study plan with visible fallback logging."""
    try:
        summary = generate_simple_explanation(topic, context_text)
        _clean_topic, before, after = get_or_create_topic_suggestions(topic)
        return {"summary": summary, "before": before, "after": after}
    except Exception as exc:
        print(f"Topic plan generation failed for '{topic}': {exc}")
        return {
            "summary": context_text or f"Study {topic} step by step.",
            "before": [],
            "after": [],
        }


def get_or_create_topic_suggestions(topic):
    clean_topic = clean_concept_name(topic)
    before, after = fetch_suggestions_for_topic(clean_topic)

    if before or after:
        return clean_topic, before, after

    before, after = generate_topic_suggestions_with_ai(clean_topic)

    if before or after:
        save_topic_suggestions(clean_topic, before, after)

    return clean_topic, before, after


def process_input(topic=None, text=None):
    summary = None
    context_text = text

    if text:
        summary = summarize_text(text)
        topic = infer_main_topic(summary or text)
        context_text = summary
        graph_data = build_knowledge_graph(summary or text)
        knowledge_graph.update(graph_data)
        save_graph_to_neo4j(graph_data)
    elif topic:
        topic = clean_concept_name(topic)
        summary = generate_simple_explanation(topic)
        context_text = summary
    else:
        topic = "Learning Topic"
        summary = "No topic or PDF content was provided."

    topic, before, after = get_or_create_topic_suggestions(topic)

    quiz_data = generate_quiz(topic, context_text)
    latest_quiz.clear()
    latest_quiz.extend(quiz_data)

    result = {
        "topic": topic,
        "summary": summary,
        "before": before[:5],
        "after": after[:5],
        "quiz": quiz_data,
    }
    latest_result.clear()
    latest_result.update(result)

    return result
