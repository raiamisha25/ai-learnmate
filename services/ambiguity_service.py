import json

from services.groq_service import safe_groq_generate
from utils.topic_validator import normalize_topic_name


DEFAULT_AMBIGUOUS_TOPICS = {
    "tree": ["Binary Tree", "AVL Tree", "Decision Tree", "Biological Tree"],
    "python": ["Python Programming", "Python Data Analysis"],
    "java": ["Java Programming", "Java Collections"],
}


def clean_json_object_text(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()
    start = text.find("{")
    end = text.rfind("}")
    return text[start : end + 1] if start != -1 and end != -1 else text


def fallback_ambiguity(topic):
    options = DEFAULT_AMBIGUOUS_TOPICS.get(topic.lower())

    if options:
        return {"ambiguous": True, "options": options, "error": None}

    return {"ambiguous": False, "options": [normalize_topic_name(topic)], "error": None}


def check_topic_ambiguity(topic):
    system_prompt = "You detect topic ambiguity for an educational learning app. Return JSON only."
    user_prompt = f"""
The topic "{topic}" may have multiple meanings.

Return JSON only:
{{
  "ambiguous": true,
  "options": ["specific educational meaning 1", "specific educational meaning 2"]
}}

If the topic is clearly academic and specific, set ambiguous=false.
For "tree", include Binary Tree, AVL Tree, Decision Tree, and Biological Tree.
"""
    response_text, error = safe_groq_generate(system_prompt, user_prompt, max_tokens=500)

    if error:
        print(f"Ambiguity detection failed for '{topic}': {error}")
        return fallback_ambiguity(topic)

    try:
        data = json.loads(clean_json_object_text(response_text or "{}"))
    except (json.JSONDecodeError, TypeError, AttributeError) as exc:
        print(f"Ambiguity detection failed for '{topic}': could not parse JSON: {exc}")
        return fallback_ambiguity(topic)

    clean_options = []

    for option in data.get("options", []):
        if isinstance(option, str):
            clean_option = normalize_topic_name(option)
            if clean_option and clean_option not in clean_options:
                clean_options.append(clean_option)

    if bool(data.get("ambiguous")) and len(clean_options) > 1:
        return {"ambiguous": True, "options": clean_options[:4], "error": None}

    return {
        "ambiguous": False,
        "options": clean_options[:1] or [normalize_topic_name(topic)],
        "error": None,
    }
