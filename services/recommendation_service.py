"""
recommendation_service.py

Responsible ONLY for:
- Recommendation scoring, ranking, and filtering
- Computing confidence scores
- Generating educational explanations and learning benefits for recommendations
- Curriculum ordering and educational dependency reasoning

This service consumes graph data but does NOT execute Cypher queries directly.
"""

from utils.topic_validator import canonicalize_concept_name, is_valid_topic, logger


RECOMMENDATION_WEIGHTS = {
    "prerequisite": 0.40,
    "curriculum": 0.25,
    "semantic": 0.20,
    "graph_distance": 0.10,
    "goal": 0.05,
}

# Domain curriculum dependency maps for strong pedagogical recommendations
CURRICULUM_PREREQUISITE_MAP = {
    "linked list": ["Pointers", "Nodes", "Memory Allocation", "Arrays"],
    "arraylist": ["Arrays", "Indexed Storage", "Object Oriented Programming"],
    "binary tree": ["Recursion", "Linked List", "Tree Traversal", "Pointers"],
    "avl tree": ["Binary Tree", "Binary Search Tree", "Tree BalanceFactor"],
    "hashmap": ["Arrays", "Hash Function", "Collision Handling"],
    "hashset": ["HashMap", "Hashing"],
    "recursion": ["Functions", "Call Stack", "Base Case"],
    "stack": ["Arrays", "Linked List", "Pointers"],
    "queue": ["Arrays", "Linked List", "FIFO Principle"],
    "graph": ["Linked List", "Recursion", "Depth First Search", "Breadth First Search"],
    "operating system": ["Computer Architecture", "Processes", "Memory Management"],
    "machine learning": ["Python Programming", "Linear Algebra", "Statistics", "Data Preprocessing"],
    "supervised learning": ["Machine Learning", "Linear Regression", "Logistic Regression"],
    "neural network": ["Machine Learning", "Linear Algebra", "Gradient Descent", "Backpropagation"],
}

CURRICULUM_NEXT_MAP = {
    "linked list": ["Doubly Linked List", "Circular Linked List", "Stack", "Queue"],
    "arraylist": ["Linked List", "HashMap", "Collections Framework"],
    "binary tree": ["Binary Search Tree", "AVL Tree", "Heap", "Graphs"],
    "avl tree": ["Red Black Tree", "B-Tree"],
    "hashmap": ["HashSet", "Collision Handling", "ConcurrentHashMap"],
    "recursion": ["Binary Tree", "Dynamic Programming", "Backtracking"],
    "operating system": ["Process Scheduling", "Memory Management", "File Systems"],
    "machine learning": ["Supervised Learning", "Unsupervised Learning", "Neural Network"],
}


def calculate_recommendation_score(candidate_name, target_topic, relation_type=None, graph_dist=1, user_goal=None):
    cand_lower = candidate_name.lower()
    target_lower = target_topic.lower()

    # 1. Prerequisite strength (0.0 to 1.0)
    prereq_score = 0.0
    known_prereqs = [p.lower() for p in CURRICULUM_PREREQUISITE_MAP.get(target_lower, [])]
    if cand_lower in known_prereqs or relation_type in ("PREREQUISITE", "PREREQUISITE_OF", "requires", "builds_on"):
        prereq_score = 1.0
    elif relation_type in ("USES", "IMPLEMENTS", "PART_OF"):
        prereq_score = 0.7

    # 2. Curriculum progression (0.0 to 1.0)
    curriculum_score = 0.0
    known_nexts = [n.lower() for n in CURRICULUM_NEXT_MAP.get(target_lower, [])]
    if cand_lower in known_nexts or relation_type in ("NEXT_TOPIC", "EXTENDS", "ALTERNATIVE_TO", "SPECIAL_CASE_OF"):
        curriculum_score = 1.0
    elif cand_lower in known_prereqs:
        curriculum_score = 0.8

    # 3. Semantic similarity (0.0 to 1.0)
    semantic_score = 0.0
    cand_tokens = set(cand_lower.split())
    target_tokens = set(target_lower.split())
    overlap = cand_tokens.intersection(target_tokens)
    if overlap:
        semantic_score = len(overlap) / max(len(cand_tokens), len(target_tokens))
    elif any(token in target_lower for token in cand_tokens) or any(token in cand_lower for token in target_tokens):
        semantic_score = 0.5
    else:
        semantic_score = 0.3

    # 4. Graph distance (0.0 to 1.0)
    dist_score = max(0.0, 1.0 - (graph_dist - 1) * 0.4)

    # 5. Goal relevance (0.0 to 1.0)
    goal_score = 0.0
    if user_goal and user_goal.lower() in cand_lower:
        goal_score = 1.0
    elif user_goal:
        goal_score = 0.4

    # Weighted final score calculation
    final_score = (
        RECOMMENDATION_WEIGHTS["prerequisite"] * prereq_score +
        RECOMMENDATION_WEIGHTS["curriculum"] * curriculum_score +
        RECOMMENDATION_WEIGHTS["semantic"] * semantic_score +
        RECOMMENDATION_WEIGHTS["graph_distance"] * dist_score +
        RECOMMENDATION_WEIGHTS["goal"] * goal_score
    )

    confidence = round(min(0.99, max(0.50, final_score + 0.10)), 2)
    return round(final_score, 2), confidence


def generate_recommendation_explanation(candidate_name, target_topic, relation_type, is_prerequisite):
    cand_clean = canonicalize_concept_name(candidate_name)
    target_clean = canonicalize_concept_name(target_topic)

    if is_prerequisite or relation_type in ("PREREQUISITE", "PREREQUISITE_OF", "requires"):
        reason = f"{cand_clean} is a fundamental prerequisite for {target_clean}."
        benefit = f"Mastering {cand_clean} provides essential theoretical background required before studying {target_clean}."
    elif relation_type in ("NEXT_TOPIC", "EXTENDS", "builds_on"):
        reason = f"{cand_clean} builds directly upon concepts introduced in {target_clean}."
        benefit = f"Studying {cand_clean} applies knowledge from {target_clean} to more complex problem domains."
    elif relation_type in ("USES", "IMPLEMENTS", "PART_OF"):
        reason = f"{cand_clean} is a core structural component or implementation pattern used in {target_clean}."
        benefit = f"Understanding {cand_clean} reveals how {target_clean} is constructed under the hood."
    else:
        reason = f"{cand_clean} shares complementary concepts with {target_clean}."
        benefit = f"Learning {cand_clean} broadens your domain understanding alongside {target_clean}."

    return reason, benefit


def rank_recommendations(raw_suggestions, target_topic, user_goal=None, limit=5):
    """
    Ranks raw candidate suggestions using weighted educational scoring.
    """
    target_clean = canonicalize_concept_name(target_topic)
    scored_candidates = []
    seen_names = set()

    for item in raw_suggestions:
        if isinstance(item, dict):
            cand_name = canonicalize_concept_name(item.get("topic") or item.get("name"))
            rel_type = item.get("relation") or "RELATED_TO"
            why_override = item.get("why")
        else:
            cand_name = canonicalize_concept_name(item)
            rel_type = "RELATED_TO"
            why_override = None

        if not cand_name or not is_valid_topic(cand_name) or cand_name.lower() == target_clean.lower():
            continue

        if cand_name.lower() in seen_names:
            continue

        seen_names.add(cand_name.lower())

        is_prereq = cand_name.lower() in [p.lower() for p in CURRICULUM_PREREQUISITE_MAP.get(target_clean.lower(), [])]
        score, confidence = calculate_recommendation_score(
            cand_name, target_clean, relation_type=rel_type, user_goal=user_goal
        )

        reason, benefit = generate_recommendation_explanation(
            cand_name, target_clean, rel_type, is_prereq
        )

        if why_override and len(why_override) > 10:
            reason = why_override

        scored_candidates.append({
            "topic": cand_name,
            "score": score,
            "confidence": confidence,
            "reason": reason,
            "learning_benefit": benefit,
            "matched_relationships": [rel_type],
        })

    # Sort candidates descending by score
    scored_candidates.sort(key=lambda x: x["score"], reverse=True)

    logger.info(f"[VALIDATION] Recommendation engine ranked {len(scored_candidates)} topics for '{target_clean}'.")
    return scored_candidates[:limit]
