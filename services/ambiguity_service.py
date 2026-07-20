"""
ambiguity_service.py

Responsible ONLY for:
- Detecting topic ambiguity for broad educational terms
- Resolving ambiguous user inputs into distinct (label, canonical_topic, domain) options
- Bypassing ambiguity resolution for specific academic terms

Neo4j and canonical educational concepts remain the single source of truth.
No hardcoded subject lookup tables exist for educational content.
"""

import json

from services.groq_service import safe_groq_generate
from utils.topic_validator import canonicalize_concept_name, logger


DEFAULT_AMBIGUOUS_TOPICS = {
    "list": [
        {"label": "Data Structure List", "canonical": "Linked List", "domain": "Computer Science"},
        {"label": "Python List Data Type", "canonical": "Python List", "domain": "Computer Science"},
        {"label": "HTML Ordered / Unordered List", "canonical": "HTML List", "domain": "Web Development"},
    ],
    "tree": [
        {"label": "Binary Tree Data Structure", "canonical": "Binary Tree", "domain": "Computer Science"},
        {"label": "Decision Tree Machine Learning", "canonical": "Decision Tree", "domain": "Machine Learning"},
        {"label": "Abstract Syntax Tree", "canonical": "Syntax Tree", "domain": "Compilers"},
    ],
    "network": [
        {"label": "Computer Networks & Protocols", "canonical": "Computer Networks", "domain": "Computer Science"},
        {"label": "Artificial Neural Network", "canonical": "Neural Network", "domain": "Machine Learning"},
        {"label": "Social Graph Network", "canonical": "Social Network", "domain": "Data Science"},
    ],
    "kernel": [
        {"label": "Operating System Kernel", "canonical": "Operating System Kernel", "domain": "Operating Systems"},
        {"label": "Kernel Method (Machine Learning)", "canonical": "Kernel Method", "domain": "Machine Learning"},
        {"label": "Linux Kernel Architecture", "canonical": "Linux Kernel", "domain": "Systems"},
    ],
    "graph": [
        {"label": "Graph Data Structure & Algorithms", "canonical": "Graph", "domain": "Computer Science"},
        {"label": "Graph Theory (Mathematics)", "canonical": "Graph Theory", "domain": "Mathematics"},
        {"label": "Knowledge Graph & Ontologies", "canonical": "Knowledge Graph", "domain": "Artificial Intelligence"},
    ],
    "python": [
        {"label": "Python Programming Language", "canonical": "Python Programming", "domain": "Software Development"},
        {"label": "Python Data Analysis & Science", "canonical": "Python Data Analysis", "domain": "Data Science"},
    ],
    "java": [
        {"label": "Java Programming Fundamentals", "canonical": "Java Programming", "domain": "Software Development"},
        {"label": "Java Collections Framework", "canonical": "Collections Framework", "domain": "Java Development"},
    ],
}

SPECIFIC_ACADEMIC_TOPICS = {
    "binary tree", "quick sort", "arraylist", "depth first search", "recursion",
    "avl tree", "logistic regression", "linear regression", "breadth first search",
    "linked list", "doubly linked list", "circular linked list", "dynamic programming",
    "process scheduling", "memory management", "file systems", "binary search tree",
    "random forest", "gradient descent", "neural network", "decision tree",
    "collections framework", "hashmap", "hashset", "call stack", "computer networks",
}


def clean_json_object_text(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()
    start = text.find("{")
    end = text.rfind("}")
    return text[start : end + 1] if start != -1 and end != -1 else text


def fallback_ambiguity(topic):
    clean_t = canonicalize_concept_name(topic)
    options = DEFAULT_AMBIGUOUS_TOPICS.get(topic.lower()) or DEFAULT_AMBIGUOUS_TOPICS.get(clean_t.lower())

    if options:
        return {"ambiguous": True, "options": options, "error": None}

    single_option = {"label": clean_t, "canonical": clean_t, "domain": "General"}
    return {"ambiguous": False, "options": [single_option], "error": None}


def check_topic_ambiguity(topic):
    clean_t = canonicalize_concept_name(topic)
    lower_t = clean_t.lower()

    # 1. Specific Academic Topic Bypass
    if lower_t in SPECIFIC_ACADEMIC_TOPICS or (len(clean_t.split()) >= 2 and lower_t not in DEFAULT_AMBIGUOUS_TOPICS):
        logger.info(f"[VALIDATION] Ambiguity bypassed for specific topic '{clean_t}'.")
        single_opt = {"label": clean_t, "canonical": clean_t, "domain": "Specific Topic"}
        return {"ambiguous": False, "options": [single_opt], "error": None}

    # Check default dictionary mapping
    if lower_t in DEFAULT_AMBIGUOUS_TOPICS:
        logger.info(f"[VALIDATION] Ambiguity matched for term '{clean_t}'.")
        return {"ambiguous": True, "options": DEFAULT_AMBIGUOUS_TOPICS[lower_t], "error": None}

    system_prompt = """
You detect topic ambiguity for an educational learning platform.
Return ONLY valid JSON. Do not include markdown or prose.
Identify if a topic has multiple distinct academic/domain meanings.
Each option MUST pair a user-friendly UI display label with its exact canonical educational topic.
"""
    user_prompt = f"""
The user searched for: "{clean_t}"

If this topic is broad and has multiple distinct domain meanings (e.g. "Tree" can mean Binary Tree, Decision Tree, Syntax Tree, or Biological Tree), return ambiguous=true with distinct options containing:
- label: UI display label (e.g. "Data Structure List")
- canonical: Exact canonical topic identifier (e.g. "Linked List")
- domain: Academic domain (e.g. "Computer Science")

If the topic is already specific (e.g. "Binary Tree", "ArrayList", "Quick Sort", "Depth First Search"), set ambiguous=false.

Return ONLY JSON:
{{
  "ambiguous": true | false,
  "options": [
    {{
      "label": "Display Label 1",
      "canonical": "Canonical Topic 1",
      "domain": "Domain 1"
    }},
    {{
      "label": "Display Label 2",
      "canonical": "Canonical Topic 2",
      "domain": "Domain 2"
    }}
  ]
}}
"""
    response_text, error = safe_groq_generate(system_prompt, user_prompt, max_tokens=400)

    if error:
        logger.error(f"[AI RESPONSE] Ambiguity detection failed for '{clean_t}': {error}")
        return fallback_ambiguity(clean_t)

    try:
        data = json.loads(clean_json_object_text(response_text or "{}"))
    except (json.JSONDecodeError, TypeError, AttributeError) as exc:
        logger.error(f"[JSON PARSING] Ambiguity detection failed for '{clean_t}': {exc}")
        return fallback_ambiguity(clean_t)

    clean_options = []
    seen_canonicals = set()

    for item in data.get("options", []):
        if isinstance(item, dict):
            lbl = item.get("label") or item.get("canonical")
            can = canonicalize_concept_name(item.get("canonical") or lbl)
            dom = item.get("domain") or "General"

            if can and can.lower() not in seen_canonicals:
                seen_canonicals.add(can.lower())
                clean_options.append({"label": lbl, "canonical": can, "domain": dom})
        elif isinstance(item, str):
            can = canonicalize_concept_name(item)
            if can and can.lower() not in seen_canonicals:
                seen_canonicals.add(can.lower())
                clean_options.append({"label": can, "canonical": can, "domain": "General"})

    if bool(data.get("ambiguous")) and len(clean_options) > 1:
        logger.info(f"[VALIDATION] Ambiguity detected for broad term '{clean_t}': {[opt['canonical'] for opt in clean_options[:4]]}")
        return {"ambiguous": True, "options": clean_options[:4], "error": None}

    fallback_opt = clean_options[0] if clean_options else {"label": clean_t, "canonical": clean_t, "domain": "General"}
    return {
        "ambiguous": False,
        "options": [fallback_opt],
        "error": None,
    }
