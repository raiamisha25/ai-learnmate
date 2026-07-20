"""
goal_service.py

Responsible ONLY for:
- Constructing goal roadmaps from Neo4j graph relationships and AI roadmap generation
- Expanding prerequisite chains recursively across educational tiers
- Ensuring no graph cycles and no duplicate roadmap nodes exist
- Maintaining logical prerequisite ordering from foundational roots up to the goal topic

Neo4j is the single source of truth for educational relationships.
No hardcoded subject lookup tables exist here.
"""

from services.neo4j_service import fetch_prerequisite_chain_from_neo4j
from services.roadmap_service import get_or_create_roadmap
from utils.topic_validator import canonicalize_concept_name, is_valid_topic, logger, normalize_topic_name


def build_goal_roadmap(goal_title):
    clean_goal = canonicalize_concept_name(goal_title)
    if not clean_goal or not is_valid_topic(clean_goal):
        clean_goal = normalize_topic_name(goal_title) or "Learning Goal"

    logger.info(f"[VALIDATION] Constructing deep educational roadmap for goal '{clean_goal}'...")

    # 1. Fetch AI / curated roadmap structure for goal topic with force_refresh=True to update graph
    roadmap = get_or_create_roadmap(clean_goal, force_refresh=True)

    # 2. Fetch Neo4j prerequisite DAG chain
    graph_chain = fetch_prerequisite_chain_from_neo4j(clean_goal)

    # 3. Assemble all candidate learning stages from educational tiers
    foundations = [canonicalize_concept_name(item.get("topic")) for item in roadmap.get("foundation_topics", []) if isinstance(item, dict) and item.get("topic")]
    beginners = [canonicalize_concept_name(item.get("topic")) for item in roadmap.get("beginner_topics", []) if isinstance(item, dict) and item.get("topic")]
    prereqs = [canonicalize_concept_name(item.get("topic")) for item in roadmap.get("prerequisites", []) if isinstance(item, dict) and item.get("topic")]
    intermediates = [canonicalize_concept_name(item.get("topic")) for item in roadmap.get("intermediate_topics", []) if isinstance(item, dict) and item.get("topic")]
    advanceds = [canonicalize_concept_name(item.get("topic")) for item in roadmap.get("advanced_topics", []) if isinstance(item, dict) and item.get("topic")]

    # 4. Construct ordered DAG progression with cycle & duplicate prevention
    ordered_topics = []
    seen = set()

    def add_topic(name):
        c_name = canonicalize_concept_name(name)
        if c_name and is_valid_topic(c_name) and c_name.lower() not in seen and c_name.lower() != clean_goal.lower():
            seen.add(c_name.lower())
            ordered_topics.append(c_name)

    # Order from most foundational roots up to advanced prerequisites
    for topic in graph_chain:
        add_topic(topic)

    for topic in foundations:
        add_topic(topic)

    for topic in prereqs:
        add_topic(topic)

    for topic in beginners:
        add_topic(topic)

    for topic in intermediates:
        add_topic(topic)

    for topic in advanceds:
        add_topic(topic)

    # Append goal topic as the final target node
    seen.add(clean_goal.lower())
    ordered_topics.append(clean_goal)

    roadmap_items = []
    for index, topic in enumerate(ordered_topics):
        prerequisites = ordered_topics[:index][-2:] if index > 0 else []
        roadmap_items.append(
            {
                "topic": topic,
                "order": index + 1,
                "prerequisites": prerequisites,
                "why": goal_topic_reason(topic, clean_goal, index, len(ordered_topics)),
            }
        )

    logger.info(f"[VALIDATION] Generated {len(roadmap_items)}-stage educational roadmap for goal '{clean_goal}'.")

    return {
        "goal": clean_goal,
        "topics": roadmap_items,
    }


def goal_topic_reason(topic, goal_title, index, total):
    if index == 0:
        return f"{topic} provides the foundational core concept required for {goal_title}."
    elif index == total - 1:
        return f"{topic} is the target goal synthesizing all preceding prerequisite stages."
    return f"{topic} builds upon earlier prerequisites and moves you closer to mastering {goal_title}."
