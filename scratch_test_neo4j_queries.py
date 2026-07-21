import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.neo4j_service import get_neo4j_driver, fetch_raw_suggestions_from_neo4j
from utils.topic_validator import canonicalize_concept_name, KNOWN_EDUCATIONAL_TOPICS, TECHNICAL_SIGNALS

def test_neo4j_graph_and_queries():
    print("=== STEP 2 & STEP 3: GRAPH & QUERY VALIDATION ===")

    physics_terms = ["ray optics", "wave optics", "optics", "physics", "light", "reflection", "refraction", "lens", "mirror"]
    for term in physics_terms:
        KNOWN_EDUCATIONAL_TOPICS.add(term)
        TECHNICAL_SIGNALS.add(term)

    topics_to_check = ["Linked List", "Binary Tree", "Hash Table", "Quick Sort", "Ray Optics"]

    try:
        driver = get_neo4j_driver()
        with driver.session() as session:
            print("\n--- 1. DIRECT NEO4J GRAPH QUERY INSPECTION ---")
            for topic in topics_to_check:
                clean_t = canonicalize_concept_name(topic)
                rec = session.run(
                    """
                    MATCH (t:Concept)
                    WHERE toLower(t.name) = toLower($topic)
                    OPTIONAL MATCH (in_node:Concept)-[r_in]->(t)
                    OPTIONAL MATCH (t)-[r_out]->(out_node:Concept)
                    RETURN t.name AS topic,
                           collect(DISTINCT {from: in_node.name, type: type(r_in)}) AS incoming,
                           collect(DISTINCT {to: out_node.name, type: type(r_out)}) AS outgoing
                    """,
                    topic=clean_t
                ).single()

                if rec:
                    print(f"\nNode: '{rec['topic']}'")
                    print(f"  Incoming: {rec['incoming']}")
                    print(f"  Outgoing: {rec['outgoing']}")
                else:
                    print(f"\nNode: '{clean_t}' -> NOT FOUND IN NEO4J GRAPH")

    except Exception as exc:
        print(f"\n[NEO4J CONNECTION WARNING]: {exc}")

    print("\n--- 2. RAW SUGGESTIONS RETRIEVAL INSPECTION ---")
    for topic in topics_to_check:
        clean_t = canonicalize_concept_name(topic)
        suggs = fetch_raw_suggestions_from_neo4j(clean_t)
        print(f"\nRaw suggestions for '{clean_t}': {suggs}")

if __name__ == "__main__":
    test_neo4j_graph_and_queries()
