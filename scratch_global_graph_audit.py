import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.neo4j_service import get_neo4j_driver
from utils.topic_validator import canonicalize_concept_name, is_valid_topic, get_topic_validation_details

def audit_global_knowledge_graph():
    print("=== STEP 2: GLOBAL KNOWLEDGE GRAPH AUDIT ===")

    try:
        driver = get_neo4j_driver()
        with driver.session() as session:
            # 1. Total nodes and labels
            node_count = session.run("MATCH (n:Concept) RETURN count(n) AS total_nodes").single()["total_nodes"]
            print(f"Total Concept Nodes in Neo4j: {node_count}")

            # 2. Distinct relationship types
            rel_types_res = session.run("MATCH ()-[r]->() RETURN DISTINCT type(r) AS rel_type")
            rel_types = [r["rel_type"] for r in rel_types_res]
            print(f"Distinct Relationship Types in Neo4j: {rel_types}")

            # 3. Total relationships count by type
            rel_counts = session.run("MATCH ()-[r]->() RETURN type(r) AS rel_type, count(r) AS count")
            for r in rel_counts:
                print(f"  Relationship Label '{r['rel_type']}': {r['count']} edges")

            # 4. Check for self-referential edges
            self_loops = session.run("MATCH (n:Concept)-[r]->(n) RETURN n.name AS node, type(r) AS rel").data()
            print(f"Self-Referential Edges (Self-loops): {len(self_loops)}")

            # 5. Check for isolated nodes (no incoming or outgoing relationships)
            isolated = session.run("MATCH (n:Concept) WHERE NOT (n)-[]-() RETURN n.name AS node").data()
            print(f"Isolated Nodes: {len(isolated)}")
            if isolated:
                print(f"  Isolated Node Names: {[i['node'] for i in isolated[:10]]}")

            # 6. Sample 10 random nodes and verify outgoing successor relationships
            sample_nodes = session.run("MATCH (n:Concept) RETURN n.name AS name LIMIT 15").data()
            print("\n--- SAMPLE NODE TRAVERSAL CHECK ---")
            for item in sample_nodes:
                name = item["name"]
                clean = canonicalize_concept_name(name)
                is_val, reason = get_topic_validation_details(clean)
                succs = session.run(
                    "MATCH (n:Concept {name: $name})-[r:NEXT_TOPIC|BUILDS_ON|EXTENDS|SPECIAL_CASE_OF|IMPLEMENTS|FOLLOWS]->(m:Concept) RETURN m.name AS succ, type(r) AS type",
                    name=name
                ).data()
                print(f"Node '{name}' -> Canonical: '{clean}' | Valid: {is_val} | Outgoing Successors: {[s['succ'] for s in succs]}")

    except Exception as exc:
        print(f"[NEO4J CONNECTION ERROR]: {exc}")

if __name__ == "__main__":
    audit_global_knowledge_graph()
