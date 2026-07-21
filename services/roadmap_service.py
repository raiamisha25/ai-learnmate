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
        "beginner_topics": [{"topic": "Pointers", "why": "Nodes connect using reference pointers."}],
        "intermediate_topics": [{"topic": "Tree Traversal", "why": "Learn Inorder, Preorder, and Postorder traversals."}],
        "advanced_topics": [{"topic": "AVL Tree", "why": "Self-balancing binary search trees."}],
        "optional_reading": [{"topic": "Heap", "why": "Priority queue implementation using trees."}],
        "learning_milestones": ["Can implement node structure", "Can traverse tree recursively"],
        "prerequisites": [{"topic": "Recursion", "why": "Tree algorithms rely on recursive sub-problems."}],
        "next_topics": [{"topic": "AVL Tree", "why": "AVL Trees maintain tree balance."}],
        "related_topics": [{"topic": "Tree Traversal", "why": "Visiting all nodes in defined order."}],
    },
    "System Design": {
        "topic": "System Design",
        "definition": "System Design is the process of defining architecture, components, and interfaces for scalable systems.",
        "why_it_matters": "It enables building high-traffic, resilient software systems.",
        "example": "Designing scalable architectures like Netflix or Google.",
        "explanation": "System Design synthesizes software engineering, networking, and distributed storage.",
        "difficulty": "Advanced",
        "estimated_study_time": "20-30 hours",
        "foundation_topics": [
            {"topic": "Programming Fundamentals", "why": "Core code execution principles."},
            {"topic": "Object Oriented Programming", "why": "Modular component design."}
        ],
        "beginner_topics": [
            {"topic": "Data Structures", "why": "In-memory data organization."},
            {"topic": "Algorithms", "why": "Efficient computational procedures."}
        ],
        "intermediate_topics": [
            {"topic": "Operating System", "why": "Process management and memory isolation."},
            {"topic": "Computer Networks", "why": "TCP/IP, HTTP, and socket communication."},
            {"topic": "Database", "why": "Relational and NoSQL persistence."}
        ],
        "advanced_topics": [
            {"topic": "Concurrency", "why": "Multithreading and asynchronous execution."},
            {"topic": "Distributed Systems", "why": "Consensus, partitioning, and replication."},
            {"topic": "Caching", "why": "Low-latency memory storage like Redis."},
            {"topic": "Load Balancing", "why": "Traffic distribution across servers."}
        ],
        "learning_milestones": ["Architect scalable backend", "Design distributed storage"],
        "prerequisites": [{"topic": "Computer Networks", "why": "Networking fundamentals."}],
        "next_topics": [{"topic": "Microservices Architecture", "why": "Decomposed service domains."}],
        "related_topics": [{"topic": "Distributed Systems", "why": "Core architectural model."}],
    },
    "Machine Learning": {
        "topic": "Machine Learning",
        "definition": "Machine Learning focuses on algorithms that learn patterns from data to make predictions.",
        "why_it_matters": "It powers modern AI, computer vision, natural language processing, and automated decision engines.",
        "example": "Spam filters identifying spam emails automatically.",
        "explanation": "Machine Learning combines linear algebra, statistics, and optimization algorithms.",
        "difficulty": "Intermediate",
        "estimated_study_time": "15-25 hours",
        "foundation_topics": [
            {"topic": "Programming Fundamentals", "why": "Algorithmic thinking."},
            {"topic": "Python Programming", "why": "Primary language for ML frameworks."}
        ],
        "beginner_topics": [
            {"topic": "Linear Algebra", "why": "Matrix and vector operations."},
            {"topic": "Probability", "why": "Uncertainty modeling."},
            {"topic": "Statistics", "why": "Data distribution analysis."}
        ],
        "intermediate_topics": [
            {"topic": "Data Preprocessing", "why": "Feature scaling and cleaning."},
            {"topic": "Supervised Learning", "why": "Regression and classification."},
            {"topic": "Unsupervised Learning", "why": "Clustering and dimensionality reduction."}
        ],
        "advanced_topics": [
            {"topic": "Model Evaluation", "why": "Precision, recall, and cross-validation."},
            {"topic": "Neural Network", "why": "Deep learning architectures."},
            {"topic": "Deep Learning", "why": "Advanced multi-layer networks."}
        ],
        "learning_milestones": ["Train predictive model", "Evaluate model accuracy"],
        "prerequisites": [{"topic": "Statistics", "why": "Statistical foundation."}],
        "next_topics": [{"topic": "Deep Learning", "why": "Complex neural architectures."}],
        "related_topics": [{"topic": "Supervised Learning", "why": "Core ML paradigm."}],
    },
    "Linked List": {
        "topic": "Linked List",
        "definition": "A Linked List is a linear data structure where elements are stored in nodes connected by pointers.",
        "why_it_matters": "It allows efficient dynamic memory allocation and O(1) insertions and deletions.",
        "example": "Like a treasure hunt where each clue leads to the location of the next clue.",
        "explanation": "Definition: A Linked List stores data in dynamic nodes connected sequentially by reference pointers.",
        "difficulty": "Beginner",
        "estimated_study_time": "3-4 hours",
        "foundation_topics": [{"topic": "Arrays", "why": "Contiguous memory storage fundamentals."}],
        "beginner_topics": [{"topic": "Pointers", "why": "Memory address references."}],
        "intermediate_topics": [{"topic": "Doubly Linked List", "why": "Bidirectional node traversal."}],
        "advanced_topics": [{"topic": "Circular Linked List", "why": "Ring buffer memory structure."}],
        "prerequisites": [{"topic": "Arrays", "why": "Array memory fundamentals."}, {"topic": "Pointers", "why": "Pointer references."}],
        "next_topics": [{"topic": "Doubly Linked List", "why": "Two-way node pointer linkage."}, {"topic": "Circular Linked List", "why": "Tail points to head node."}, {"topic": "Skip List", "why": "Probabilistic search optimization."}],
        "related_topics": [{"topic": "Stack", "why": "LIFO memory structure."}, {"topic": "Queue", "why": "FIFO memory structure."}],
    },
    "Computer Networks": {
        "topic": "Computer Networks",
        "definition": "Computer Networks connect computing devices to share resources and communicate via protocols.",
        "why_it_matters": "It powers internet communication, cloud infrastructure, and distributed services.",
        "example": "The global Internet routing data packets between clients and servers.",
        "explanation": "Computer Networks analyze protocol stacks (OSI/TCP-IP), routing algorithms, and socket communications.",
        "difficulty": "Intermediate",
        "estimated_study_time": "10-15 hours",
        "foundation_topics": [{"topic": "Computer Architecture", "why": "Hardware hardware interfaces."}],
        "beginner_topics": [{"topic": "TCP/IP", "why": "Internet protocol suite."}],
        "intermediate_topics": [{"topic": "Routing", "why": "Packet path selection."}],
        "advanced_topics": [{"topic": "Switching", "why": "Data link frame forwarding."}],
        "prerequisites": [{"topic": "Computer Architecture", "why": "Hardware communication fundamentals."}],
        "next_topics": [{"topic": "TCP/IP", "why": "Core network protocol suite."}, {"topic": "Routing", "why": "Path determination algorithms."}, {"topic": "Switching", "why": "Frame switching architectures."}, {"topic": "Network Security", "why": "Cryptographic network protection."}],
        "related_topics": [{"topic": "Network Security", "why": "Data encryption and firewalls."}],
    },
}


def clean_json_object(text):
    import re
    import ast
    import json

    text = (text or "").strip()

    # 1. Regex to extract the JSON payload (everything from first { or [ to last } or ])
    match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
    if match:
        text = match.group(1)

    # 2. Replace non-breaking spaces (\xa0) and zero-width spaces (\u200b) with standard spaces
    text = text.replace('\xa0', ' ').replace('\u200b', ' ')

    # Sanitize invalid control characters (except standard tabs/newlines)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', lambda m: f'\\u{ord(m.group(0)):04x}', text)

    # 3. Try parsing with json.loads. If it fails, fallback to ast.literal_eval
    try:
        parsed = json.loads(text)
        return json.dumps(parsed)
    except Exception:
        try:
            parsed = ast.literal_eval(text)
            return json.dumps(parsed)
        except Exception:
            return text


def fallback_roadmap(topic):
    clean_topic = canonicalize_concept_name(topic)
    if clean_topic in CURATED_ROADMAPS:
        return CURATED_ROADMAPS[clean_topic]

    return {
        "topic": clean_topic,
        "definition": f"{clean_topic} is an educational concept in academic curricula.",
        "why_it_matters": f"Mastering {clean_topic} supports core domain understanding and problem solving.",
        "example": f"Core principles and applications of {clean_topic}.",
        "explanation": f"Definition: {clean_topic} is an educational concept.\nWhy It Matters: It supports learning in its domain.",
        "difficulty": "Beginner",
        "estimated_study_time": "3-5 hours",
        "foundation_topics": [],
        "beginner_topics": [],
        "intermediate_topics": [],
        "advanced_topics": [],
        "optional_reading": [],
        "learning_milestones": ["Understand core principles", "Apply concept to domain problems"],
        "prerequisites": [],
        "next_topics": [],
        "related_topics": [],
    }


def validate_roadmap(data, requested_topic, is_from_pdf=False, context_text=None):
    logger.info(f"[VALIDATION] Starting roadmap validation for topic '{requested_topic}'...")

    if requested_topic and is_valid_topic(canonicalize_concept_name(requested_topic)):
        main_topic = canonicalize_concept_name(requested_topic)
    else:
        raw_main_topic = data.get("topic") or requested_topic
        main_topic = canonicalize_concept_name(raw_main_topic)

    # Adapter: Convert flat string lists to list of dictionaries internally to preserve insertion / validation logic
    for key, rel_lbl in [("prerequisites", "prerequisite"), ("next_topics", "successor"), ("related_topics", "related concept")]:
        raw_list = data.get(key, [])
        if raw_list and isinstance(raw_list, list) and all(isinstance(x, str) for x in raw_list):
            data[key] = [{"topic": item, "why": f"{item} is a {rel_lbl} for {main_topic}."} for item in raw_list]

    all_ai_topics = {main_topic.lower()}
    for key in ("prerequisites", "next_topics", "related_topics", "foundation_topics", "beginner_topics", "intermediate_topics", "advanced_topics"):
        for item in data.get(key, []):
            if isinstance(item, dict) and item.get("topic"):
                all_ai_topics.add(canonicalize_concept_name(item.get("topic")).lower())

    is_main_valid, main_reason = get_topic_validation_details(
        main_topic,
        pdf_text=context_text,
        ai_topics=all_ai_topics,
        curated_topics=KNOWN_EDUCATIONAL_TOPICS,
        main_topic=None
    )

    if not is_main_valid:
        logger.info(f"[REJECTED CONCEPT] Main topic '{main_topic}' rejected: {main_reason}. Using requested topic.")
        main_topic = canonicalize_concept_name(requested_topic)

    audit_tracker.seen_concepts.add(main_topic.lower())
    audit_tracker.accepted += 1
    logger.info(f"[ACCEPTED CONCEPT] Main topic '{main_topic}' accepted.")

    # Request-scoped validation context set for this roadmap execution
    request_validated_topics = {main_topic.lower(), main_topic}

    def clean_topic_items(items, rel_type, label):
        cleaned_list = []
        seen_relations = set()
        for item in items or []:
            if not isinstance(item, dict):
                continue
            raw_item_topic = item.get("topic", "")
            item_topic = canonicalize_concept_name(raw_item_topic)
            why = item.get("why", f"{item_topic} relates to {main_topic}.")

            is_valid, reason = get_topic_validation_details(
                item_topic,
                pdf_text=context_text,
                ai_topics=all_ai_topics,
                curated_topics=KNOWN_EDUCATIONAL_TOPICS,
                main_topic=main_topic,
                is_prereq=(rel_type == "PREREQUISITE_OF")
            )
            if not is_valid:
                logger.info(f"[REJECTED CONCEPT] Concept '{item_topic}' in {label} rejected: {reason}")
                continue

            request_validated_topics.add(item_topic.lower())
            request_validated_topics.add(item_topic)

            is_rel_valid, rel_reason = is_valid_relationship(
                main_topic, item_topic, rel_type, why, seen_relations, validated_topics=request_validated_topics
            )
            if not is_rel_valid:
                logger.info(f"[REJECTED CONCEPT] Relationship '{main_topic}' -[{rel_type}]-> '{item_topic}' rejected: {rel_reason}")
                continue

            audit_tracker.seen_concepts.add(item_topic.lower())
            rel_key = (main_topic.lower(), rel_type, item_topic.lower())
            seen_relations.add(rel_key)
            audit_tracker.seen_relationships.add(rel_key)
            audit_tracker.accepted += 1
            cleaned_list.append({"topic": item_topic, "why": why})
        return cleaned_list

    foundation_clean = clean_topic_items(data.get("foundation_topics"), "PREREQUISITE_OF", "foundation topics")
    beginner_clean = clean_topic_items(data.get("beginner_topics"), "PREREQUISITE_OF", "beginner topics")
    intermediate_clean = clean_topic_items(data.get("intermediate_topics"), "BUILDS_ON", "intermediate topics")
    advanced_clean = clean_topic_items(data.get("advanced_topics"), "BUILDS_ON", "advanced topics")
    prereqs_clean = clean_topic_items(data.get("prerequisites"), "PREREQUISITE_OF", "prerequisites")
    next_clean = clean_topic_items(data.get("next_topics"), "NEXT_TOPIC", "next topics")
    related_clean = clean_topic_items(data.get("related_topics"), "RELATED_TOPIC", "related topics")

    # Separate prerequisites from progression topics cleanly
    all_prereqs = []
    seen_prereqs = set()
    for item in foundation_clean + beginner_clean + prereqs_clean:
        t_low = item["topic"].lower()
        if t_low not in seen_prereqs and t_low != main_topic.lower():
            seen_prereqs.add(t_low)
            all_prereqs.append(item)

    all_next = []
    seen_next = set()
    for item in intermediate_clean + advanced_clean + next_clean:
        t_low = item["topic"].lower()
        if t_low not in seen_next and t_low != main_topic.lower() and t_low not in seen_prereqs:
            seen_next.add(t_low)
            all_next.append(item)

    cleaned = {
        "topic": main_topic,
        "definition": data.get("definition") or f"{main_topic} is a core academic topic.",
        "why_it_matters": data.get("why_it_matters") or f"Understanding {main_topic} enables advanced domain mastery.",
        "example": data.get("example") or f"Practical applications of {main_topic} in problem solving.",
        "explanation": data.get("explanation") or f"Simple Definition: {main_topic}",
        "difficulty": data.get("difficulty") or "Beginner",
        "estimated_study_time": data.get("estimated_study_time") or "3-5 hours",
        "foundation_topics": foundation_clean,
        "beginner_topics": beginner_clean,
        "intermediate_topics": intermediate_clean,
        "advanced_topics": advanced_clean,
        "optional_reading": data.get("optional_reading") or [],
        "learning_milestones": data.get("learning_milestones") or ["Master core concept"],
        "prerequisites": all_prereqs,
        "next_topics": all_next,
        "related_topics": related_clean,
        "validated_topics": list(request_validated_topics),
    }

    logger.info(f"[VALIDATION] Finished roadmap validation for '{main_topic}'. Total prerequisites: {len(all_prereqs)}, Next: {len(all_next)}")
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
