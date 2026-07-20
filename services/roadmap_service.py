import json

from services.groq_service import safe_groq_generate
from services.neo4j_service import fetch_roadmap_from_neo4j, save_roadmap_to_neo4j
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


ROADMAP_SYSTEM_PROMPT = """
You are an expert curriculum designer.
Create beginner-friendly learning roadmaps.
Return JSON only. No markdown.
Never include random nouns, adjectives, filler words, sentence fragments, or generic words.
Only include meaningful educational concepts.
Explanations must be simple, concrete, and useful for a beginner.
Avoid textbook language. Explain like an excellent teacher.
"""


CURATED_ROADMAPS = {
    "ArrayList": {
        "topic": "ArrayList",
        "definition": "An ArrayList stores items in order and can grow when you add more items.",
        "why_it_matters": "It makes it easy to store, access, and update a changing list of data.",
        "example": "Like a playlist where songs stay in order, but you can keep adding more.",
        "explanation": "Definition: An ArrayList stores items in order and can grow when you add more items.\nWhy It Matters: It makes changing lists easy to manage.\nReal World Example: Like a playlist where you can keep adding songs.",
        "difficulty": "Beginner",
        "estimated_time": "2 hours",
        "prerequisites": [
            {"topic": "Arrays", "why": "ArrayList is built on the idea of indexed storage."},
            {"topic": "Object Oriented Programming", "why": "ArrayList is used as a class with methods."},
        ],
        "next_topics": [
            {"topic": "Linked List", "why": "It shows another way to store ordered data."},
            {"topic": "HashMap", "why": "It introduces key-value lookup instead of index lookup."},
        ],
        "related_topics": [
            {"topic": "Collections Framework", "why": "ArrayList belongs to Java collections."}
        ],
    },
    "Binary Tree": {
        "topic": "Binary Tree",
        "definition": "A Binary Tree stores data in nodes where each node can have up to two children.",
        "why_it_matters": "It helps organize data for searching, sorting, and decision-making.",
        "example": "Like a yes/no decision chart that branches into smaller choices.",
        "explanation": "Definition: A Binary Tree stores data in nodes with up to two children.\nWhy It Matters: It helps organize data for searching and decisions.\nReal World Example: Like a yes/no decision chart.",
        "difficulty": "Intermediate",
        "estimated_time": "4 hours",
        "prerequisites": [
            {"topic": "Recursion", "why": "Tree problems are often solved by repeating the same logic on subtrees."},
            {"topic": "Linked List", "why": "Tree nodes also connect to other nodes using references."},
        ],
        "next_topics": [
            {"topic": "AVL Tree", "why": "AVL Trees keep Binary Trees balanced."},
            {"topic": "Heap", "why": "A Heap is a specialized tree used in priority queues."},
            {"topic": "Graphs", "why": "Graphs generalize tree-like relationships."},
        ],
        "related_topics": [
            {"topic": "Tree Traversal", "why": "Traversal is how you visit every node."}
        ],
    },
    "Linked List": {
        "topic": "Linked List",
        "definition": "A Linked List stores items as connected nodes instead of one continuous block.",
        "why_it_matters": "It teaches how data can grow, shrink, and connect through references.",
        "example": "Like a treasure hunt where each clue points to the next clue.",
        "explanation": "Definition: A Linked List stores items as connected nodes.\nWhy It Matters: It teaches flexible data storage with references.\nReal World Example: Like clues where each clue points to the next.",
        "difficulty": "Beginner",
        "estimated_time": "3 hours",
        "prerequisites": [
            {"topic": "Arrays", "why": "Arrays make it easier to compare indexed storage with linked storage."},
            {"topic": "Pointers", "why": "Linked Lists depend on references from one node to another."},
        ],
        "next_topics": [
            {"topic": "Stack", "why": "Stacks can be implemented using linked nodes."},
            {"topic": "Queue", "why": "Queues help apply linked list operations in order-based problems."},
            {"topic": "Binary Tree", "why": "Tree nodes also connect through references."},
        ],
        "related_topics": [
            {"topic": "Doubly Linked List", "why": "It extends Linked List by connecting nodes forward and backward."},
            {"topic": "Circular Linked List", "why": "It shows how linked structures can loop back to the start."},
        ],
    },
    "Recursion": {
        "topic": "Recursion",
        "definition": "Recursion solves a problem by having a function call itself on smaller cases.",
        "why_it_matters": "It makes problems like trees, folders, and repeated patterns easier to solve.",
        "example": "Like opening nested boxes until you reach the smallest box.",
        "explanation": "Definition: Recursion solves a problem by calling itself on smaller cases.\nWhy It Matters: It makes repeated patterns easier to solve.\nReal World Example: Like opening nested boxes one by one.",
        "difficulty": "Beginner",
        "estimated_time": "3 hours",
        "prerequisites": [
            {"topic": "Functions", "why": "A recursive solution is a function calling itself."},
            {"topic": "Base Case", "why": "The base case tells recursion when to stop."},
        ],
        "next_topics": [
            {"topic": "Binary Tree", "why": "Tree algorithms often depend on recursion."},
            {"topic": "Dynamic Programming", "why": "Dynamic Programming improves repeated recursive solutions."},
        ],
        "related_topics": [
            {"topic": "Call Stack", "why": "The call stack stores recursive function calls."}
        ],
    },
    "Operating System": {
        "topic": "Operating System",
        "definition": "An Operating System manages the computer's hardware, files, memory, and running programs.",
        "why_it_matters": "It lets apps run smoothly without users controlling hardware directly.",
        "example": "Like a manager assigning time, space, and tools to workers.",
        "explanation": "Definition: An Operating System manages hardware, files, memory, and programs.\nWhy It Matters: It lets apps run smoothly.\nReal World Example: Like a manager assigning tools and schedules.",
        "difficulty": "Intermediate",
        "estimated_time": "8 hours",
        "prerequisites": [
            {"topic": "Computer Architecture", "why": "OS concepts depend on CPU, memory, and storage basics."},
            {"topic": "Processes", "why": "Processes are the core units an OS manages."},
        ],
        "next_topics": [
            {"topic": "Process Scheduling", "why": "Scheduling decides which program runs next."},
            {"topic": "Memory Management", "why": "Memory management controls how programs use RAM."},
        ],
        "related_topics": [
            {"topic": "File Systems", "why": "File systems organize data on storage devices."}
        ],
    },
    "HashMap": {
        "topic": "HashMap",
        "definition": "A HashMap stores data as key-value pairs so you can find values quickly by key.",
        "why_it_matters": "It makes searching, counting, and lookup problems much faster.",
        "example": "Like a contact list where a name helps you instantly find a phone number.",
        "explanation": "Definition: A HashMap stores key-value pairs.\nWhy It Matters: It gives fast lookup by key.\nReal World Example: Like finding a phone number by a person's name.",
        "difficulty": "Beginner",
        "estimated_time": "3 hours",
        "prerequisites": [
            {"topic": "Arrays", "why": "HashMaps often use array-like storage behind the scenes."},
            {"topic": "Hash Function", "why": "A hash function decides where each key should be stored."},
        ],
        "next_topics": [
            {"topic": "HashSet", "why": "HashSet uses similar hashing ideas to store unique values."},
            {"topic": "Collision Handling", "why": "Collisions explain what happens when keys land in the same place."},
        ],
        "related_topics": [
            {"topic": "Dictionary", "why": "Many languages use dictionary-style structures like HashMap."},
            {"topic": "Time Complexity", "why": "HashMap performance is usually described using time complexity."},
        ],
    },
    "Machine Learning": {
        "topic": "Machine Learning",
        "definition": "Machine Learning helps computers learn patterns from data and make predictions.",
        "why_it_matters": "It powers recommendations, image recognition, chatbots, and many AI tools.",
        "example": "Like learning to identify spam emails after seeing many examples.",
        "explanation": "Definition: Machine Learning helps computers learn patterns from data.\nWhy It Matters: It powers predictions and AI tools.\nReal World Example: Like learning to spot spam emails from examples.",
        "difficulty": "Intermediate",
        "estimated_time": "10 hours",
        "prerequisites": [
            {"topic": "Python Programming", "why": "Python is commonly used for ML experiments."},
            {"topic": "Linear Algebra", "why": "Models use vectors and matrices to represent data."},
            {"topic": "Statistics", "why": "Statistics helps measure uncertainty and performance."},
        ],
        "next_topics": [
            {"topic": "Supervised Learning", "why": "It is the most common starting point for ML."},
            {"topic": "Neural Network", "why": "Neural Networks power many modern AI systems."},
        ],
        "related_topics": [
            {"topic": "Data Preprocessing", "why": "Good data preparation improves ML results."}
        ],
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
            "definition": f"{clean_topic} is an important concept that helps you solve a specific type of problem.",
            "why_it_matters": "It gives you a foundation for learning related topics more easily.",
            "example": "Like learning one tool before using it in a bigger project.",
            "explanation": f"Definition: {clean_topic} is an important concept for solving specific problems.\nWhy It Matters: It supports related topics.\nReal World Example: Like learning one tool before using it in a bigger project.",
            "analogy": "Like learning one tool before using it in a bigger project.",
            "common_mistakes": "Skipping practice examples or learning related topics without understanding the main idea.",
            "interview_questions": f"What problem does {clean_topic} solve? When would you use it?",
            "when_to_study_next": "Move on after you can explain the idea and solve one simple example without help.",
            "difficulty": "Beginner",
            "estimated_time": "2-4 hours",
            "prerequisites": [],
            "next_topics": [],
            "related_topics": [],
        },
    )


def validate_roadmap(data, requested_topic, is_from_pdf=False, context_text=None):
    logger.info(f"[VALIDATION] Starting validation for topic '{requested_topic}'...")

    # 1. Canonicalize and validate main topic
    raw_main_topic = data.get("topic") or requested_topic
    main_topic = canonicalize_concept_name(raw_main_topic)

    # Pre-collect all AI topics for hallucination check
    all_ai_topics = {main_topic.lower()}
    for key in ("prerequisites", "next_topics", "related_topics"):
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
        logger.info(f"[REJECTED CONCEPT] Main topic '{main_topic}' rejected: {main_reason}. Falling back to requested topic.")
        main_topic = canonicalize_concept_name(requested_topic)
        # Re-validate fallback requested topic
        is_main_valid, main_reason = get_topic_validation_details(
            main_topic,
            pdf_text=context_text,
            ai_topics=all_ai_topics,
            curated_topics=KNOWN_EDUCATIONAL_TOPICS
        )
        if not is_main_valid:
            main_topic = canonicalize_concept_name(requested_topic)
            logger.info(f"[VALIDATION] Fallback topic '{main_topic}' used despite validation warning.")

    audit_tracker.seen_concepts.add(main_topic.lower())
    audit_tracker.accepted += 1
    logger.info(f"[ACCEPTED CONCEPT] Main topic '{main_topic}' accepted.")

    # Validate main topic descriptive fields
    definition = data.get("definition") or ""
    why_it_matters = data.get("why_it_matters") or ""
    example = data.get("example") or ""
    analogy = data.get("analogy") or ""

    if not definition or len(definition.strip()) < 10:
        logger.info(f"[REJECTED CONCEPT] Incomplete field: 'definition' for '{main_topic}' is missing or too short.")
        definition = f"{main_topic} is a key educational topic in this study domain."
    if not why_it_matters or len(why_it_matters.strip()) < 10:
        logger.info(f"[REJECTED CONCEPT] Incomplete field: 'why_it_matters' for '{main_topic}' is missing or too short.")
        why_it_matters = f"Mastering {main_topic} provides a fundamental foundation for learning advanced concepts."
    if not example or len(example.strip()) < 10:
        example = f"Practice applying {main_topic} in hands-on exercises."

    cleaned = {
        "topic": main_topic,
        "definition": definition,
        "why_it_matters": why_it_matters,
        "example": example,
        "explanation": "",
        "analogy": analogy or "Think of it as a tool you learn before using it in a larger project.",
        "common_mistakes": data.get("common_mistakes") or "Memorizing code or theory without practical application.",
        "interview_questions": data.get("interview_questions") or f"What problem does {main_topic} solve? When would you use it?",
        "when_to_study_next": data.get("when_to_study_next") or "When you can solve simple examples without assistance.",
        "difficulty": data.get("difficulty") or "Beginner",
        "estimated_time": data.get("estimated_time") or "2-4 hours",
        "prerequisites": [],
        "next_topics": [],
        "related_topics": [],
    }

    # 2. Validate prerequisites, next_topics, related_topics
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
                logger.info(f"[REJECTED CONCEPT] Invalid item format in {label} (not a dict): {item}")
                continue

            raw_item_topic = item.get("topic", "")
            item_topic = canonicalize_concept_name(raw_item_topic)
            why = item.get("why", "")

            # Validate name
            is_valid, reason = get_topic_validation_details(
                item_topic,
                pdf_text=context_text,
                ai_topics=all_ai_topics,
                curated_topics=KNOWN_EDUCATIONAL_TOPICS
            )
            if not is_valid:
                logger.info(f"[REJECTED CONCEPT] Concept '{item_topic}' in {label} rejected: {reason}")
                continue

            # Validate relationship
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

            cleaned[key].append({
                "topic": item_topic,
                "why": why
            })

    # Curation fallback enrichment if needed
    if not is_from_pdf:
        curated = fallback_roadmap(cleaned["topic"])
        if curated.get("topic") == cleaned["topic"]:
            for key, (rel_type, label) in rel_map.items():
                existing = {it["topic"].lower() for it in cleaned[key]}
                for cur_item in curated.get(key, []):
                    if len(cleaned[key]) >= 5:
                        break
                    cur_topic = canonicalize_concept_name(cur_item.get("topic", ""))
                    if not cur_topic or cur_topic.lower() in existing:
                        continue

                    why = cur_item.get("why") or f"{cur_topic} supports {cleaned['topic']}."
                    cleaned[key].append({
                        "topic": cur_topic,
                        "why": why
                    })
                    existing.add(cur_topic.lower())
                    audit_tracker.seen_concepts.add(cur_topic.lower())

    cleaned["explanation"] = format_explanation(cleaned)
    logger.info(f"[VALIDATION] Finished validation for '{main_topic}'.")
    return cleaned


def generate_roadmap_with_ai(topic, context_text=None):
    if context_text:
        system_prompt = """
You are an expert educational AI. Your task is to analyze study material (PDF text) to detect main concepts and build prerequisite relationships between them.
Return ONLY valid JSON. Do not include markdown, prose, or comments.
"""
        user_prompt = f"""
Analyze the following study material to extract main learning concepts and organize them into a roadmap.

Study Material:
{context_text[:7000]}

Follow these instructions strictly:
1. Detect the main concepts covered in this study material.
2. Do not summarize every sentence. Instead, extract only distinct, meaningful learning concepts.
3. Remove duplicate concepts (ensure all concept names are unique and distinct).
4. Build prerequisite relationships between these concepts:
   - Identify which concepts must be studied BEFORE other concepts.
   - Map these relationships by listing them as prerequisites or next_topics.
5. Ignore any headers, page numbers, footers, captions, or references.
6. Store only meaningful learning concepts (real educational topics, domain-specific terminology). Do not include generic verbs, adjectives, pronouns, or common words.
7. Set the overall main concept of the document as the main "topic".

Return ONLY JSON in this exact shape:
{{
  "topic": "Main Concept Name",
  "definition": "Simple definition of the main concept in plain English",
  "why_it_matters": "Why this main concept matters",
  "example": "Real-world example of the main concept",
  "analogy": "Simple analogy of the main concept",
  "common_mistakes": "Common learner mistakes for the main concept",
  "interview_questions": "2-3 interview questions about the main concept",
  "when_to_study_next": "When the learner is ready to study next concepts",
  "explanation": "Simple Definition: ...\\nWhy it matters: ...\\nReal-life analogy: ...\\nExample: ...\\nCommon mistakes: ...\\nInterview questions: ...\\nWhen to study next topic: ...",
  "difficulty": "Beginner | Intermediate | Advanced",
  "estimated_time": "study time (e.g. 2-4 hours)",
  "prerequisites": [
    {{"topic": "Prerequisite Concept Name", "why": "Why this is a prerequisite of the main concept"}}
  ],
  "next_topics": [
    {{"topic": "Next Concept Name", "why": "Why this should be learned after the main concept"}}
  ],
  "related_topics": [
    {{"topic": "Related Concept Name", "why": "How this connects to the main concept"}}
  ]
}}
"""
        response_text, error = safe_groq_generate(system_prompt, user_prompt)
    else:
        user_prompt = f"""
Create a learning roadmap for: {topic}

Context:
{(context_text or topic)[:6000]}

Return JSON only:
{{
  "topic": "real educational topic",
  "definition": "simple definition in plain English",
  "why_it_matters": "why this topic matters",
  "example": "real world example",
  "analogy": "simple analogy",
  "common_mistakes": "common learner mistakes",
  "interview_questions": "2-3 interview questions",
  "when_to_study_next": "when the learner is ready for the next topic",
  "explanation": "Simple Definition: ...\\nWhy it matters: ...\\nReal-life analogy: ...\\nExample: ...\\nCommon mistakes: ...\\nInterview questions: ...\\nWhen to study next topic: ...",
  "difficulty": "Beginner | Intermediate | Advanced",
  "estimated_time": "study time",
  "prerequisites": [
    {{"topic": "meaningful prerequisite", "why": "why it matters"}}
  ],
  "next_topics": [
    {{"topic": "meaningful next topic", "why": "why it comes next"}}
  ],
  "related_topics": [
    {{"topic": "meaningful related topic", "why": "how it connects"}}
  ]
}}

Rules:
- Extract ONLY meaningful educational topics.
- Return ONLY real study concepts.
- Do not include random words, generic nouns, sentence fragments, adjectives, or verbs.
- Reject words like Elements, Initial, Specified, Grow, Creates, Size.
- Explanation must have exactly 7 short sections: Simple Definition, Why it matters, Real-life analogy, Example, Common mistakes, Interview questions, When to study next topic.
- Keep the full explanation under 300 words.
- Avoid textbook language. Explain like an excellent teacher.
- Use simple English, short sentences, and concrete examples.
- Recommend only true prerequisites, meaningful next topics, and useful related topics.
- Every recommendation must include a clear reason.
"""
        response_text, error = safe_groq_generate(ROADMAP_SYSTEM_PROMPT, user_prompt)

    if error:
        logger.error(f"[AI RESPONSE] Roadmap generation failed for '{topic}': {error}")
        return fallback_roadmap(topic)

    logger.info(f"[AI RESPONSE] Roadmap generated for '{topic}'. Parsing JSON...")

    try:
        logger.info(f"[JSON PARSING] Attempting to parse JSON for topic '{topic}'...")
        data = json.loads(clean_json_object(response_text))
        logger.info(f"[JSON PARSING] Success parsing JSON for topic '{topic}'.")
    except (json.JSONDecodeError, TypeError) as exc:
        logger.error(f"[JSON PARSING] Failed parsing JSON for topic '{topic}': {exc}")
        return fallback_roadmap(topic)

    return validate_roadmap(data, topic, is_from_pdf=bool(context_text), context_text=context_text)


def format_explanation(data):
    definition = (data.get("definition") or "").strip()
    why = (data.get("why_it_matters") or "").strip()
    analogy = (data.get("analogy") or "Think of it as a tool you learn before using it in a bigger project.").strip()
    example = (data.get("example") or analogy).strip()
    mistakes = (
        data.get("common_mistakes")
        or "A common mistake is memorizing the words without trying a small example."
    ).strip()
    questions = (
        data.get("interview_questions")
        or f"What problem does {data.get('topic', 'this topic')} solve? When would you use it?"
    ).strip()
    next_step = (
        data.get("when_to_study_next")
        or "Study the next topic when you can explain this one simply and solve a basic example."
    ).strip()

    explanation = "\n".join(
        [
            f"Simple Definition: {definition}",
            f"Why it matters: {why}",
            f"Real-life analogy: {analogy}",
            f"Example: {example}",
            f"Common mistakes: {mistakes}",
            f"Interview questions: {questions}",
            f"When to study next topic: {next_step}",
        ]
    )
    words = explanation.split()
    return " ".join(words[:300]) if len(words) > 300 else explanation


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
