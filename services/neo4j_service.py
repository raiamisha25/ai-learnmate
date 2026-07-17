import os

from dotenv import load_dotenv
from neo4j import GraphDatabase

from models.state import knowledge_graph, neo4j_status
from utils.topic_validator import is_valid_topic, normalize_topic_name, validate_concepts


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
    except Exception as exc:
        print(f"Neo4j connection failed: {exc}")
        neo4j_status.update(
            {
                "connected": False,
                "message": "Learning path storage is offline, so local suggestions will be used.",
            }
        )

    return neo4j_status


def clean_topic_list(topics):
    return sorted({normalize_topic_name(topic) for topic in topics if topic and is_valid_topic(topic)})


def relation_to_type(relation):
    relation_types = {
        "explains": "EXPLAINS",
        "EXPLAINS": "EXPLAINS",
        "is related to": "RELATED_TO",
        "RELATED_TO": "RELATED_TO",
        "next topic": "NEXT_TOPIC",
        "NEXT_TOPIC": "NEXT_TOPIC",
        "prerequisite": "PREREQUISITE",
        "PREREQUISITE": "PREREQUISITE",
    }

    return relation_types.get(relation, "RELATED_TO")


def save_graph_to_neo4j(graph_data):
    valid_names = set(validate_concepts([node.get("name") for node in graph_data.get("nodes", [])], limit=25))

    graph_data = {
        "nodes": [
            {"name": node["name"], "important": node.get("important", False)}
            for node in graph_data.get("nodes", [])
            if node.get("name") in valid_names
        ],
        "edges": [
            edge for edge in graph_data.get("edges", [])
            if edge.get("subject") in valid_names and edge.get("object") in valid_names
        ],
        "triples": [
            triple for triple in graph_data.get("triples", [])
            if len(triple) == 3 and triple[0] in valid_names and triple[2] in valid_names
        ],
    }

    if not graph_data["nodes"]:
        return

    concept_names = [node["name"] for node in graph_data["nodes"]]

    try:
        with get_neo4j_driver() as driver:
            with driver.session() as session:
                session.run(
                    """
                    MATCH (start:Concept)-[rel:PREREQUISITE|NEXT_TOPIC|EXPLAINS|RELATED_TO]->(end:Concept)
                    WHERE start.name IN $concept_names OR end.name IN $concept_names
                    DELETE rel
                    """,
                    concept_names=concept_names,
                )
                session.run(
                    """
                    MATCH (concept:Concept)
                    WHERE concept.name IN ["Linked", "List"]
                    DETACH DELETE concept
                    """
                )

                for node in graph_data["nodes"]:
                    session.run(
                        """
                        MERGE (concept:Concept {name: $name})
                        SET concept.important = $important
                        """,
                        name=node["name"],
                        important=node["important"],
                    )

                for edge in graph_data["edges"]:
                    relation_type = relation_to_type(edge["relation"])
                    cypher = f"""
                    MATCH (subject:Concept {{name: $subject}})
                    MATCH (object:Concept {{name: $object}})
                    MERGE (subject)-[rel:{relation_type}]->(object)
                    SET rel.label = $relation_type
                    """
                    session.run(
                        cypher,
                        subject=edge["subject"],
                        object=edge["object"],
                        relation_type=relation_type,
                    )

        neo4j_status.update({"connected": True, "message": "Learning path saved."})
    except Exception as exc:
        print(f"Could not save graph to Neo4j: {exc}")
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
                    subject = record["subject"]
                    object_name = record["object"]
                    relation = record["relation"] or "RELATED_TO"

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
        print(f"Could not load graph from Neo4j: {exc}")
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
                    before_topics = clean_topic_list(record["before_topics"])
                    after_topics = clean_topic_list(record["after_topics"])

                    if before_topics or after_topics:
                        suggestions[record["topic"]] = {
                            "before": before_topics,
                            "after": after_topics,
                        }

        return suggestions or build_local_topic_suggestions()
    except Exception as exc:
        print(f"Could not fetch topic suggestions from Neo4j: {exc}")
        return build_local_topic_suggestions()


def fetch_suggestions_for_topic(topic):
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
                    topic=topic,
                )
                record = result.single()

        if not record:
            return [], []

        before = clean_topic_list(record["before_topics"])
        after = clean_topic_list(record["after_topics"])
        return before, after
    except Exception as exc:
        print(f"Could not fetch suggestions for topic '{topic}' from Neo4j: {exc}")
        return [], []


def save_topic_suggestions(topic, before, after):
    clean_topic = normalize_topic_name(topic)
    if not is_valid_topic(clean_topic):
        return

    before = validate_concepts(before, limit=5)
    after = validate_concepts(after, limit=5)

    try:
        with get_neo4j_driver() as driver:
            with driver.session() as session:
                for before_topic in before:
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

                for after_topic in after:
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
    except Exception as exc:
        print(f"Could not save topic suggestions to Neo4j for '{topic}': {exc}")


def fetch_roadmap_from_neo4j(topic):
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
                    topic=topic,
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
                    topic=topic,
                ).single()

        def clean_items(items):
            return [
                {"topic": item["topic"], "why": item.get("why") or ""}
                for item in items or []
                if item.get("topic")
            ]

        return {
            "topic": topic_record["topic"],
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
        print(f"Could not fetch roadmap for '{topic}' from Neo4j: {exc}")
        return None


def save_roadmap_to_neo4j(roadmap):
    topic = normalize_topic_name(roadmap.get("topic"))
    if not is_valid_topic(topic):
        return

    for key in ("prerequisites", "next_topics", "related_topics"):
        valid_topics = set(validate_concepts([item.get("topic") for item in roadmap.get(key, [])], limit=5))
        roadmap[key] = [
            {**item, "topic": normalize_topic_name(item.get("topic"))}
            for item in roadmap.get(key, [])
            if normalize_topic_name(item.get("topic")) in valid_topics
        ]
    roadmap["topic"] = topic

    try:
        with get_neo4j_driver() as driver:
            with driver.session() as session:
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

                for item in roadmap.get("prerequisites", []):
                    session.run(
                        """
                        MERGE (pre:Concept {name: $pre})
                        MERGE (topic:Concept {name: $topic})
                        MERGE (pre)-[rel:PREREQUISITE_OF]->(topic)
                        SET rel.why = $why
                        """,
                        pre=item["topic"],
                        topic=roadmap["topic"],
                        why=item.get("why"),
                    )

                for item in roadmap.get("next_topics", []):
                    session.run(
                        """
                        MERGE (topic:Concept {name: $topic})
                        MERGE (next:Concept {name: $next})
                        MERGE (topic)-[rel:NEXT_TOPIC]->(next)
                        SET rel.why = $why
                        """,
                        topic=roadmap["topic"],
                        next=item["topic"],
                        why=item.get("why"),
                    )

                for item in roadmap.get("related_topics", []):
                    session.run(
                        """
                        MERGE (topic:Concept {name: $topic})
                        MERGE (related:Concept {name: $related})
                        MERGE (topic)-[rel:RELATED_TOPIC]->(related)
                        SET rel.why = $why
                        """,
                        topic=roadmap["topic"],
                        related=item["topic"],
                        why=item.get("why"),
                    )
    except Exception as exc:
        print(f"Could not save roadmap to Neo4j for '{roadmap.get('topic')}': {exc}")
