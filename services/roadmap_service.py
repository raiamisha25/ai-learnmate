import json

from services.groq_service import safe_groq_generate
from services.neo4j_service import fetch_roadmap_from_neo4j, save_roadmap_to_neo4j
from services.prompt_builders import (
    build_pdf_analysis_prompt,
    build_roadmap_prompt,
)
from utils.topic_validator import (
    KNOWN_EDUCATIONAL_TOPICS,
    audit_tracker,
    canonicalize_concept_name,
    filter_valid_topics,
    get_topic_validation_details,
    is_valid_relationship,
    is_valid_topic,
    logger,
    normalize_topic_name,
)


CURATED_ROADMAPS = {
    "ArrayList": {
        "topic": "ArrayList",
        "definition": "An ArrayList stores items in order and can grow dynamically when items are added.",
        "why_it_matters": "It makes changing list storage easy to manage in memory.",
        "example": "Like a playlist where you can keep adding songs without fixing a size upfront.",
        "explanation": "Definition: An ArrayList stores items in order and can grow dynamically.\nWhy It Matters: It makes changing list storage easy to manage in memory.\nReal World Example: Like a playlist where you can keep adding songs.",
        "difficulty": "Beginner",
        "estimated_study_time": "2-3 hours",
        "foundation_topics": [{"topic": "Arrays", "why": "ArrayList is built on indexed storage."}],
        "beginner_topics": [{"topic": "Object Oriented Programming", "why": "ArrayList methods are invoked on class objects."}],
        "intermediate_topics": [{"topic": "Linked List", "why": "Compares dynamic array vs node-based storage."}],
        "advanced_topics": [{"topic": "HashMap", "why": "Transition from index lookup to key-value hashing."}],
        "optional_reading": [{"topic": "Collections Framework", "why": "Explore Java interface hierarchies."}],
        "learning_milestones": ["Can instantiate ArrayList", "Understands dynamic resizing time complexity"],
        "prerequisites": [{"topic": "Arrays", "why": "ArrayList builds on array fundamentals."}],
        "next_topics": [{"topic": "Linked List", "why": "Shows another way to store ordered data."}],
        "related_topics": [{"topic": "Collections Framework", "why": "ArrayList belongs to Java collections."}],
    },
    "Binary Tree": {
        "topic": "Binary Tree",
        "definition": "A Binary Tree stores data in nodes where each node has at most two children.",
        "why_it_matters": "It forms the foundation for fast hierarchical searching, sorting, and decision charts.",
        "example": "Like a decision chart that branches into yes/no paths.",
        "explanation": "Definition: A Binary Tree stores data in nodes with up to two children.\nWhy It Matters: It forms the foundation for fast hierarchical searching and sorting.\nReal World Example: Like a yes/no decision chart.",
        "difficulty": "Intermediate",
        "estimated_study_time": "4-6 hours",
        "foundation_topics": [{"topic": "Recursion", "why": "Subtrees are processed recursively."}],
        "beginner_topics": [{"topic": "Linked List", "why": "Nodes connect using reference pointers."}],
        "intermediate_topics": [{"topic": "Tree Traversal", "why": "Learn Inorder, Preorder, and Postorder traversals."}],
        "advanced_topics": [{"topic": "AVL Tree", "why": "Self-balancing binary search trees."}],
        "optional_reading": [{"topic": "Heap", "why": "Priority queue implementation using trees."}],
        "learning_milestones": ["Can implement node structure", "Can traverse tree recursively"],
        "prerequisites": [{"topic": "Recursion", "why": "Tree algorithms rely on recursive sub-problems."}],
        "next_topics": [{"topic": "AVL Tree", "why": "AVL Trees maintain tree balance."}],
        "related_topics": [{"topic": "Tree Traversal", "why": "Visiting all nodes in defined order."}],
    },
}


def clean_json_object(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()
    start = text.find("{")
    end = text.rfind("}")
    return text[start : end + 1] if start != -1 and end != -1 else text


def fallback_roadmap(topic):
    clean_topic = canonicalize_concept_name(topic)
    return CURATED_ROADMAPS.get(
        clean_topic,
        {
            "topic": clean_topic,
            "definition": f"{clean_topic} is a key educational topic that provides essential foundational concepts.",
            "why_it_matters": "It builds a strong foundation for advanced problem solving.",
            "example": "Like mastering basic tools before building a larger system.",
            "explanation": f"Definition: {clean_topic} is an essential educational concept.\nWhy It Matters: It supports advanced learning.",
            "difficulty": "Beginner",
            "estimated_study_time": "3-5 hours",
            "foundation_topics": [],
            "beginner_topics": [],
            "intermediate_topics": [],
            "advanced_topics": [],
            "optional_reading": [],
            "learning_milestones": ["Understand core concept", "Solve basic exercises"],
            "prerequisites": [],
            "next_topics": [],
            "related_topics": [],
        },
    )


def validate_roadmap(data, requested_topic, is_from_pdf=False, context_text=None):
    logger.info(f"[VALIDATION] Starting roadmap validation for topic '{requested_topic}'...")

    raw_main_topic = data.get("topic") or requested_topic
    main_topic = canonicalize_concept_name(raw_main_topic)

    all_ai_topics = {main_topic.lower()}
    for key in ("prerequisites", "next_topics", "related_topics", "foundation_topics", "beginner_topics", "intermediate_topics", "advanced_topics"):
        for item in data.get(key, []):
            if isinstance(item, dict) and item.get("topic"):
                all_ai_topics.add(canonicalize_concept_name(item.get("topic")).lower())

    is_main_valid, main_reason = get_topic_validation_details(
        main_topic,
        pdf_text=context_text,
        ai_topics=all_ai_topics,
        curated_topics=KNOWN_EDUCATIONAL_TOPICS
    )

    if not is_main_valid:
        logger.info(f"[REJECTED CONCEPT] Main topic '{main_topic}' rejected: {main_reason}. Using requested topic.")
        main_topic = canonicalize_concept_name(requested_topic)

    audit_tracker.seen_concepts.add(main_topic.lower())
    audit_tracker.accepted += 1
    logger.info(f"[ACCEPTED CONCEPT] Main topic '{main_topic}' accepted.")

    cleaned = {
        "topic": main_topic,
        "definition": data.get("definition") or f"{main_topic} is a core academic topic.",
        "why_it_matters": data.get("why_it_matters") or f"Understanding {main_topic} enables advanced domain mastery.",
        "example": data.get("example") or f"Practical applications of {main_topic} in problem solving.",
        "explanation": data.get("explanation") or f"Simple Definition: {main_topic}",
        "difficulty": data.get("difficulty") or "Beginner",
        "estimated_study_time": data.get("estimated_study_time") or "3-5 hours",
        "foundation_topics": data.get("foundation_topics") or [],
        "beginner_topics": data.get("beginner_topics") or [],
        "intermediate_topics": data.get("intermediate_topics") or [],
        "advanced_topics": data.get("advanced_topics") or [],
        "optional_reading": data.get("optional_reading") or [],
        "learning_milestones": data.get("learning_milestones") or ["Master core concept"],
        "prerequisites": [],
        "next_topics": [],
        "related_topics": [],
    }

    seen_relations = set()
    rel_map = {
        "prerequisites": ("PREREQUISITE_OF", "prerequisites"),
        "next_topics": ("NEXT_TOPIC", "next topics"),
        "related_topics": ("RELATED_TOPIC", "related topics")
    }

    for key, (rel_type, label) in rel_map.items():
        logger.info(f"[VALIDATION] Validating {label} for '{main_topic}'...")
        for item in data.get(key, []):
            if not isinstance(item, dict):
                continue

            raw_item_topic = item.get("topic", "")
            item_topic = canonicalize_concept_name(raw_item_topic)
            why = item.get("why", "")

            is_valid, reason = get_topic_validation_details(
                item_topic,
                pdf_text=context_text,
                ai_topics=all_ai_topics,
                curated_topics=KNOWN_EDUCATIONAL_TOPICS
            )
            if not is_valid:
                logger.info(f"[REJECTED CONCEPT] Concept '{item_topic}' in {label} rejected: {reason}")
                continue

            is_rel_valid, rel_reason = is_valid_relationship(
                main_topic, item_topic, rel_type, why, seen_relations
            )
            if not is_rel_valid:
                logger.info(f"[REJECTED CONCEPT] Relationship '{main_topic}' -[{rel_type}]-> '{item_topic}' rejected: {rel_reason}")
                continue

            audit_tracker.seen_concepts.add(item_topic.lower())
            rel_key = (main_topic.lower(), rel_type, item_topic.lower())
            seen_relations.add(rel_key)
            audit_tracker.seen_relationships.add(rel_key)
            audit_tracker.accepted += 1
            logger.info(f"[ACCEPTED CONCEPT] Relationship: '{main_topic}' -[{rel_type}]-> '{item_topic}' accepted.")

            cleaned[key].append({"topic": item_topic, "why": why})

    logger.info(f"[VALIDATION] Finished roadmap validation for '{main_topic}'.")
    return cleaned


def analyze_pdf_educational_content(pdf_text):
    system_prompt, user_prompt = build_pdf_analysis_prompt(pdf_text)
    response_text, error = safe_groq_generate(system_prompt, user_prompt, max_tokens=2500)

    if error:
        logger.error(f"[AI RESPONSE] PDF educational analysis failed: {error}")
        return None

    try:
        logger.info("[JSON PARSING] Parsing JSON for PDF educational chapter analysis...")
        analysis_data = json.loads(clean_json_object(response_text))
        logger.info("[JSON PARSING] Success parsing PDF educational chapter analysis.")
        return analysis_data
    except (json.JSONDecodeError, TypeError) as exc:
        logger.error(f"[JSON PARSING] Failed parsing PDF chapter analysis: {exc}")
        return None


def generate_roadmap_with_ai(topic, context_text=None):
    if context_text:
        analysis = analyze_pdf_educational_content(context_text)
        if analysis and isinstance(analysis, dict):
            main_title = canonicalize_concept_name(analysis.get("title") or topic)
            prereqs = [{"topic": canonicalize_concept_name(p.get("topic")), "why": p.get("why", "")} for p in analysis.get("prerequisites", []) if p.get("topic")]
            concepts = [canonicalize_concept_name(c.get("name")) for c in analysis.get("important_concepts", []) if c.get("name")]
            next_t = [{"topic": c, "why": f"{c} is covered in this chapter."} for c in concepts[1:4]]

            roadmap_data = {
                "topic": main_title,
                "definition": analysis.get("chapter_overview") or f"Educational chapter on {main_title}",
                "why_it_matters": "Chapter analysis extracted from uploaded study material.",
                "example": analysis.get("examples", [{}])[0].get("description") or "Practical exercises.",
                "explanation": f"Chapter Overview: {analysis.get('chapter_overview')}",
                "difficulty": "Intermediate",
                "estimated_study_time": "4-6 hours",
                "learning_milestones": analysis.get("learning_sequence") or ["Read chapter concepts"],
                "prerequisites": prereqs[:4],
                "next_topics": next_t[:4],
                "related_topics": [{"topic": c, "why": "Extracted concept"} for c in concepts[4:7]],
            }
            return validate_roadmap(roadmap_data, topic, is_from_pdf=True, context_text=context_text)

    system_prompt, user_prompt = build_roadmap_prompt(topic, context_text)
    response_text, error = safe_groq_generate(system_prompt, user_prompt, max_tokens=1500)

    if error:
        logger.error(f"[AI RESPONSE] Roadmap generation failed for '{topic}': {error}")
        return fallback_roadmap(topic)

    logger.info(f"[AI RESPONSE] Roadmap generated for '{topic}'. Parsing JSON...")

    try:
        data = json.loads(clean_json_object(response_text))
    except (json.JSONDecodeError, TypeError) as exc:
        logger.error(f"[JSON PARSING] Failed parsing JSON for topic '{topic}': {exc}")
        return fallback_roadmap(topic)

    return validate_roadmap(data, topic, is_from_pdf=bool(context_text), context_text=context_text)


def get_or_create_roadmap(topic, context_text=None, force_refresh=False):
    audit_tracker.reset()
    clean_topic = canonicalize_concept_name(topic)

    if not force_refresh and not context_text:
        cached = fetch_roadmap_from_neo4j(clean_topic)
        if cached:
            cached = validate_roadmap(cached, clean_topic)
            cached["cached"] = True
            audit_tracker.print_report()
            return cached

    roadmap = generate_roadmap_with_ai(clean_topic, context_text)
    save_roadmap_to_neo4j(roadmap)
    roadmap["cached"] = False
    audit_tracker.print_report()
    return roadmap
