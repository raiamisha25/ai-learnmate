import json
import re

import networkx as nx

from services.groq_service import safe_groq_generate
from services.prompt_builders import (
    build_relationship_extraction_prompt,
    build_topic_extraction_prompt,
)
from utils.topic_validator import (
    canonicalize_concept_name,
    is_valid_relationship,
    is_valid_topic,
    logger,
    validate_concepts,
)


STOP_WORDS = {
    "about", "after", "also", "because", "before", "between", "could",
    "depend", "depends", "explain", "explains", "from", "have", "into",
    "more", "most", "other", "should", "such", "summary", "their",
    "there", "these", "this", "that", "they", "through", "used",
    "using", "when", "where", "which", "while", "with", "would",
    "and", "are", "can", "for", "has", "the", "was", "will",
}


def clean_json_object(text):
    text = (text or "").strip()
    start = text.find("{")
    end = text.rfind("}")
    return text[start : end + 1] if start != -1 and end != -1 and end > start else ""


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
    system_prompt, user_prompt = build_topic_extraction_prompt(text)
    response_text, error = safe_groq_generate(system_prompt, user_prompt, max_tokens=1200)

    if error:
        logger.error(f"[AI RESPONSE] Concept extraction failed: {error}")
        return []

    logger.info("[AI RESPONSE] Concept extraction raw response received.")

    try:
        logger.info("[JSON PARSING] Attempting to parse JSON for AI concept extraction...")
        data = json.loads(clean_json_object(response_text))
        logger.info("[JSON PARSING] Success parsing JSON for AI concept extraction.")
    except (json.JSONDecodeError, TypeError) as exc:
        logger.error(f"[JSON PARSING] Failed parsing JSON for AI concept extraction: {exc}")
        return []

    concepts = data.get("concepts", []) if isinstance(data, dict) else []
    if not isinstance(concepts, list):
        return []

    return validate_concepts(concepts, limit=10)


def extract_fallback_concepts(summary):
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
        concept = canonicalize_concept_name(phrase)

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

    system_prompt, user_prompt = build_relationship_extraction_prompt(summary, concepts)
    response_text, error = safe_groq_generate(system_prompt, user_prompt, max_tokens=1000)

    if error:
        logger.error(f"[AI RESPONSE] Relationship classification failed: {error}")
        return []

    logger.info("[AI RESPONSE] Relationship classification raw response received.")

    try:
        logger.info("[JSON PARSING] Attempting to parse JSON for AI relationship classification...")
        data = json.loads(clean_json_object(response_text))
        logger.info("[JSON PARSING] Success parsing JSON for AI relationship classification.")
    except (json.JSONDecodeError, TypeError) as exc:
        logger.error(f"[JSON PARSING] Failed parsing JSON for AI relationship classification: {exc}")
        return []

    relationships = data.get("relationships", []) if isinstance(data, dict) else []
    if not isinstance(relationships, list):
        return []

    clean_relationships = []
    seen_relationships = set()

    for relationship in relationships:
        if not isinstance(relationship, dict):
            continue

        raw_subj = str(relationship.get("subject", "")).strip()
        raw_obj = str(relationship.get("object", "")).strip()
        relation = str(relationship.get("relation", "")).strip().upper()
        why = str(relationship.get("why", "")).strip()

        subject = canonicalize_concept_name(raw_subj)
        object_name = canonicalize_concept_name(raw_obj)

        if not why or len(why) < 10:
            why = f"{subject} relates to {object_name} in learning order."

        is_rel_valid, rel_reason = is_valid_relationship(subject, object_name, relation, why, seen_relationships)
        if not is_rel_valid:
            logger.info(f"[RELATIONSHIP VALIDATION] Edge '{subject}' -[{relation}]-> '{object_name}' rejected: {rel_reason}")
            continue

        relationship_key = (subject.lower(), relation, object_name.lower())
        seen_relationships.add(relationship_key)

        logger.info(f"[RELATIONSHIP VALIDATION] Validated edge: '{subject}' -[{relation}]-> '{object_name}'")
        clean_relationships.append(
            {"subject": subject, "relation": relation, "object": object_name, "why": why}
        )

    return clean_relationships


def build_knowledge_graph(summary):
    concepts = validate_concepts(extract_key_concepts(summary), limit=10)
    graph = nx.MultiDiGraph()

    for index, concept in enumerate(concepts):
        graph.add_node(concept, important=index < 5)

    edges = classify_relationships_with_ai(summary, concepts)

    for edge in edges:
        graph.add_edge(edge["subject"], edge["object"], relation=edge["relation"], why=edge.get("why", ""))

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
