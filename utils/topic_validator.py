import difflib
import logging
import re
import sys
import time

# Configure Python's standard logging module
logger = logging.getLogger("ai_learnmate")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class PipelineAuditTracker:
    def __init__(self):
        self.raw_concepts = 0
        self.normalized_concepts = 0
        self.accepted = 0
        self.rejected = 0
        self.duplicates = 0
        self.hallucinations = 0
        self.generic_words = 0
        self.ui_words = 0
        self.neo4j_nodes = 0
        self.neo4j_relationships = 0
        self.seen_concepts = set()
        self.seen_relationships = set()
        self.start_time = None

    def reset(self):
        self.raw_concepts = 0
        self.normalized_concepts = 0
        self.accepted = 0
        self.rejected = 0
        self.duplicates = 0
        self.hallucinations = 0
        self.generic_words = 0
        self.ui_words = 0
        self.neo4j_nodes = 0
        self.neo4j_relationships = 0
        self.seen_concepts = set()
        self.seen_relationships = set()
        self.start_time = time.perf_counter()

    def print_report(self):
        elapsed = 0.0
        if self.start_time is not None:
            elapsed = time.perf_counter() - self.start_time

        logger.info("\n========== PIPELINE REPORT ==========")
        logger.info(f"Raw concepts: {self.raw_concepts}")
        logger.info(f"Normalized concepts: {self.normalized_concepts}")
        logger.info(f"Accepted concepts: {self.accepted}")
        logger.info(f"Rejected concepts: {self.rejected}")
        logger.info(f"Duplicate concepts: {self.duplicates}")
        logger.info(f"Hallucinated concepts: {self.hallucinations}")
        logger.info(f"Generic words rejected: {self.generic_words}")
        logger.info(f"UI words rejected: {self.ui_words}")
        logger.info(f"Neo4j nodes created: {self.neo4j_nodes}")
        logger.info(f"Neo4j relationships created: {self.neo4j_relationships}")
        logger.info(f"Total processing time: {elapsed:.2f}s")
        logger.info("=====================================\n")


audit_tracker = PipelineAuditTracker()


COMMON_WORDS = {
    "a", "an", "the", "and", "or", "but", "if", "because", "as", "until",
    "while", "of", "at", "by", "for", "with", "about", "against", "between",
    "into", "through", "during", "before", "after", "above", "below", "to",
    "from", "up", "down", "in", "out", "on", "off", "over", "under", "again",
    "further", "then", "once", "able", "also", "being", "continue", "creates",
    "data", "does", "done", "each", "elements", "environment", "example",
    "first", "grow", "important", "initial", "items", "learn", "many", "more",
    "most", "next", "other", "same", "simple", "size", "specified", "step",
    "such", "topic", "understanding", "used", "using", "value", "when",
    "where", "which", "while", "overview", "introduction", "summary", "conclusion",
    "thing", "things", "concept", "concepts", "computer topic", "learning topic",
    "educational concept", "main topic",
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
    "navigation", "nav", "back", "forward", "loading", "error", "success",
    "header", "footer", "navbar", "checkpoint", "result", "view",
}

VERBS = {
    "add", "added", "adding", "build", "building", "change", "changing",
    "choose", "chosen", "click", "continue", "create", "created", "creates",
    "creating", "do", "does", "done", "explain", "explains", "generate",
    "generated", "go", "grow", "grows", "learn", "learning", "make", "makes",
    "read", "reading", "return", "returned", "save", "saved", "show",
    "shows", "start", "started", "stop", "stopping", "understand",
    "understanding", "use", "used", "using", "write", "writing",
}

ADJECTIVES = {
    "basic", "better", "common", "different", "easy", "first", "general",
    "good", "initial", "important", "large", "main", "many", "meaningful",
    "next", "other", "random", "real", "simple", "specific", "specified", "useful",
}

KNOWN_EDUCATIONAL_TOPICS = {
    "arrays", "functions", "base case", "arraylist", "linked list", "binary tree", "avl tree", "recursion",
    "hashmap", "hashset", "dynamic programming", "operating system", "operating systems",
    "machine learning", "neural network", "database", "databases", "graph", "heap",
    "stack", "queue", "sorting", "searching", "object oriented programming",
    "process scheduling", "memory management", "supervised learning",
    "array", "linked lists", "binary search tree", "tree traversal",
    "depth first search", "breadth first search", "dfs", "bfs", "decision tree",
    "random forest", "gradient descent", "overfitting", "underfitting",
    "linear regression", "logistic regression", "classification",
    "clustering", "cell", "mitochondria", "dna", "rna", "photosynthesis",
    "osmosis", "enzyme", "chromosome", "protein synthesis", "collections framework",
    "doubly linked list", "circular linked list", "call stack", "file systems",
    "hash function", "collision handling", "dictionary", "time complexity",
    "data preprocessing", "pointers", "pointer", "nodes", "node", "memory allocation",
    "processes", "computer architecture", "tree", "trees", "matrix", "vectors",
    "programming fundamentals", "programming fundamental", "data structures", "algorithms",
    "computer networks", "network fundamental", "concurrency", "distributed systems",
    "caching", "load balancing", "system design", "linear algebra", "probability",
    "statistics", "model evaluation", "deep learning", "python programming",
    "quantum mechanics", "quantum computing", "microservices architecture",
    "quick sort", "merge sort", "bubble sort", "insertion sort", "selection sort",
    "radix sort", "heap sort", "hash table", "hash tables", "hashing", "sorting algorithms",
    "osi model", "osi", "tcp/ip", "ip",
    "optics", "ray optics", "wave optics", "fiber optics", "quantum optics", "thermodynamics", "kinematics", "electromagnetism",
}

TECHNICAL_SIGNALS = {
    "algorithm", "algorithms", "algebra", "array", "backpropagation", "biology", "case",
    "cell", "classification", "clustering", "collection", "complexity",
    "database", "databases", "descent", "dna", "dynamic", "enzyme", "forest", "function",
    "graph", "hash", "hashing", "heap", "learning", "linear", "linked", "list",
    "machine", "management", "memory", "mitochondria", "network", "networks", "neural",
    "operating", "overfitting", "pointer", "pointers", "node", "nodes",
    "programming", "queue", "recursion", "regression", "scheduling", "search",
    "sort", "sorting", "stack", "structure", "structures", "supervised", "system", "systems", "tree", "traversal",
    "framework", "architecture", "security", "cryptography", "polity",
    "geography", "economy", "ethics", "concurrency", "caching", "balancing",
    "design", "probability", "statistics", "evaluation", "physics", "mechanics",
    "quantum", "fundamental", "fundamentals", "table", "tables", "osi", "tcp", "ip",
    "optics", "ray", "wave", "light", "lens", "mirror", "reflection", "refraction", "laser", "thermodynamics", "electromagnetism",
    "fusion", "nuclear", "computing", "neuromorphic",
    "cardiovascular", "immunology", "pharmacology", "pathology", "anatomy", "physiology", "atp", "calvin", "chloroplast", "photosynthesis", "respiration", "nucleosynthesis", "plasma", "tokamak", "orbital", "orbitals",
    "circuit", "semiconductor", "amplifier", "fourier", "fluid", "stress", "strain", "statics", "dynamics", "transistor", "diode", "voltage", "current",
    "microeconomics", "macroeconomics", "finance", "equity", "derivative", "option", "inflation", "gdp", "portfolio", "asset", "valuation",
    "constitutional", "jurisprudence", "statute", "revolution", "feudalism", "cognition", "behavior", "neuroscience", "psychology", "history", "law", "mathematics", "math",
}

SPECIAL_CASES = {
    "arraylist": "ArrayList",
    "hashmap": "HashMap",
    "hashset": "HashSet",
    "avl tree": "AVL Tree",
    "dfs": "DFS",
    "bfs": "BFS",
    "dna": "DNA",
    "rna": "RNA",
    "api": "API",
    "http": "HTTP",
    "oop": "OOP",
    "sql": "SQL",
    "dbms": "DBMS",
    "upsc": "UPSC",
    "gate": "GATE",
    "cat": "CAT",
    "mcq": "MCQ",
    "rest": "REST",
    "cpu": "CPU",
    "ram": "RAM",
    "os": "OS",
    "osi model": "OSI Model",
    "osi": "OSI",
    "tcp/ip": "TCP/IP",
    "ip": "IP",
    "programming fundamental": "Programming Fundamentals",
    "programming fundamentals": "Programming Fundamentals",
}


def canonicalize_concept_name(name):
    """
    Normalize every concept name:
    1. Trim whitespace & strip trailing punctuation
    2. Collapse multiple spaces
    3. Replace hyphens with spaces
    4. Normalize plural to singular form using exceptions
    5. Standardize capitalization
    """
    if not name or not isinstance(name, str):
        return ""

    # 1. Trim whitespace and remove trailing/leading punctuation
    cleaned = name.strip().strip('.,;:!?-"\'')

    # 2. Collapse multiple spaces
    cleaned = re.sub(r'\s+', ' ', cleaned)

    # 3. Replace hyphens with spaces
    cleaned = cleaned.replace("-", " ")

    # 4. Handle plural to singular
    words = cleaned.split()
    if words:
        last_word = words[-1]
        lower_last = last_word.lower()

        singular_exceptions = {
            'process', 'processes', 'database', 'databases', 'statistics', 'analysis', 'hypothesis',
            'oss', 'dbms', 'gps', 'graphics', 'physics', 'mathematics', 'mechanics', 'quantum mechanics',
            'coordinates', 'class', 'bias', 'canvas', 'networks', 'neural networks', 'computer networks',
            'systems', 'distributed systems', 'operating systems', 'file systems',
            'fundamentals', 'programming fundamentals', 'data structures', 'algorithms',
            'optics', 'ray optics', 'wave optics', 'fiber optics', 'quantum optics', 'thermodynamics', 'kinematics', 'electromagnetism'
        }

        is_except = False
        full_lower = cleaned.lower()
        if full_lower in singular_exceptions or lower_last in singular_exceptions:
            is_except = True

        if not is_except and last_word.endswith('s'):
            if lower_last.endswith('ss') or lower_last.endswith('sis') or len(lower_last) <= 3:
                pass
            elif lower_last.endswith('ies'):
                words[-1] = last_word[:-3] + 'y'
                cleaned = " ".join(words)
            elif lower_last.endswith('es'):
                if any(lower_last.endswith(suffix) for suffix in ('ches', 'shes', 'xes', 'ses', 'zes')):
                    words[-1] = last_word[:-2]
                elif lower_last == 'matrices':
                    words[-1] = last_word[:-5] + 'x'
                elif lower_last == 'indices':
                    words[-1] = last_word[:-5] + 'ex'
                else:
                    words[-1] = last_word[:-1]
                cleaned = " ".join(words)
            else:
                words[-1] = last_word[:-1]
                cleaned = " ".join(words)

    # 5. Normalize capitalization
    words = cleaned.split()
    for i, word in enumerate(words):
        lower_word = word.lower()
        full_cand = " ".join(words[:i+1]).lower()
        if lower_word in SPECIAL_CASES:
            words[i] = SPECIAL_CASES[lower_word]
        elif word.isupper() and len(word) >= 2:
            words[i] = word
        else:
            words[i] = word.capitalize()

    final_cleaned = " ".join(words)
    if final_cleaned.lower() in SPECIAL_CASES:
        final_cleaned = SPECIAL_CASES[final_cleaned.lower()]

    if name != final_cleaned:
        logger.info(f"[CANONICALIZATION] Normalized: '{name}' -> '{final_cleaned}'")

    return final_cleaned


def normalize_topic_name(topic):
    """Maintain backward compatibility with existing codebase callers."""
    return canonicalize_concept_name(topic)


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


def is_hallucinated(concept_name, pdf_text=None, ai_topics=None, curated_topics=None):
    """
    Verify concept existence against PDF text, AI roadmap output, or curated educational topics.
    Uses normalized comparison and fuzzy/token matching.
    """
    norm_name = canonicalize_concept_name(concept_name).lower()
    if not norm_name:
        return True

    # 1. Verification against Curated Topics
    check_curated = curated_topics if curated_topics is not None else KNOWN_EDUCATIONAL_TOPICS
    for topic in check_curated:
        if norm_name == canonicalize_concept_name(topic).lower():
            return False

    # 2. Verification against AI topics
    if ai_topics:
        for topic in ai_topics:
            cand = canonicalize_concept_name(topic).lower()
            if norm_name == cand or cand in norm_name or norm_name in cand:
                return False

    # 3. Verification against PDF text
    if pdf_text:
        clean_text = re.sub(r'\s+', ' ', pdf_text.replace("-", " ")).lower()
        # Word boundary exact phrase match
        pattern = r'\b' + re.escape(norm_name) + r'\b'
        if re.search(pattern, clean_text):
            return False

        # Token set match for multi-word concepts
        norm_tokens = set(norm_name.split())
        if len(norm_tokens) > 1 and all(token in clean_text for token in norm_tokens):
            return False

        # Fuzzy matching for spelling variations
        if len(norm_name) >= 4:
            for word in clean_text.split():
                if difflib.SequenceMatcher(None, norm_name, word).ratio() >= 0.88:
                    return False

    return True


FORBIDDEN_MODIFIERS = {
    "basic", "intermediate", "advanced", "applied", "practical", "core", "expert",
    "mastering", "introductory", "fundamental", "overview", "basics", "principles",
    "introduction", "implementation", "implementations", "application", "applications",
    "optimization", "optimizations", "concept", "concepts", "topic", "topics"
}

def is_placeholder_concept(topic_name, main_topic=None):
    if not topic_name or not isinstance(topic_name, str):
        return True, "Empty concept name"
    
    cleaned = canonicalize_concept_name(topic_name)
    low = cleaned.lower()

    if main_topic:
        main_clean = canonicalize_concept_name(main_topic).lower()
        main_forms = {main_clean}
        main_forms.add(main_clean + 's')
        main_forms.add(main_clean + 'es')
        if main_clean.endswith('y') and len(main_clean) > 1 and main_clean[-2] not in 'aeiou':
            main_forms.add(main_clean[:-1] + 'ies')

        main_pattern = r'\b(' + '|'.join(re.escape(form) for form in main_forms) + r')\b'

        # Check prefixes & suffixes template patterns wrapping the main topic
        prefixes = r"(basic|applied|advanced|intermediate|practical|introduction to|intro to|implementation of|overview of|basics of|principles of)"
        suffixes = r"(concept|concepts|implementation|implementations|application|applications|optimization|optimizations|topic|topics)"
        
        pattern_1 = r"^" + prefixes + r"\s+" + main_pattern + r"(\s+" + suffixes + r")?$"
        if re.match(pattern_1, low):
            return True, f"Concept '{cleaned}' is a generated template wrapping main topic '{main_topic}'"

        pattern_2 = r"^" + main_pattern + r"\s+" + suffixes + r"$"
        if re.match(pattern_2, low):
            return True, f"Concept '{cleaned}' is a generated template wrapping main topic '{main_topic}'"

        # Check if the topic name consists only of the main topic padded with generic adjectives/suffixes
        match = re.search(main_pattern, low)
        if match:
            start, end = match.span()
            remainder = (low[:start] + " " + low[end:]).strip().split()
            if remainder and all(w in FORBIDDEN_MODIFIERS for w in remainder):
                return True, f"Concept '{cleaned}' is a placeholder variation of main topic '{main_topic}'"

    return False, "Not a placeholder"


def check_node_exists_in_neo4j(concept_name):
    """
    Check if a concept node exists in Neo4j database.
    Uses dynamic import to avoid circular dependency.
    """
    try:
        from services.neo4j_service import get_neo4j_driver
        clean_name = canonicalize_concept_name(concept_name)
        if not clean_name:
            return False
        with get_neo4j_driver() as driver:
            with driver.session() as session:
                result = session.run(
                    "MATCH (c:Concept) WHERE toLower(c.name) = toLower($name) RETURN count(c) > 0 AS exists",
                    name=clean_name
                ).single()
                return result and result["exists"]
    except Exception as exc:
        logger.debug(f"Failed to check concept existence in Neo4j: {exc}")
        return False


def get_topic_validation_details(topic, pdf_text=None, ai_topics=None, curated_topics=None, main_topic=None, is_prereq=False, validated_topics=None, explanation=None):
    """
    Centralized validation function for concepts.
    Returns (is_valid, reason). Updates audit_tracker metrics.
    Uses confidence-based validation: Priority 1 to 6.
    """
    audit_tracker.raw_concepts += 1

    if not topic or not isinstance(topic, str):
        audit_tracker.rejected += 1
        return False, "Concept name is empty or not a string"

    cleaned = canonicalize_concept_name(topic)
    audit_tracker.normalized_concepts += 1

    if not cleaned:
        audit_tracker.rejected += 1
        return False, "Concept name becomes empty after canonicalization"

    lower = cleaned.lower()
    words = lower.split()

    # Priority 1: Already validated during the current request
    if validated_topics and (lower in validated_topics or cleaned in validated_topics):
        return True, "Valid concept (Priority 1: Already validated in current request)"

    # Priority 2: Already exists in Neo4j
    if check_node_exists_in_neo4j(cleaned):
        return True, "Valid concept (Priority 2: Already exists in Neo4j)"

    # Keep Rejecting: Syntax & Structure Rejections
    # 1. Punctuation-only check
    if re.match(r'^[.,;:!?\-+_#*()\s]+$', cleaned):
        audit_tracker.rejected += 1
        return False, f"Concept '{cleaned}' contains only punctuation"

    # 2. Number-only check
    if cleaned.isdigit():
        audit_tracker.rejected += 1
        return False, f"Concept '{cleaned}' contains only numbers"

    # 3. Minimum length check
    if len(cleaned.replace(" ", "")) < 3:
        audit_tracker.rejected += 1
        return False, f"Concept name too short (less than 3 characters: '{cleaned}')"

    # 4. Valid characters check
    if not re.fullmatch(r"[A-Za-z0-9+#.\- ]+", cleaned):
        audit_tracker.rejected += 1
        return False, f"Concept '{cleaned}' contains invalid characters"

    # 5. Generic English words check
    if lower in COMMON_WORDS:
        audit_tracker.generic_words += 1
        audit_tracker.rejected += 1
        return False, f"Concept '{cleaned}' is a generic common English word"

    if lower in PRONOUNS:
        audit_tracker.generic_words += 1
        audit_tracker.rejected += 1
        return False, f"Concept '{cleaned}' is a pronoun"

    if len(words) == 1 and (lower in VERBS or lower in ADJECTIVES):
        audit_tracker.generic_words += 1
        audit_tracker.rejected += 1
        return False, f"Single-word concept '{cleaned}' is a verb or adjective"

    if any(w in PRONOUNS for w in words):
        audit_tracker.generic_words += 1
        audit_tracker.rejected += 1
        return False, f"Concept '{cleaned}' contains a pronoun"

    # 6. UI elements or navigation check
    if lower in UI_WORDS or any(w in UI_WORDS for w in words):
        audit_tracker.ui_words += 1
        audit_tracker.rejected += 1
        return False, f"Concept '{cleaned}' is a UI or navigation keyword"

    # 7. Placeholder Concept Check
    is_ph, ph_reason = is_placeholder_concept(cleaned, main_topic=main_topic)
    if is_ph:
        audit_tracker.rejected += 1
        return False, ph_reason

    # 8. Word count limit
    if len(words) > 6:
        audit_tracker.rejected += 1
        return False, f"Concept name too long (more than 6 words: '{cleaned}')"

    # 9. Duplicate check (internal roadmap track to prevent redundant items in same request)
    if lower in audit_tracker.seen_concepts:
        audit_tracker.duplicates += 1
        audit_tracker.rejected += 1
        return False, f"Concept '{cleaned}' is a duplicate"

    # Determine matched priority for logging
    matched_priority = "Priority 6 (Passed syntax validation)"
    if ai_topics and isinstance(ai_topics, dict) and ai_topics.get(lower, 0) > 1:
        matched_priority = "Priority 3 (Appears multiple times consistently)"
    elif explanation and isinstance(explanation, str) and len(explanation.strip()) >= 10:
        matched_priority = "Priority 4 (Has meaningful explanation)"
    elif main_topic:
        matched_priority = "Priority 5 (Has meaningful relationship to main topic)"

    return True, f"Valid concept ({matched_priority})"


def is_valid_topic(topic, approved_topics=None, validated_topics=None, main_topic=None, is_prereq=False):
    """
    Simplified check without mutating audit counters (useful for quick checks).
    Supports request-scoped validated_topics context.
    """
    if not topic or not isinstance(topic, str):
        return False
    cleaned = canonicalize_concept_name(topic)
    if not cleaned:
        return False
    lower = cleaned.lower()

    # Priority 1: Check request-scoped validated topics
    if validated_topics and (lower in validated_topics or cleaned in validated_topics):
        return True

    # Priority 2: Check Neo4j existence
    if check_node_exists_in_neo4j(cleaned):
        return True

    words = lower.split()
    if re.match(r'^[.,;:!?\-+_#*()\s]+$', cleaned):
        return False
    if cleaned.isdigit():
        return False
    if len(cleaned.replace(" ", "")) < 3:
        return False
    if not re.fullmatch(r"[A-Za-z0-9+#.\- ]+", cleaned):
        return False
    if lower in COMMON_WORDS or lower in PRONOUNS or lower in UI_WORDS:
        return False
    if len(words) == 1 and (lower in VERBS or lower in ADJECTIVES):
        return False
    if any(w in PRONOUNS or w in UI_WORDS for w in words):
        return False
    if is_placeholder_concept(cleaned, main_topic=main_topic)[0]:
        return False
    if len(words) > 6:
        return False

    # Priority 6: Passes syntax validation
    return True


def is_valid_relationship(src, dest, rel_type, why, existing_relationships=None, validated_topics=None):
    """
    Validates relationships before Neo4j storage.
    Ensures source & dest concepts exist, no self-loops, valid relation label,
    non-trivial explanation, and no duplicates. Accepts request-scoped validated_topics.
    """
    src_clean = canonicalize_concept_name(src)
    dest_clean = canonicalize_concept_name(dest)

    is_dest_prereq = (rel_type == "PREREQUISITE_OF")
    if not src_clean or not is_valid_topic(src_clean, validated_topics=validated_topics):
        return False, f"Source concept '{src}' is invalid"
    if not dest_clean or not is_valid_topic(dest_clean, validated_topics=validated_topics, main_topic=src_clean, is_prereq=is_dest_prereq):
        return False, f"Destination concept '{dest}' is invalid"

    src_norm = src_clean.lower()
    dest_norm = dest_clean.lower()
    if src_norm == dest_norm:
        return False, "Self-relationship is not allowed"

    valid_types = {
        "PREREQUISITE", "PREREQUISITE_OF", "REQUIRES", "REQUIRED_FOR", "FOUNDATION_OF", "USES",
        "BUILDS_ON", "EXTENDS", "SPECIAL_CASE_OF", "ADVANCED_FORM_OF", "NEXT_TOPIC", "FOLLOWS",
        "APPLICATION_OF", "USED_IN", "IMPLEMENTS",
        "RELATED_TO", "RELATED_TOPIC", "SIMILAR_TO", "CONNECTED_TO", "ALTERNATIVE_TO", "PART_OF"
    }
    if not rel_type or rel_type.upper() not in valid_types:
        return False, f"Relationship type '{rel_type}' is invalid"

    if not why or not isinstance(why, str) or len(why.strip()) < 10:
        return False, f"Relationship explanation is missing or too short (under 10 characters: '{why}')"

    # Check if explanation just echoes concept names
    why_lower = why.lower()
    if why_lower in (src_norm, dest_norm) or f"{src_norm} is {dest_norm}" in why_lower:
        return False, "Relationship explanation is a trivial repetition of concept names"

    rel_key = (src_norm, rel_type.upper(), dest_norm)
    if existing_relationships is not None and rel_key in existing_relationships:
        return False, "Relationship is a duplicate"

    if rel_key in audit_tracker.seen_relationships:
        return False, "Relationship is a duplicate"

    return True, "Valid relationship"


def validate_concept(concept):
    if isinstance(concept, dict):
        name = concept.get("name") or concept.get("topic") or ""
    else:
        name = concept

    return canonicalize_concept_name(name) if is_valid_topic(name) else None


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
        approved_set = {canonicalize_concept_name(item).lower() for item in approved_topics}
        return [
            topic for topic in validate_concepts(topics, limit=limit)
            if topic.lower() in approved_set
        ]

    return validate_concepts(topics, limit=limit)
