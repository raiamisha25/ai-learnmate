import json

from services.groq_service import safe_groq_generate
from services.neo4j_service import fetch_roadmap_from_neo4j, save_roadmap_to_neo4j
from utils.topic_validator import filter_valid_topics, is_valid_topic, normalize_topic_name


ROADMAP_SYSTEM_PROMPT = """
You are an expert curriculum designer.
Create beginner-friendly learning roadmaps.
Return JSON only. No markdown.
Never include random nouns, adjectives, filler words, sentence fragments, or generic words.
Only include meaningful educational concepts.
Explanations must be simple, concrete, and useful for a beginner.
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
    clean_topic = normalize_topic_name(topic)
    return CURATED_ROADMAPS.get(
        clean_topic,
        {
            "topic": clean_topic,
            "definition": f"{clean_topic} is an important concept that helps you solve a specific type of problem.",
            "why_it_matters": "It gives you a foundation for learning related topics more easily.",
            "example": "Like learning one tool before using it in a bigger project.",
            "explanation": f"Definition: {clean_topic} is an important concept for solving specific problems.\nWhy It Matters: It supports related topics.\nReal World Example: Like learning one tool before using it in a bigger project.",
            "analogy": "Like learning one tool before using it in a bigger project.",
            "difficulty": "Beginner",
            "estimated_time": "2-4 hours",
            "prerequisites": [],
            "next_topics": [],
            "related_topics": [],
        },
    )


def validate_roadmap(data, requested_topic):
    topic = normalize_topic_name(data.get("topic") or requested_topic)
    if not is_valid_topic(topic):
        topic = normalize_topic_name(requested_topic)

    approved = [topic]

    for key in ("prerequisites", "next_topics", "related_topics"):
        approved.extend(item.get("topic", "") for item in data.get(key, []) if isinstance(item, dict))

    cleaned = {
        "topic": topic,
        "definition": data.get("definition") or fallback_roadmap(topic).get("definition"),
        "why_it_matters": data.get("why_it_matters") or fallback_roadmap(topic).get("why_it_matters"),
        "example": data.get("example") or fallback_roadmap(topic).get("example"),
        "explanation": "",
        "analogy": data.get("analogy") or "Think of it as one step in a larger learning path.",
        "difficulty": data.get("difficulty") or "Beginner",
        "estimated_time": data.get("estimated_time") or "2-4 hours",
        "prerequisites": [],
        "next_topics": [],
        "related_topics": [],
    }
    cleaned["explanation"] = format_explanation(cleaned)

    for key in ("prerequisites", "next_topics", "related_topics"):
        topics = filter_valid_topics(
            [item.get("topic", "") for item in data.get(key, []) if isinstance(item, dict)],
            limit=5,
        )
        for topic_name in topics:
            source = next(
                (item for item in data.get(key, []) if normalize_topic_name(item.get("topic", "")) == topic_name),
                {},
            )
            cleaned[key].append(
                {
                    "topic": topic_name,
                    "why": source.get("why") or f"{topic_name} helps you understand {cleaned['topic']}.",
                }
            )

    curated = fallback_roadmap(cleaned["topic"])
    if curated.get("topic") == cleaned["topic"]:
        for key in ("prerequisites", "next_topics", "related_topics"):
            add_curated_items(cleaned, curated, key)

    return cleaned


def add_curated_items(cleaned, curated, key):
    """Fill weak AI sections with trusted beginner roadmap items."""
    existing = {item["topic"].lower() for item in cleaned.get(key, [])}

    for item in curated.get(key, []):
        if len(cleaned[key]) >= 5:
            break

        topic_name = item.get("topic", "")
        if not topic_name or topic_name.lower() in existing:
            continue

        cleaned[key].append(
            {
                "topic": topic_name,
                "why": item.get("why") or f"{topic_name} supports {cleaned['topic']}.",
            }
        )
        existing.add(topic_name.lower())


def generate_roadmap_with_ai(topic, context_text=None):
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
  "explanation": "Definition: ...\\nWhy It Matters: ...\\nReal World Example: ...",
  "analogy": "simple analogy",
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
- Explanation must have exactly 3 short sections: Definition, Why It Matters, Real World Example.
- Use simple English. Avoid jargon where possible.
- Recommend only true prerequisites, meaningful next topics, and useful related topics.
- Every recommendation must include a clear reason.
"""
    response_text, error = safe_groq_generate(ROADMAP_SYSTEM_PROMPT, user_prompt)

    if error:
        print(f"Roadmap generation failed for '{topic}': {error}")
        return fallback_roadmap(topic)

    try:
        data = json.loads(clean_json_object(response_text))
    except (json.JSONDecodeError, TypeError) as exc:
        print(f"Roadmap generation failed for '{topic}': invalid JSON from Groq: {exc}")
        return fallback_roadmap(topic)

    return validate_roadmap(data, topic)


def format_explanation(data):
    definition = (data.get("definition") or "").strip()
    why = (data.get("why_it_matters") or "").strip()
    example = (data.get("example") or data.get("analogy") or "").strip()

    return "\n".join(
        [
            f"Definition: {definition}",
            f"Why It Matters: {why}",
            f"Real World Example: {example}",
        ]
    )


def get_or_create_roadmap(topic, context_text=None, force_refresh=False):
    clean_topic = normalize_topic_name(topic)

    if not force_refresh:
        cached = fetch_roadmap_from_neo4j(clean_topic)
        if cached:
            cached = validate_roadmap(cached, clean_topic)
            cached["cached"] = True
            return cached

    roadmap = generate_roadmap_with_ai(clean_topic, context_text)
    save_roadmap_to_neo4j(roadmap)
    roadmap["cached"] = False
    return roadmap
