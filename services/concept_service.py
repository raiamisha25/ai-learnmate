import json
import re

import networkx as nx

from services.groq_service import safe_groq_generate
from utils.topic_validator import validate_concepts


STOP_WORDS = {
    "about", "after", "also", "because", "before", "between", "could",
    "depend", "depends", "explain", "explains", "from", "have", "into",
    "more", "most", "other", "should", "such", "summary", "their",
    "there", "these", "this", "that", "they", "through", "used",
    "using", "when", "where", "which", "while", "with", "would",
    "and", "are", "can", "for", "has", "the", "was", "will",
}


CONCEPT_EXTRACTION_SYSTEM_PROMPT = """
You extract learning concepts from study material.
Return ONLY valid JSON. Do not include markdown, prose, or comments.
Only include domain-specific educational concepts, not random English words.
"""

ALLOWED_RELATIONSHIPS = {
    "PREREQUISITE",
    "NEXT_TOPIC",
    "PART_OF",
    "USES",
    "APPLICATION_OF",
    "COMPARES_WITH",
    "RELATED_TO",
}

RELATIONSHIP_CLASSIFICATION_SYSTEM_PROMPT = """
You classify relationships between learning concepts.
Return ONLY valid JSON. Do not include markdown, prose, or comments.
Use only the allowed relationship labels.
"""


def clean_json_object(text):
    text = (text or "").strip()
    start = text.find("{")
    end = text.rfind("}")
    return text[start : end + 1] if start != -1 and end != -1 and end > start else ""


def clean_concept_name(text):
    return " ".join(word.capitalize() for word in (text or "").split())


def is_meaningful_phrase(words):
    return (
        len(words) >= 2
        and not any(word in STOP_WORDS for word in words)
        and all(len(word) > 2 for word in words)
    )


def add_phrases_from_chunk(chunk, phrase_counts):
    for phrase_size in (2, 3):
        for index in range(len(chunk) - phrase_size + 1):
            phrase_words = chunk[index : index + phrase_size]

            if is_meaningful_phrase(phrase_words):
                phrase = " ".join(phrase_words)
                phrase_counts[phrase] = phrase_counts.get(phrase, 0) + 1


def extract_concepts_with_ai(text):
    user_prompt = f"""
Extract the important learning concepts from this study material.

Return ONLY JSON in this exact shape:
{{
  "concepts": [
    {{
      "name": "ArrayList",
      "definition": "short definition",
      "importance": "why it matters",
      "prerequisites": ["related prerequisite concept"],
      "next_topics": ["meaningful next concept"]
    }}
  ]
}}

Rules:
- Include only domain-specific concepts, such as ArrayList, Linked List, Binary Tree, Heap, Graph, DFS, Gradient Descent, Random Forest, Cell, Mitochondria, or DNA.
- Do not include common English words, pronouns, UI words, verbs, adjectives, or sentence fragments.
- Reject words like Learn, Your, Environment, Initial, Important, Example, Simple, Next, Topic, Step, Continue, Before, After, This, That, Understanding, Elements, and Size.
- If there are no clear domain concepts, return {{"concepts":[]}}.

Study material:
{(text or "")[:7000]}
"""
    response_text, error = safe_groq_generate(
        CONCEPT_EXTRACTION_SYSTEM_PROMPT,
        user_prompt,
        max_tokens=1200,
    )

    if error:
        print(f"AI concept extraction failed: {error}")
        return []

    try:
        data = json.loads(clean_json_object(response_text))
    except (json.JSONDecodeError, TypeError) as exc:
        print(f"AI concept extraction returned invalid JSON: {exc}")
        return []

    concepts = data.get("concepts", []) if isinstance(data, dict) else []
    if not isinstance(concepts, list):
        return []

    return validate_concepts(concepts, limit=10)


def extract_fallback_concepts(summary):
    """Extract multi-word study topics such as Linked List or Binary Tree."""
    phrase_counts = {}
    sentences = re.split(r"[.!?;:\n]+", (summary or "").lower())

    for sentence in sentences:
        words = re.findall(r"\b[A-Za-z][A-Za-z-]{2,}\b", sentence)
        chunk = []

        for word in words:
            if word in STOP_WORDS:
                if len(chunk) >= 2:
                    add_phrases_from_chunk(chunk, phrase_counts)
                chunk = []
            else:
                chunk.append(word)

        if len(chunk) >= 2:
            add_phrases_from_chunk(chunk, phrase_counts)

    sorted_phrases = sorted(
        phrase_counts.items(),
        key=lambda item: (item[1], -len(item[0].split())),
        reverse=True,
    )

    concepts = []

    for phrase, _count in sorted_phrases:
        concept = clean_concept_name(phrase)

        if concept not in concepts:
            concepts.append(concept)

        if len(concepts) == 10:
            break

    return validate_concepts(concepts, limit=10)


def extract_key_concepts(summary):
    concepts = extract_concepts_with_ai(summary)
    return concepts or extract_fallback_concepts(summary)


def classify_relationships_with_ai(summary, concepts):
    if len(concepts) < 2:
        return []

    user_prompt = f"""
Classify meaningful relationships between these learning concepts.

Allowed relationship labels:
- PREREQUISITE
- NEXT_TOPIC
- PART_OF
- USES
- APPLICATION_OF
- COMPARES_WITH
- RELATED_TO

Return ONLY JSON in this exact shape:
{{
  "relationships": [
    {{"subject": "Binary Tree", "relation": "PREREQUISITE", "object": "Tree"}},
    {{"subject": "Heap", "relation": "RELATED_TO", "object": "Priority Queue"}},
    {{"subject": "Random Forest", "relation": "PREREQUISITE", "object": "Decision Tree"}}
  ]
}}

Rules:
- Use only the concepts listed below as subject and object values.
- Store the relation as exactly one of the allowed labels.
- Do not invent relationship labels.
- Do not create relationships just because concepts appear next to each other.
- Include only relationships that are supported by the study material or by standard educational dependency.
- If no meaningful relationship exists, return {{"relationships":[]}}.

Concepts:
{json.dumps(concepts)}

Study material:
{(summary or "")[:7000]}
"""
    response_text, error = safe_groq_generate(
        RELATIONSHIP_CLASSIFICATION_SYSTEM_PROMPT,
        user_prompt,
        max_tokens=1000,
    )

    if error:
        print(f"AI relationship classification failed: {error}")
        return []

    try:
        data = json.loads(clean_json_object(response_text))
    except (json.JSONDecodeError, TypeError) as exc:
        print(f"AI relationship classification returned invalid JSON: {exc}")
        return []

    relationships = data.get("relationships", []) if isinstance(data, dict) else []
    if not isinstance(relationships, list):
        return []

    concept_lookup = {concept.lower(): concept for concept in concepts}
    clean_relationships = []
    seen_relationships = set()

    for relationship in relationships:
        if not isinstance(relationship, dict):
            continue

        subject = concept_lookup.get(str(relationship.get("subject", "")).strip().lower())
        object_name = concept_lookup.get(str(relationship.get("object", "")).strip().lower())
        relation = str(relationship.get("relation", "")).strip().upper()

        if not subject or not object_name or subject == object_name:
            continue
        if relation not in ALLOWED_RELATIONSHIPS:
            continue

        relationship_key = (subject, relation, object_name)
        if relationship_key in seen_relationships:
            continue

        seen_relationships.add(relationship_key)
        clean_relationships.append(
            {"subject": subject, "relation": relation, "object": object_name}
        )

    return clean_relationships


def build_knowledge_graph(summary):
    concepts = validate_concepts(extract_key_concepts(summary), limit=10)
    graph = nx.MultiDiGraph()

    for index, concept in enumerate(concepts):
        graph.add_node(concept, important=index < 5)

    edges = classify_relationships_with_ai(summary, concepts)

    for edge in edges:
        graph.add_edge(edge["subject"], edge["object"], relation=edge["relation"])

    triples = [
        (edge["subject"], edge["relation"], edge["object"])
        for edge in edges
    ]

    nodes = [
        {"name": node, "important": graph.nodes[node].get("important", False)}
        for node in graph.nodes
    ]

    return {"nodes": nodes, "edges": edges, "triples": triples}


def infer_main_topic(text):
    concepts = extract_key_concepts(text)
    return concepts[0] if concepts else "Uploaded PDF"

