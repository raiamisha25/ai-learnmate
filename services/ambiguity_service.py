import json

from services.groq_service import safe_groq_generate
from utils.topic_validator import canonicalize_concept_name, logger


DEFAULT_AMBIGUOUS_TOPICS = {
    "tree": ["Binary Tree", "Decision Tree", "Syntax Tree", "Biological Tree"],
    "network": ["Computer Networks", "Neural Network", "Social Network"],
    "kernel": ["Operating System Kernel", "Kernel Method (Machine Learning)", "Linux Kernel"],
    "graph": ["Graph Data Structure", "Graph Theory", "Knowledge Graph"],
    "python": ["Python Programming", "Python Data Analysis"],
    "java": ["Java Programming", "Java Collections"],
}

SPECIFIC_ACADEMIC_TOPICS = {
    "binary tree", "quick sort", "arraylist", "depth first search", "recursion",
    "avl tree", "logistic regression", "linear regression", "breadth first search",
    "linked list", "doubly linked list", "circular linked list", "dynamic programming",
    "process scheduling", "memory management", "file systems", "binary search tree",
    "random forest", "gradient descent", "neural network", "decision tree",
    "collections framework", "hashmap", "hashset", "call stack",
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

    return {"ambiguous": False, "options": [canonicalize_concept_name(topic)], "error": None}


def check_topic_ambiguity(topic):
    clean_t = canonicalize_concept_name(topic)
    lower_t = clean_t.lower()

    # 1. Specific Academic Topic Bypass
    if lower_t in SPECIFIC_ACADEMIC_TOPICS or len(clean_t.split()) >= 2:
        # Check if it's explicitly ambiguous like "tree"
        if lower_t not in DEFAULT_AMBIGUOUS_TOPICS:
            logger.info(f"[VALIDATION] Ambiguity bypassed for specific topic '{clean_t}'.")
            return {"ambiguous": False, "options": [clean_t], "error": None}

    system_prompt = """
You detect topic ambiguity for an educational learning platform.
Return ONLY valid JSON. Do not include markdown or prose.
Identify if a topic has multiple distinct academic/domain meanings.
"""
    user_prompt = f"""
The user searched for: "{clean_t}"

If this topic is broad and has multiple distinct domain meanings (e.g. "Tree" can mean Binary Tree, Decision Tree, Syntax Tree, or Biological Tree), return ambiguous=true with distinct options.

If the topic is already specific (e.g. "Binary Tree", "ArrayList", "Quick Sort", "Depth First Search"), set ambiguous=false.

Return ONLY JSON:
{{
  "ambiguous": true | false,
  "options": ["Distinct Domain Meaning 1", "Distinct Domain Meaning 2"]
}}
"""
    response_text, error = safe_groq_generate(system_prompt, user_prompt, max_tokens=350)

    if error:
        logger.error(f"[AI RESPONSE] Ambiguity detection failed for '{clean_t}': {error}")
        return fallback_ambiguity(clean_t)

    try:
        data = json.loads(clean_json_object_text(response_text or "{}"))
    except (json.JSONDecodeError, TypeError, AttributeError) as exc:
        logger.error(f"[JSON PARSING] Ambiguity detection failed for '{clean_t}': {exc}")
        return fallback_ambiguity(clean_t)

    clean_options = []
    for option in data.get("options", []):
        if isinstance(option, str):
            opt_clean = canonicalize_concept_name(option)
            if opt_clean and opt_clean not in clean_options:
                clean_options.append(opt_clean)

    if bool(data.get("ambiguous")) and len(clean_options) > 1:
        logger.info(f"[VALIDATION] Ambiguity detected for broad term '{clean_t}': {clean_options[:4]}")
        return {"ambiguous": True, "options": clean_options[:4], "error": None}

    return {
        "ambiguous": False,
        "options": clean_options[:1] or [clean_t],
        "error": None,
    }
