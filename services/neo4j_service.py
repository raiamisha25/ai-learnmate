import os

from dotenv import load_dotenv
from neo4j import GraphDatabase

from models.state import knowledge_graph, neo4j_status


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
    except Exception:
        neo4j_status.update(
            {
                "connected": False,
                "message": "Learning path storage is offline, so local suggestions will be used.",
            }
        )

    return neo4j_status


def clean_topic_list(topics):
    return sorted({topic for topic in topics if topic})


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
    except Exception:
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
    except Exception:
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
    except Exception:
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
    except Exception:
        return [], []


def save_topic_suggestions(topic, before, after):
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
                        topic=topic,
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
                        topic=topic,
                        after_topic=after_topic,
                    )
    except Exception:
        pass
