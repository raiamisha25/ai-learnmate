COMMON_WORDS = {
    "able", "about", "above", "after", "again", "array", "also", "before",
    "being", "below", "between", "creates", "data", "does", "done", "each",
    "elements", "example", "first", "from", "grow", "initial", "into",
    "items", "list", "many", "more", "most", "next", "other", "same",
    "size", "specified", "such", "that", "their", "them", "then", "there",
    "these", "this", "those", "used", "using", "value", "when", "where",
    "which", "while", "with",
}

KNOWN_EDUCATIONAL_TOPICS = {
    "arrays", "functions", "base case", "arraylist", "linked list", "binary tree", "avl tree", "recursion",
    "hashmap", "hashset", "dynamic programming", "operating system",
    "machine learning", "neural network", "database", "graph", "heap",
    "stack", "queue", "sorting", "searching", "object oriented programming",
    "process scheduling", "memory management", "supervised learning",
}


def normalize_topic_name(topic):
    topic = " ".join((topic or "").replace("_", " ").split())
    special_names = {
        "arraylist": "ArrayList",
        "hashmap": "HashMap",
        "hashset": "HashSet",
        "avl tree": "AVL Tree",
    }
    lower = topic.lower()

    if lower in special_names:
        return special_names[lower]

    return " ".join(word.capitalize() for word in topic.split())


def is_valid_topic(topic, approved_topics=None):
    clean = normalize_topic_name(topic)
    lower = clean.lower()

    if len(clean) < 3:
        return False
    if lower in COMMON_WORDS:
        return False
    if len(clean.split()) == 1 and lower not in KNOWN_EDUCATIONAL_TOPICS:
        # Single generic words are a major source of bad recommendations.
        return lower in {"recursion", "arraylist", "hashmap", "hashset", "heap", "stack", "queue"}
    if approved_topics and lower not in {item.lower() for item in approved_topics}:
        return False

    return True


def filter_valid_topics(topics, approved_topics=None, limit=8):
    clean_topics = []

    for topic in topics or []:
        clean = normalize_topic_name(topic)
        if is_valid_topic(clean, approved_topics) and clean not in clean_topics:
            clean_topics.append(clean)
        if len(clean_topics) == limit:
            break

    return clean_topics
