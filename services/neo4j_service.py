import os
import re

from dotenv import load_dotenv
from neo4j import GraphDatabase

from models.state import knowledge_graph, neo4j_status
from utils.topic_validator import (
    audit_tracker,
    canonicalize_concept_name,
    is_valid_relationship,
    is_valid_topic,
    logger,
    normalize_topic_name,
    validate_concepts,
)


load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "whatif@12")


def get_neo4j_driver():
    return GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USERNAME, NEO4J_PASSWORD),
        connection_timeout=5,
        max_transaction_retry_time=1,
    )


def check_neo4j_connection():
    try:
        with get_neo4j_driver() as driver:
            driver.verify_connectivity()

        neo4j_status.update({"connected": True, "message": "Connected to Neo4j."})
        logger.info("[NEO4J INSERTION] Connection verified successfully.")
    except Exception as exc:
        logger.error(f"[NEO4J INSERTION] Connection failed: {exc}")
        neo4j_status.update(
            {
                "connected": False,
                "message": "Learning path storage is offline, so local suggestions will be used.",
            }
        )

    return neo4j_status


def clean_topic_list(topics):
    return sorted({canonicalize_concept_name(topic) for topic in topics if topic and is_valid_topic(topic)})


def clean_concept_name_for_storage(name):
    return canonicalize_concept_name(name)


def relation_to_type(relation):
    allowed_types = {
        "PREREQUISITE",
        "PREREQUISITE_OF",
        "NEXT_TOPIC",
        "PART_OF",
        "USES",
        "APPLICATION_OF",
        "COMPARES_WITH",
        "RELATED_TO",
        "RELATED_TOPIC",
    }

    relation_type = str(relation or "").strip().upper()
    return relation_type if relation_type in allowed_types else "RELATED_TO"


def save_graph_to_neo4j(graph_data):
    node_properties = {}

    for node in graph_data.get("nodes", []):
        clean_name = canonicalize_concept_name(node.get("name"))
        if is_valid_topic(clean_name):
            node_properties[clean_name] = {
                "name": clean_name,
                "important": bool(node.get("important", False)),
            }

    edges = []
    seen_edges = set()

    for edge in graph_data.get("edges", []):
        subject = canonicalize_concept_name(edge.get("subject"))
        object_name = canonicalize_concept_name(edge.get("object"))
        relation_type = relation_to_type(edge.get("relation"))
        why = edge.get("why") or f"{subject} relates to {object_name}."

        is_rel_ok, rel_reason = is_valid_relationship(subject, object_name, relation_type, why, seen_edges)
        if not is_rel_ok:
            logger.info(f"[REJECTED CONCEPT] Graph edge '{subject}' -> '{object_name}' rejected: {rel_reason}")
            continue

        edge_key = (subject.lower(), relation_type, object_name.lower())
        seen_edges.add(edge_key)
        audit_tracker.seen_relationships.add(edge_key)

        edges.append(
            {"subject": subject, "relation": relation_type, "object": object_name, "why": why}
        )
        node_properties.setdefault(
            subject,
            {"name": subject, "important": False},
        )
        node_properties.setdefault(
            object_name,
            {"name": object_name, "important": False},
        )

    connected_names = {edge["subject"] for edge in edges} | {edge["object"] for edge in edges}
    nodes = [
        node
        for name, node in node_properties.items()
        if name in connected_names
    ]

    if not edges or not nodes:
        logger.info("[NEO4J INSERTION] Skip saving graph: no valid edges or nodes.")
        return

    concept_names = [node["name"] for node in nodes]

    try:
        with get_neo4j_driver() as driver:
            with driver.session() as session:
                # Cleanup existing relationships for affected concept nodes
                try:
                    session.run(
                        """
                        MATCH (start:Concept)-[rel:PREREQUISITE|PREREQUISITE_OF|NEXT_TOPIC|PART_OF|USES|APPLICATION_OF|COMPARES_WITH|RELATED_TO|RELATED_TOPIC]->(end:Concept)
                        WHERE start.name IN $concept_names OR end.name IN $concept_names
                        DELETE rel
                        """,
                        concept_names=concept_names,
                    )
                except Exception as exc:
                    logger.error(f"[NEO4J INSERTION] Failed to clean old relationships: {exc}")

                # Insert nodes with fault tolerance per node
                for node in nodes:
                    try:
                        session.run(
                            """
                            MERGE (concept:Concept {name: $name})
                            SET concept.important = $important
                            """,
                            name=node["name"],
                            important=node["important"],
                        )
                        audit_tracker.neo4j_nodes += 1
                        logger.info(f"[NEO4J INSERTION] Merged concept node: '{node['name']}'")
                    except Exception as exc:
                        logger.error(f"[NEO4J INSERTION] Failed to merge concept node '{node['name']}': {exc}")

                # Insert edges with fault tolerance per edge
                for edge in edges:
                    try:
                        relation_type = edge["relation"]
                        cypher = f"""
                        MATCH (subject:Concept {{name: $subject}})
                        MATCH (object:Concept {{name: $object}})
                        MERGE (subject)-[rel:{relation_type}]->(object)
                        SET rel.label = $relation_type, rel.why = $why
                        """
                        session.run(
                            cypher,
                            subject=edge["subject"],
                            object=edge["object"],
                            relation_type=relation_type,
                            why=edge["why"],
                        )
                        audit_tracker.neo4j_relationships += 1
                        logger.info(f"[NEO4J INSERTION] Merged relationship: '{edge['subject']}' -[{relation_type}]-> '{edge['object']}'")
                    except Exception as exc:
                        logger.error(f"[NEO4J INSERTION] Failed to merge relationship '{edge['subject']}' -> '{edge['object']}': {exc}")

                # Clean up orphans
                try:
                    session.run(
                        """
                        MATCH (concept:Concept)
                        WHERE NOT (concept)--()
                        DELETE concept
                        """
                    )
                except Exception as exc:
                    logger.error(f"[NEO4J INSERTION] Failed orphan cleanup: {exc}")

        neo4j_status.update({"connected": True, "message": "Learning path saved."})
    except Exception as exc:
        logger.error(f"[NEO4J INSERTION] Could not save graph to Neo4j: {exc}")
        neo4j_status.update(
            {
                "connected": False,
                "message": "Learning path storage is offline, so local suggestions will be used.",
            }
        )


def fetch_graph_from_neo4j():
    try:
        with get_neo4j_driver() as driver:
            with driver.session() as session:
                records = session.run(
                    """
                    MATCH (subject:Concept)-[rel]->(object:Concept)
                    RETURN subject.name AS subject,
                           coalesce(rel.label, type(rel)) AS relation,
                           object.name AS object,
                           subject.important AS subject_important,
                           object.important AS object_important
                    ORDER BY subject.name, object.name
                    """
                )

                nodes_by_name = {}
                edges = []
                triples = []

                for record in records:
                    subject = canonicalize_concept_name(record["subject"])
                    object_name = canonicalize_concept_name(record["object"])
                    relation = record["relation"] or "RELATED_TO"

                    if not is_valid_topic(subject) or not is_valid_topic(object_name):
                        continue

                    nodes_by_name[subject] = {
                        "name": subject,
                        "important": bool(record["subject_important"]),
                    }
                    nodes_by_name[object_name] = {
                        "name": object_name,
                        "important": bool(record["object_important"]),
                    }
                    edges.append(
                        {"subject": subject, "relation": relation, "object": object_name}
                    )
                    triples.append((subject, relation, object_name))

        graph_data = {
            "nodes": list(nodes_by_name.values()),
            "edges": edges,
            "triples": triples,
        }

        if graph_data["nodes"]:
            knowledge_graph.update(graph_data)

        neo4j_status.update({"connected": True, "message": "Learning path loaded."})
        return graph_data
    except Exception as exc:
        logger.error(f"[NEO4J INSERTION] Could not load graph from Neo4j: {exc}")
        neo4j_status.update(
            {
                "connected": False,
                "message": "Learning path storage is offline, so local suggestions will be used.",
            }
        )
        return knowledge_graph


def build_local_topic_suggestions():
    suggestions = {}

    for edge in knowledge_graph["edges"]:
        suggestions.setdefault(edge["subject"], {"before": [], "after": []})
        suggestions.setdefault(edge["object"], {"before": [], "after": []})

        if edge["relation"] in ("NEXT_TOPIC", "next topic"):
            suggestions[edge["subject"]]["after"].append(edge["object"])
            suggestions[edge["object"]]["before"].append(edge["subject"])

    return {
        topic: {
            "before": clean_topic_list(items["before"]),
            "after": clean_topic_list(items["after"]),
        }
        for topic, items in suggestions.items()
        if items["before"] or items["after"]
    }


def fetch_topic_suggestions():
    try:
        with get_neo4j_driver() as driver:
            with driver.session() as session:
                records = session.run(
                    """
                    MATCH (topic:Concept)
                    OPTIONAL MATCH (before:Concept)-[:NEXT_TOPIC]->(topic)
                    OPTIONAL MATCH (topic)-[:NEXT_TOPIC]->(after:Concept)
                    RETURN topic.name AS topic,
                           collect(DISTINCT before.name) AS before_topics,
                           collect(DISTINCT after.name) AS after_topics
                    ORDER BY topic.name
                    """
                )

                suggestions = {}

                for record in records:
                    t_name = canonicalize_concept_name(record["topic"])
                    if not is_valid_topic(t_name):
                        continue

                    before_topics = clean_topic_list(record["before_topics"])
                    after_topics = clean_topic_list(record["after_topics"])

                    if before_topics or after_topics:
                        suggestions[t_name] = {
                            "before": before_topics,
                            "after": after_topics,
                        }

        return suggestions or build_local_topic_suggestions()
    except Exception as exc:
        logger.error(f"[NEO4J INSERTION] Could not fetch topic suggestions: {exc}")
        return build_local_topic_suggestions()


def fetch_suggestions_for_topic(topic):
    clean_t = canonicalize_concept_name(topic)
    try:
        with get_neo4j_driver() as driver:
            with driver.session() as session:
                result = session.run(
                    """
                    MATCH (t:Concept)
                    WHERE toLower(t.name) = toLower($topic)

                    OPTIONAL MATCH (before:Concept)-[:NEXT_TOPIC]->(t)
                    OPTIONAL MATCH (t)-[:NEXT_TOPIC]->(after:Concept)

                    RETURN
                        collect(DISTINCT before.name) AS before_topics,
                        collect(DISTINCT after.name) AS after_topics
                    """,
                    topic=clean_t,
                )
                record = result.single()

        if not record:
            return [], []

        before = clean_topic_list(record["before_topics"])
        after = clean_topic_list(record["after_topics"])
        return before, after
    except Exception as exc:
        logger.error(f"[NEO4J INSERTION] Could not fetch suggestions for '{topic}': {exc}")
        return [], []


def save_topic_suggestions(topic, before, after):
    clean_topic = canonicalize_concept_name(topic)
    if not is_valid_topic(clean_topic):
        return

    before = validate_concepts([canonicalize_concept_name(item) for item in before], limit=5)
    after = validate_concepts([canonicalize_concept_name(item) for item in after], limit=5)

    try:
        with get_neo4j_driver() as driver:
            with driver.session() as session:
                for before_topic in before:
                    try:
                        session.run(
                            """
                            MERGE (before:Concept {name: $before_topic})
                            MERGE (topic:Concept {name: $topic})
                            MERGE (before)-[:NEXT_TOPIC]->(topic)
                            MERGE (topic)-[:PREREQUISITE]->(before)
                            MERGE (before)-[:RELATED_TO]->(topic)
                            """,
                            before_topic=before_topic,
                            topic=clean_topic,
                        )
                        audit_tracker.neo4j_nodes += 2
                        audit_tracker.neo4j_relationships += 3
                    except Exception as exc:
                        logger.error(f"[NEO4J INSERTION] Failed saving suggestion '{before_topic}' -> '{clean_topic}': {exc}")

                for after_topic in after:
                    try:
                        session.run(
                            """
                            MERGE (topic:Concept {name: $topic})
                            MERGE (after:Concept {name: $after_topic})
                            MERGE (topic)-[:NEXT_TOPIC]->(after)
                            MERGE (after)-[:PREREQUISITE]->(topic)
                            MERGE (topic)-[:RELATED_TO]->(after)
                            """,
                            topic=clean_topic,
                            after_topic=after_topic,
                        )
                        audit_tracker.neo4j_nodes += 2
                        audit_tracker.neo4j_relationships += 3
                    except Exception as exc:
                        logger.error(f"[NEO4J INSERTION] Failed saving suggestion '{clean_topic}' -> '{after_topic}': {exc}")
    except Exception as exc:
        logger.error(f"[NEO4J INSERTION] Could not save topic suggestions for '{topic}': {exc}")


def fetch_roadmap_from_neo4j(topic):
    clean_t = canonicalize_concept_name(topic)
    try:
        with get_neo4j_driver() as driver:
            with driver.session() as session:
                topic_record = session.run(
                    """
                    MATCH (topic:Concept)
                    WHERE toLower(topic.name) = toLower($topic)
                    RETURN topic.name AS topic,
                           topic.explanation AS explanation,
                           topic.analogy AS analogy,
                           coalesce(topic.definition, "") AS definition,
                           coalesce(topic.why_it_matters, "") AS why_it_matters,
                           coalesce(topic.example, "") AS example,
                           topic.difficulty AS difficulty,
                           topic.estimated_time AS estimated_time
                    LIMIT 1
                    """,
                    topic=clean_t,
                ).single()

                if not topic_record or not topic_record["explanation"]:
                    return None

                relation_records = session.run(
                    """
                    MATCH (topic:Concept)
                    WHERE toLower(topic.name) = toLower($topic)
                    OPTIONAL MATCH (pre:Concept)-[pre_rel:PREREQUISITE_OF]->(topic)
                    OPTIONAL MATCH (topic)-[next_rel:NEXT_TOPIC]->(next:Concept)
                    OPTIONAL MATCH (topic)-[related_rel:RELATED_TOPIC]->(related:Concept)
                    RETURN
                        collect(DISTINCT {topic: pre.name, why: pre_rel.why}) AS prerequisites,
                        collect(DISTINCT {topic: next.name, why: next_rel.why}) AS next_topics,
                        collect(DISTINCT {topic: related.name, why: related_rel.why}) AS related_topics
                    """,
                    topic=clean_t,
                ).single()

        def clean_items(items):
            return [
                {"topic": canonicalize_concept_name(item["topic"]), "why": item.get("why") or ""}
                for item in items or []
                if item.get("topic") and is_valid_topic(canonicalize_concept_name(item["topic"]))
            ]

        return {
            "topic": canonicalize_concept_name(topic_record["topic"]),
            "explanation": topic_record["explanation"],
            "analogy": topic_record["analogy"],
            "definition": topic_record["definition"],
            "why_it_matters": topic_record["why_it_matters"],
            "example": topic_record["example"],
            "difficulty": topic_record["difficulty"],
            "estimated_time": topic_record["estimated_time"],
            "prerequisites": clean_items(relation_records["prerequisites"]),
            "next_topics": clean_items(relation_records["next_topics"]),
            "related_topics": clean_items(relation_records["related_topics"]),
        }
    except Exception as exc:
        logger.error(f"[NEO4J INSERTION] Could not fetch roadmap for '{topic}': {exc}")
        return None


def save_roadmap_to_neo4j(roadmap):
    topic = canonicalize_concept_name(roadmap.get("topic"))
    if not is_valid_topic(topic):
        logger.info(f"[NEO4J INSERTION] Skip saving roadmap: main topic '{topic}' is not valid.")
        return

    for key in ("prerequisites", "next_topics", "related_topics"):
        valid_topics = set(
            validate_concepts(
                [canonicalize_concept_name(item.get("topic")) for item in roadmap.get(key, [])],
                limit=5,
            )
        )
        roadmap[key] = [
            {**item, "topic": canonicalize_concept_name(item.get("topic"))}
            for item in roadmap.get(key, [])
            if canonicalize_concept_name(item.get("topic")) in valid_topics
        ]
    roadmap["topic"] = topic

    if not any(roadmap.get(key) for key in ("prerequisites", "next_topics", "related_topics")):
        logger.info(f"[NEO4J INSERTION] Skip saving roadmap for '{topic}': no valid related topics.")
        return

    try:
        driver = get_neo4j_driver()
    except Exception as exc:
        logger.error(f"[NEO4J INSERTION] Failed to initialize Neo4j driver: {exc}")
        return

    try:
        with driver as drv:
            with drv.session() as session:
                # 1. Merge main concept node
                try:
                    session.run(
                        """
                        MERGE (topic:Concept {name: $topic})
                        SET topic.explanation = $explanation,
                            topic.analogy = $analogy,
                            topic.definition = $definition,
                            topic.why_it_matters = $why_it_matters,
                            topic.example = $example,
                            topic.difficulty = $difficulty,
                            topic.estimated_time = $estimated_time,
                            topic.roadmap_cached = true
                        """,
                        topic=roadmap["topic"],
                        explanation=roadmap.get("explanation"),
                        analogy=roadmap.get("analogy"),
                        definition=roadmap.get("definition"),
                        why_it_matters=roadmap.get("why_it_matters"),
                        example=roadmap.get("example"),
                        difficulty=roadmap.get("difficulty"),
                        estimated_time=roadmap.get("estimated_time"),
                    )
                    audit_tracker.neo4j_nodes += 1
                    logger.info(f"[NEO4J INSERTION] Merged concept node: '{roadmap['topic']}'")
                except Exception as exc:
                    logger.error(f"[NEO4J INSERTION] Failed to merge concept node '{roadmap['topic']}': {exc}")

                # 2. Merge prerequisite relationships
                for item in roadmap.get("prerequisites", []):
                    try:
                        pre_name = item["topic"]
                        why_desc = item.get("why") or f"{pre_name} is a prerequisite of {roadmap['topic']}."
                        session.run(
                            """
                            MERGE (pre:Concept {name: $pre})
                            MERGE (topic:Concept {name: $topic})
                            MERGE (pre)-[rel:PREREQUISITE_OF]->(topic)
                            SET rel.why = $why
                            """,
                            pre=pre_name,
                            topic=roadmap["topic"],
                            why=why_desc,
                        )
                        audit_tracker.neo4j_nodes += 1
                        audit_tracker.neo4j_relationships += 1
                        logger.info(f"[NEO4J INSERTION] Merged prerequisite: '{pre_name}' -[PREREQUISITE_OF]-> '{roadmap['topic']}'")
                    except Exception as exc:
                        logger.error(f"[NEO4J INSERTION] Failed to merge prerequisite '{item.get('topic')}' -> '{roadmap['topic']}': {exc}")

                # 3. Merge next topic relationships
                for item in roadmap.get("next_topics", []):
                    try:
                        next_name = item["topic"]
                        why_desc = item.get("why") or f"{next_name} comes after {roadmap['topic']}."
                        session.run(
                            """
                            MERGE (topic:Concept {name: $topic})
                            MERGE (next:Concept {name: $next})
                            MERGE (topic)-[rel:NEXT_TOPIC]->(next)
                            SET rel.why = $why
                            """,
                            topic=roadmap["topic"],
                            next=next_name,
                            why=why_desc,
                        )
                        audit_tracker.neo4j_nodes += 1
                        audit_tracker.neo4j_relationships += 1
                        logger.info(f"[NEO4J INSERTION] Merged next topic: '{roadmap['topic']}' -[NEXT_TOPIC]-> '{next_name}'")
                    except Exception as exc:
                        logger.error(f"[NEO4J INSERTION] Failed to merge next topic '{roadmap['topic']}' -> '{item.get('topic')}': {exc}")

                # 4. Merge related topic relationships
                for item in roadmap.get("related_topics", []):
                    try:
                        rel_name = item["topic"]
                        why_desc = item.get("why") or f"{rel_name} connects with {roadmap['topic']}."
                        session.run(
                            """
                            MERGE (topic:Concept {name: $topic})
                            MERGE (related:Concept {name: $related})
                            MERGE (topic)-[rel:RELATED_TOPIC]->(related)
                            SET rel.why = $why
                            """,
                            topic=roadmap["topic"],
                            related=rel_name,
                            why=why_desc,
                        )
                        audit_tracker.neo4j_nodes += 1
                        audit_tracker.neo4j_relationships += 1
                        logger.info(f"[NEO4J INSERTION] Merged related topic: '{roadmap['topic']}' -[RELATED_TOPIC]-> '{rel_name}'")
                    except Exception as exc:
                        logger.error(f"[NEO4J INSERTION] Failed to merge related topic '{roadmap['topic']}' -> '{item.get('topic')}': {exc}")
    except Exception as exc:
        logger.error(f"[NEO4J INSERTION] Session execution failed: {exc}")
