"""
recommendation_service.py

Responsible ONLY for:
- Recommendation scoring, ranking, and filtering using configurable weights
- Computing confidence scores
- Generating educational explanations and learning benefits for recommendations
- Dynamic relationship-based educational dependency reasoning & semantic section routing

This service consumes graph data from Neo4j but does NOT execute Cypher queries directly.
No hardcoded subject lookup tables exist here. Neo4j is the single source of truth.
"""

from utils.topic_validator import canonicalize_concept_name, is_valid_topic, logger


RECOMMENDATION_WEIGHTS = {
    "prerequisite": 0.40,
    "curriculum": 0.25,
    "semantic": 0.20,
    "graph_distance": 0.10,
    "goal": 0.05,
}

RELATION_SECTION_MAP = {
    # Learn Before (Prerequisites)
    "PREREQUISITE_OF": "before",
    "USES": "before",
    "REQUIRED_FOR": "before",
    "FOUNDATION_OF": "before",
    "PREREQUISITE": "before",
    "REQUIRES": "before",

    # Learn Next (Progressions)
    "BUILDS_ON": "after",
    "EXTENDS": "after",
    "SPECIAL_CASE_OF": "after",
    "IMPLEMENTS": "after",
    "NEXT_TOPIC": "after",
    "FOLLOWS": "after",

    # Related Topics (Lateral / Alternatives / Components)
    "RELATED_TO": "related",
    "SIMILAR_TO": "related",
    "ALTERNATIVE_TO": "related",
    "PART_OF": "related",
    "RELATED_TOPIC": "related",

    # Applications
    "APPLICATION_OF": "applications",
    "USED_IN": "applications",
}


def get_educational_category(relation_type, fallback_direction="related"):
    rel_upper = str(relation_type or "").strip().upper()
    if rel_upper in RELATION_SECTION_MAP:
        return RELATION_SECTION_MAP[rel_upper]

    if fallback_direction in ("before", "after", "related", "applications"):
        return fallback_direction

    return "related"


def calculate_recommendation_score(candidate_name, target_topic, relation_type=None, graph_dist=1, user_goal=None):
    cand_lower = candidate_name.lower()
    target_lower = target_topic.lower()
    rel_type_upper = str(relation_type or "").upper()

    # 1. Prerequisite strength (0.0 to 1.0) based on graph relationship type
    prereq_score = 0.0
    if rel_type_upper in ("PREREQUISITE", "PREREQUISITE_OF", "REQUIRES", "BUILDS_ON"):
        prereq_score = 1.0
    elif rel_type_upper in ("USES", "IMPLEMENTS", "PART_OF"):
        prereq_score = 0.7

    # 2. Curriculum progression (0.0 to 1.0) based on educational progression labels
    curriculum_score = 0.0
    if rel_type_upper in ("NEXT_TOPIC", "EXTENDS", "ALTERNATIVE_TO", "SPECIAL_CASE_OF", "BUILDS_ON"):
        curriculum_score = 1.0
    elif rel_type_upper in ("PREREQUISITE", "PREREQUISITE_OF"):
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
    rel_type_upper = str(relation_type or "").upper()

    if is_prerequisite or rel_type_upper in ("PREREQUISITE", "PREREQUISITE_OF", "REQUIRES"):
        reason = f"{cand_clean} is a fundamental prerequisite for {target_clean}."
        benefit = f"Mastering {cand_clean} provides essential theoretical background required before studying {target_clean}."
    elif rel_type_upper in ("NEXT_TOPIC", "EXTENDS", "BUILDS_ON"):
        reason = f"{cand_clean} builds directly upon concepts introduced in {target_clean}."
        benefit = f"Studying {cand_clean} applies knowledge from {target_clean} to more complex problem domains."
    elif rel_type_upper in ("USES", "IMPLEMENTS", "PART_OF"):
        reason = f"{cand_clean} is a core structural component or implementation pattern used in {target_clean}."
        benefit = f"Understanding {cand_clean} reveals how {target_clean} is constructed under the hood."
    elif rel_type_upper in ("SPECIAL_CASE_OF", "ALTERNATIVE_TO"):
        reason = f"{cand_clean} is a specialized form or alternative approach connected with {target_clean}."
        benefit = f"Learning {cand_clean} provides critical comparative insights alongside {target_clean}."
    elif rel_type_upper in ("APPLICATION_OF", "USED_IN"):
        reason = f"{cand_clean} is a practical real-world application of {target_clean}."
        benefit = f"Exploring {cand_clean} demonstrates how {target_clean} is utilized in software production systems."
    else:
        reason = f"{cand_clean} shares complementary concepts with {target_clean}."
        benefit = f"Learning {cand_clean} broadens your domain understanding alongside {target_clean}."

    return reason, benefit


def rank_recommendations(raw_suggestions, target_topic, user_goal=None, limit=5):
    """
    Legacy wrapper ranking raw candidate suggestions using weighted educational scoring.
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

        rel_upper = rel_type.upper()
        is_prereq = rel_upper in ("PREREQUISITE", "PREREQUISITE_OF", "REQUIRES")
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

    scored_candidates.sort(key=lambda x: x["score"], reverse=True)
    logger.info(f"[VALIDATION] Recommendation engine ranked {len(scored_candidates)} topics for '{target_clean}'.")
    return scored_candidates[:limit]


def categorize_and_rank_recommendations(raw_candidates_by_source, target_topic, user_goal=None, limit=5):
    """
    Categorizes raw candidate items into 4 distinct educational sections:
    - before (Learn Before)
    - after (Learn Next)
    - related (Related Topics)
    - applications (Applications)

    Performs strict cross-section deduplication using section hierarchy:
    before > after > applications > related
    Ensures NO topic appears in multiple sections.
    """
    target_clean = canonicalize_concept_name(target_topic)
    categorized_items = {
        "before": [],
        "after": [],
        "related": [],
        "applications": [],
    }

    # Gather items by source direction or explicit relation
    for source_key, items in raw_candidates_by_source.items():
        fallback_dir = "before" if source_key == "before" else ("after" if source_key == "after" else "related")

        for item in items or []:
            if isinstance(item, dict):
                cand_name = canonicalize_concept_name(item.get("topic") or item.get("name"))
                rel_type = item.get("relation")
                why_override = item.get("why")
            else:
                cand_name = canonicalize_concept_name(item)
                rel_type = None
                why_override = None

            if not cand_name or not is_valid_topic(cand_name) or cand_name.lower() == target_clean.lower():
                continue

            section = get_educational_category(rel_type, fallback_direction=fallback_dir)
            rel_name = (rel_type or "RELATED_TO").upper()

            is_prereq = section == "before"
            score, confidence = calculate_recommendation_score(
                cand_name, target_clean, relation_type=rel_name, user_goal=user_goal
            )
            reason, benefit = generate_recommendation_explanation(
                cand_name, target_clean, rel_name, is_prereq
            )
            if why_override and len(why_override) > 10:
                reason = why_override

            rec_obj = {
                "topic": cand_name,
                "score": score,
                "confidence": confidence,
                "reason": reason,
                "learning_benefit": benefit,
                "matched_relationships": [rel_name],
                "why": reason,
            }
            categorized_items[section].append(rec_obj)

    # Sort each category descending by score
    for sec in categorized_items:
        categorized_items[sec].sort(key=lambda x: x["score"], reverse=True)

    # Global cross-section deduplication (hierarchy: before > after > applications > related)
    assigned_topics = set()
    final_categorized = {}

    for sec in ("before", "after", "applications", "related"):
        sec_unique = []
        for rec in categorized_items[sec]:
            t_low = rec["topic"].lower()
            if t_low not in assigned_topics:
                assigned_topics.add(t_low)
                sec_unique.append(rec)

        final_categorized[sec] = sec_unique[:limit]

    logger.info(
        f"[SEMANTIC ROUTING] Categorized recommendations for '{target_clean}': "
        f"Before: {len(final_categorized['before'])}, "
        f"After: {len(final_categorized['after'])}, "
        f"Applications: {len(final_categorized['applications'])}, "
        f"Related: {len(final_categorized['related'])}"
    )

    return final_categorized
