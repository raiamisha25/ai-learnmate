import json

from services.concept_service import clean_concept_name
from services.gemini_service import clean_json_object_text, safe_generate


DEFAULT_AMBIGUOUS_TOPICS = {
    "tree": ["Binary Tree", "AVL Tree", "Decision Tree", "Biological Tree"],
    "python": ["Python Programming", "Python Snake", "Python Data Analysis"],
    "java": ["Java Programming", "Java Island", "Java Coffee"],
}


def fallback_ambiguity(topic):
    options = DEFAULT_AMBIGUOUS_TOPICS.get(topic.lower())

    if options:
        return {"ambiguous": True, "options": options, "error": None}

    return {"ambiguous": False, "options": [clean_concept_name(topic)], "error": None}


def check_topic_ambiguity(topic):
    prompt = f"""
The topic "{topic}" may have multiple meanings.

Return JSON format:
{{
  "ambiguous": true,
  "options": [
    "option1",
    "option2"
  ]
}}

If topic is clearly academic and specific,
set ambiguous=false.
"""
    response_text, error = safe_generate(prompt)

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
            clean_option = clean_concept_name(option)
            if clean_option and clean_option not in clean_options:
                clean_options.append(clean_option)

    if bool(data.get("ambiguous")) and len(clean_options) > 1:
        return {"ambiguous": True, "options": clean_options[:3], "error": None}

    return {
        "ambiguous": False,
        "options": clean_options[:1] or [clean_concept_name(topic)],
        "error": None,
    }
