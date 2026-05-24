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
"""


CURATED_ROADMAPS = {
    "ArrayList": {
        "topic": "ArrayList",
        "explanation": "An ArrayList is a resizable list that stores elements in order and grows as needed.",
        "analogy": "Think of it like a notebook where you can keep adding pages without creating a new notebook.",
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
        "explanation": "A Binary Tree stores data as nodes where each node can have up to two children.",
        "analogy": "It is like a family tree where each person can branch into two children.",
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
    "Recursion": {
        "topic": "Recursion",
        "explanation": "Recursion is solving a problem by breaking it into smaller versions of itself.",
        "analogy": "It is like opening nested boxes until you reach the smallest box, then closing them back up.",
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
        "explanation": "An Operating System manages hardware, memory, files, and programs so users can run applications.",
        "analogy": "It is like a manager that assigns rooms, tools, and schedules to workers.",
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
    "Machine Learning": {
        "topic": "Machine Learning",
        "explanation": "Machine Learning teaches computers to find patterns in data and make predictions.",
        "analogy": "It is like learning from examples instead of following only fixed instructions.",
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
            "explanation": f"{clean_topic} is an important study topic. Learn the basics first, then practice with examples.",
            "analogy": "Think of it as one step in a larger learning path.",
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
        "explanation": (data.get("explanation") or fallback_roadmap(topic)["explanation"])[:360],
        "analogy": data.get("analogy") or "Think of it as one step in a larger learning path.",
        "difficulty": data.get("difficulty") or "Beginner",
        "estimated_time": data.get("estimated_time") or "2-4 hours",
        "prerequisites": [],
        "next_topics": [],
        "related_topics": [],
    }

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

    return cleaned


def generate_roadmap_with_ai(topic, context_text=None):
    user_prompt = f"""
Create a learning roadmap for: {topic}

Context:
{(context_text or topic)[:6000]}

Return JSON only:
{{
  "topic": "real educational topic",
  "explanation": "2-3 line beginner explanation",
  "analogy": "simple real-world analogy",
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


def get_or_create_roadmap(topic, context_text=None, force_refresh=False):
    clean_topic = normalize_topic_name(topic)

    if not force_refresh:
        cached = fetch_roadmap_from_neo4j(clean_topic)
        if cached:
            cached["cached"] = True
            return cached

    roadmap = generate_roadmap_with_ai(clean_topic, context_text)
    save_roadmap_to_neo4j(roadmap)
    roadmap["cached"] = False
    return roadmap

