import re


COMMON_WORDS = {
    "able", "about", "above", "after", "again", "also", "before", "being",
    "below", "between", "continue", "creates", "data", "does", "done",
    "each", "elements", "environment", "example", "first", "from", "grow",
    "important", "initial", "into", "items", "learn", "many", "more", "most",
    "next", "other", "same", "simple", "size", "specified", "step", "such",
    "topic", "understanding", "used", "using", "value", "when", "where",
    "which", "while", "with",
}

PRONOUNS = {
    "i", "me", "my", "mine", "you", "your", "yours", "he", "him", "his",
    "she", "her", "hers", "it", "its", "we", "us", "our", "ours", "they",
    "them", "their", "theirs", "this", "that", "these", "those",
}

UI_WORDS = {
    "button", "card", "click", "dashboard", "dropdown", "field", "filter",
    "form", "home", "input", "label", "login", "menu", "modal", "next",
    "page", "panel", "previous", "profile", "screen", "search", "section",
    "select", "sidebar", "signup", "submit", "tab", "toggle", "upload",
}

VERBS = {
    "add", "added", "adding", "build", "building", "change", "changing",
    "choose", "chosen", "click", "continue", "create", "created", "creates",
    "creating", "do", "does", "done", "explain", "explains", "generate",
    "generated", "go", "grow", "grows", "learn", "learning", "make", "makes",
    "read", "reading", "return", "returned", "save", "saved", "show",
    "shows", "start", "started", "stop", "stopping", "understand",
    "understanding", "use", "used", "using",
}

ADJECTIVES = {
    "basic", "better", "common", "different", "easy", "first", "general",
    "good", "initial", "important", "large", "main", "many", "meaningful",
    "next", "other", "random", "real", "same", "short", "simple",
    "specific", "specified", "useful",
}

KNOWN_EDUCATIONAL_TOPICS = {
    "arrays", "functions", "base case", "arraylist", "linked list", "binary tree", "avl tree", "recursion",
    "hashmap", "hashset", "dynamic programming", "operating system",
    "machine learning", "neural network", "database", "graph", "heap",
    "stack", "queue", "sorting", "searching", "object oriented programming",
    "process scheduling", "memory management", "supervised learning",
    "array", "linked lists", "binary search tree", "tree traversal",
    "depth first search", "breadth first search", "dfs", "bfs", "decision tree",
    "random forest", "gradient descent", "overfitting", "underfitting",
    "linear regression", "logistic regression", "classification",
    "clustering", "cell", "mitochondria", "dna", "rna", "photosynthesis",
    "osmosis", "enzyme", "chromosome", "protein synthesis",
}

TECHNICAL_SIGNALS = {
    "algorithm", "algebra", "array", "backpropagation", "biology", "case",
    "cell", "classification", "clustering", "collection", "complexity",
    "database", "descent", "dna", "dynamic", "enzyme", "forest", "function",
    "graph", "hash", "heap", "learning", "linear", "linked", "list",
    "machine", "management", "memory", "mitochondria", "network", "neural",
    "operating", "overfitting", "pointer", "programming", "queue",
    "recursion", "regression", "scheduling", "search", "stack", "structure",
    "supervised", "system", "tree", "traversal",
}


def normalize_topic_name(topic):
    topic = " ".join((topic or "").replace("_", " ").split())
    special_names = {
        "arraylist": "ArrayList",
        "hashmap": "HashMap",
        "hashset": "HashSet",
        "avl tree": "AVL Tree",
        "dfs": "DFS",
        "bfs": "BFS",
        "dna": "DNA",
        "rna": "RNA",
    }
    lower = topic.lower()

    if lower in special_names:
        return special_names[lower]

    return " ".join(word.capitalize() for word in topic.split())


def _has_domain_signal(clean):
    lower = clean.lower()
    words = lower.split()

    if lower in KNOWN_EDUCATIONAL_TOPICS:
        return True
    if any(word in TECHNICAL_SIGNALS for word in words):
        return True
    if clean.isupper() and 3 <= len(clean) <= 8:
        return True
    if re.search(r"[a-z][A-Z]", clean):
        return True

    return False


def is_valid_topic(topic, approved_topics=None):
    clean = normalize_topic_name(topic)
    lower = clean.lower()
    words = lower.split()

    if len(clean.replace(" ", "")) < 3:
        return False
    if not re.fullmatch(r"[A-Za-z0-9+#.\- ]+", clean):
        return False
    if any(char in clean for char in ".?!,:;"):
        return False
    if lower in COMMON_WORDS or lower in PRONOUNS or lower in UI_WORDS:
        return False
    if len(words) == 1 and (lower in VERBS or lower in ADJECTIVES):
        return False
    if any(word in PRONOUNS or word in UI_WORDS for word in words):
        return False
    if len(words) > 6:
        return False
    if not _has_domain_signal(clean):
        return False
    if len(clean.split()) == 1 and lower not in KNOWN_EDUCATIONAL_TOPICS:
        # Single generic words are a major source of bad recommendations.
        return lower in {
            "array", "arrays", "recursion", "arraylist", "hashmap", "hashset",
            "heap", "stack", "queue", "graph", "cell", "mitochondria", "dna",
            "rna", "enzyme", "chromosome", "overfitting", "underfitting",
        }
    if approved_topics and lower not in {item.lower() for item in approved_topics}:
        return False

    return True


def validate_concept(concept):
    if isinstance(concept, dict):
        name = concept.get("name") or concept.get("topic") or ""
    else:
        name = concept

    return normalize_topic_name(name) if is_valid_topic(name) else None


def validate_concepts(concepts, limit=10):
    clean_topics = []

    for concept in concepts or []:
        clean = validate_concept(concept)
        if clean and clean not in clean_topics:
            clean_topics.append(clean)
        if len(clean_topics) == limit:
            break

    return clean_topics


def filter_valid_topics(topics, approved_topics=None, limit=8):
    if approved_topics:
        return [
            topic for topic in validate_concepts(topics, limit=limit)
            if topic.lower() in {item.lower() for item in approved_topics}
        ]

    return validate_concepts(topics, limit=limit)
