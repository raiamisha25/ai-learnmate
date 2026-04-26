# import os
# import re

# import fitz
# import networkx as nx
# from flask import Flask, render_template, request
# from google import genai
# from neo4j import GraphDatabase
# from werkzeug.utils import secure_filename


# app = Flask(__name__)

# UPLOAD_FOLDER = "uploads"
# os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
# NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
# NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "whatif@12")

# knowledge_graph = {
#     "nodes": [],
#     "edges": [],
#     "triples": [],
# }

# latest_quiz = []
# neo4j_status = {
#     "connected": False,
#     "message": "Neo4j has not been checked yet.",
# }

# STOP_WORDS = {
#     "about",
#     "after",
#     "also",
#     "because",
#     "before",
#     "between",
#     "could",
#     "depend",
#     "depends",
#     "explain",
#     "explains",
#     "from",
#     "have",
#     "into",
#     "more",
#     "most",
#     "other",
#     "should",
#     "such",
#     "summary",
#     "their",
#     "there",
#     "these",
#     "this",
#     "that",
#     "they",
#     "through",
#     "used",
#     "using",
#     "when",
#     "where",
#     "which",
#     "while",
#     "with",
#     "would",
# }


# def get_neo4j_driver():
#     return GraphDatabase.driver(
#         NEO4J_URI,
#         auth=(NEO4J_USERNAME, NEO4J_PASSWORD),
#     )


# def check_neo4j_connection():
#     try:
#         with get_neo4j_driver() as driver:
#             driver.verify_connectivity()

#         neo4j_status["connected"] = True
#         neo4j_status["message"] = "Connected to Neo4j."
#     except Exception as exc:
#         neo4j_status["connected"] = False
#         neo4j_status["message"] = f"Neo4j connection failed: {exc}"

#     return neo4j_status


# def extract_text_from_pdf(filepath):
#     text = ""

#     with fitz.open(filepath) as doc:
#         for page in doc:
#             text += page.get_text()

#     return text.strip()


# def summarize_text(text):
#     api_key = os.getenv("GEMINI_API_KEY")

#     if not api_key:
#         return "GEMINI_API_KEY is missing. Please add your Gemini API key to your environment variables."

#     client = genai.Client(api_key=api_key)
#     prompt = f"""
# Summarize the following PDF text in simple terms.
# Use short paragraphs and bullet points where helpful.

# PDF text:
# {text[:8000]}
# """

#     response = client.models.generate_content(
#         model="gemini-2.5-flash",
#         contents=prompt,
#     )

#     return response.text or "Gemini did not return a summary. Please try again."


# def generate_quiz(summary):
#     api_key = os.getenv("GEMINI_API_KEY")

#     if not api_key:
#         return [
#             "Quiz generation needs GEMINI_API_KEY. Add your API key to generate questions."
#         ]

#     client = genai.Client(api_key=api_key)
#     prompt = f"""
# Create 5 beginner-friendly quiz questions from this summary.
# Use this format:
# Q1. Question?
# Answer: Short answer

# Summary:
# {summary[:5000]}
# """

#     response = client.models.generate_content(
#         model="gemini-2.5-flash",
#         contents=prompt,
#     )

#     quiz_text = response.text or "Gemini did not return quiz questions."
#     return [line.strip() for line in quiz_text.splitlines() if line.strip()]


# def extract_key_concepts(summary):
#     words = re.findall(r"\b[A-Za-z][A-Za-z-]{3,}\b", summary.lower())
#     concept_counts = {}

#     for word in words:
#         if word not in STOP_WORDS:
#             concept_counts[word] = concept_counts.get(word, 0) + 1

#     sorted_concepts = sorted(
#         concept_counts.items(),
#         key=lambda item: item[1],
#         reverse=True,
#     )

#     return [concept.title() for concept, count in sorted_concepts[:10]]


# def build_knowledge_graph(summary):
#     concepts = extract_key_concepts(summary)
#     graph = nx.DiGraph()
#     triples = []

#     graph.add_node("Summary", important=True)

#     for index, concept in enumerate(concepts):
#         is_important = index < 5
#         graph.add_node(concept, important=is_important)

#         relation = "explains" if index < 3 else "is related to"
#         graph.add_edge("Summary", concept, relation=relation)
#         triples.append(("Summary", relation, concept))

#     for index in range(len(concepts) - 1):
#         current_concept = concepts[index]
#         next_concept = concepts[index + 1]

#         graph.add_edge(current_concept, next_concept, relation="next topic")
#         graph.add_edge(next_concept, current_concept, relation="prerequisite")
#         triples.append((current_concept, "next topic", next_concept))
#         triples.append((next_concept, "prerequisite", current_concept))

#     nodes = [
#         {
#             "name": node,
#             "important": graph.nodes[node].get("important", False),
#         }
#         for node in graph.nodes
#     ]

#     edges = [
#         {
#             "subject": subject,
#             "relation": data["relation"],
#             "object": object_name,
#         }
#         for subject, object_name, data in graph.edges(data=True)
#     ]

#     return {
#         "nodes": nodes,
#         "edges": edges,
#         "triples": triples,
#     }


# def relation_to_type(relation):
#     relation_types = {
#         "explains": "EXPLAINS",
#         "is related to": "RELATED_TO",
#         "next topic": "NEXT_TOPIC",
#         "prerequisite": "PREREQUISITE",
#     }

#     return relation_types.get(relation, "RELATED_TO")


# def save_graph_to_neo4j(graph_data):
#     if not graph_data["nodes"]:
#         return

#     try:
#         with get_neo4j_driver() as driver:
#             with driver.session() as session:
#                 session.run(
#                     """
#                     MERGE (root:Document {name: "Latest PDF Summary"})
#                     SET root.updated_at = datetime()
#                     """
#                 )

#                 for node in graph_data["nodes"]:
#                     session.run(
#                         """
#                         MERGE (concept:Concept {name: $name})
#                         SET concept.important = $important
#                         """,
#                         name=node["name"],
#                         important=node["important"],
#                     )

#                 for edge in graph_data["edges"]:
#                     relation_type = relation_to_type(edge["relation"])
#                     cypher = f"""
#                     MATCH (subject:Concept {{name: $subject}})
#                     MATCH (object:Concept {{name: $object}})
#                     MERGE (subject)-[rel:{relation_type}]->(object)
#                     SET rel.label = $relation
#                     """
#                     session.run(
#                         cypher,
#                         subject=edge["subject"],
#                         object=edge["object"],
#                         relation=edge["relation"],
#                     )

#         neo4j_status["connected"] = True
#         neo4j_status["message"] = "Graph saved to Neo4j."
#     except Exception as exc:
#         neo4j_status["connected"] = False
#         neo4j_status["message"] = f"Could not save graph to Neo4j: {exc}"


# def fetch_graph_from_neo4j():
#     try:
#         with get_neo4j_driver() as driver:
#             with driver.session() as session:
#                 records = session.run(
#                     """
#                     MATCH (subject:Concept)-[rel]->(object:Concept)
#                     RETURN subject.name AS subject,
#                            rel.label AS relation,
#                            object.name AS object,
#                            subject.important AS subject_important,
#                            object.important AS object_important
#                     ORDER BY subject.name, object.name
#                     """
#                 )

#                 nodes_by_name = {}
#                 edges = []
#                 triples = []

#                 for record in records:
#                     subject = record["subject"]
#                     object_name = record["object"]
#                     relation = record["relation"] or "is related to"

#                     nodes_by_name[subject] = {
#                         "name": subject,
#                         "important": bool(record["subject_important"]),
#                     }
#                     nodes_by_name[object_name] = {
#                         "name": object_name,
#                         "important": bool(record["object_important"]),
#                     }
#                     edges.append(
#                         {
#                             "subject": subject,
#                             "relation": relation,
#                             "object": object_name,
#                         }
#                     )
#                     triples.append((subject, relation, object_name))

#         graph_data = {
#             "nodes": list(nodes_by_name.values()),
#             "edges": edges,
#             "triples": triples,
#         }

#         if graph_data["nodes"]:
#             knowledge_graph.update(graph_data)

#         neo4j_status["connected"] = True
#         neo4j_status["message"] = "Graph loaded from Neo4j."
#         return graph_data
#     except Exception as exc:
#         neo4j_status["connected"] = False
#         neo4j_status["message"] = f"Could not load graph from Neo4j: {exc}"
#         return knowledge_graph


# def fetch_topic_suggestions():
#     suggestions = {}

#     try:
#         with get_neo4j_driver() as driver:
#             with driver.session() as session:
#                 records = session.run(
#                     """
#                     MATCH (topic:Concept)
#                     OPTIONAL MATCH (topic)-[:PREREQUISITE]->(before:Concept)
#                     OPTIONAL MATCH (topic)-[:NEXT_TOPIC]->(after:Concept)
#                     RETURN topic.name AS topic,
#                            collect(DISTINCT before.name) AS before_topics,
#                            collect(DISTINCT after.name) AS after_topics
#                     ORDER BY topic.name
#                     """
#                 )

#                 for record in records:
#                     before_topics = [
#                         topic for topic in record["before_topics"] if topic
#                     ]
#                     after_topics = [
#                         topic for topic in record["after_topics"] if topic
#                     ]

#                     if before_topics or after_topics:
#                         suggestions[record["topic"]] = {
#                             "before": before_topics,
#                             "after": after_topics,
#                         }
#     except Exception:
#         for edge in knowledge_graph["edges"]:
#             suggestions.setdefault(edge["subject"], {"before": [], "after": []})
#             suggestions.setdefault(edge["object"], {"before": [], "after": []})

#             if edge["relation"] == "next topic":
#                 suggestions[edge["subject"]]["after"].append(edge["object"])
#             elif edge["relation"] == "prerequisite":
#                 suggestions[edge["subject"]]["before"].append(edge["object"])

#     return suggestions


# def build_local_topic_suggestions():
#     suggestions = {}

#     for edge in knowledge_graph["edges"]:
#         suggestions.setdefault(edge["subject"], {"before": [], "after": []})
#         suggestions.setdefault(edge["object"], {"before": [], "after": []})

#         if edge["relation"] == "next topic":
#             suggestions[edge["subject"]]["after"].append(edge["object"])
#         elif edge["relation"] == "prerequisite":
#             suggestions[edge["subject"]]["before"].append(edge["object"])

#     return suggestions


# @app.route("/")
# def home():
#     return render_template("home.html")


# @app.route("/upload", methods=["GET", "POST"])
# def upload():
#     summary = None
#     error = None

#     if request.method == "POST":
#         uploaded_file = request.files.get("file")

#         if not uploaded_file or not uploaded_file.filename:
#             error = "Please choose a PDF file first."
#         elif not uploaded_file.filename.lower().endswith(".pdf"):
#             error = "Please upload a PDF file."
#         else:
#             filename = secure_filename(uploaded_file.filename)
#             filepath = os.path.join(UPLOAD_FOLDER, filename)
#             uploaded_file.save(filepath)

#             try:
#                 text = extract_text_from_pdf(filepath)

#                 if not text:
#                     error = "No readable text was found in this PDF."
#                 else:
#                     summary = summarize_text(text)
#                     graph_data = build_knowledge_graph(summary)
#                     quiz = generate_quiz(summary)

#                     knowledge_graph.update(graph_data)
#                     latest_quiz.clear()
#                     latest_quiz.extend(quiz)
#                     save_graph_to_neo4j(graph_data)
#             except Exception as exc:
#                 error = f"Something went wrong: {exc}"

#     return render_template(
#         "upload.html",
#         summary=summary,
#         error=error,
#         quiz=latest_quiz,
#         neo4j_status=neo4j_status,
#     )


# @app.route("/graph")
# def graph():
#     status = check_neo4j_connection()

#     if status["connected"]:
#         graph_data = fetch_graph_from_neo4j()
#         suggestions = fetch_topic_suggestions()
#     else:
#         graph_data = knowledge_graph
#         suggestions = build_local_topic_suggestions()

#     return render_template(
#         "graph.html",
#         graph=graph_data,
#         suggestions=suggestions,
#         neo4j_status=neo4j_status,
#     )


# @app.route("/quiz")
# def quiz():
#     return render_template("quiz.html", quiz=latest_quiz)


# if __name__ == "__main__":
#     app.run(debug=True)




import os
import re
import fitz  # PyMuPDF
import networkx as nx
from flask import Flask, render_template, request
import google.generativeai as genai
from neo4j import GraphDatabase
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- API CONFIGURATION ---
# Replace "YOUR_API_KEY_HERE" with your actual Gemini API Key if not using .env
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or "YOUR_API_KEY_HERE"
genai.configure(api_key=GEMINI_API_KEY)

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "whatif@12")

knowledge_graph = {"nodes": [], "edges": [], "triples": []}
latest_quiz = []
neo4j_status = {"connected": False, "message": "Neo4j has not been checked yet."}

STOP_WORDS = {
    "about", "after", "also", "because", "before", "between", "could", 
    "depend", "depends", "explain", "explains", "from", "have", "into", 
    "more", "most", "other", "should", "such", "summary", "their", 
    "there", "these", "this", "that", "they", "through", "used", 
    "using", "when", "where", "which", "while", "with", "would",
}

# --- SMART MODEL PICKER ---
# This fixes the 404 error by finding the exact model name allowed by your key
def get_best_model():
    try:
        available_models = [m.name for m in genai.list_models() 
                            if 'generateContent' in m.supported_generation_methods]
        
        # Priority List for 2026
        priorities = ["models/gemini-3-flash", "models/gemini-2.5-flash", "models/gemini-1.5-flash-latest"]
        
        for p in priorities:
            if p in available_models:
                return p
        
        return available_models[0] if available_models else "models/gemini-1.5-flash"
    except:
        return "models/gemini-1.5-flash"

def get_neo4j_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

def check_neo4j_connection():
    try:
        with get_neo4j_driver() as driver:
            driver.verify_connectivity()
        neo4j_status.update({"connected": True, "message": "Connected to Neo4j."})
    except Exception as exc:
        neo4j_status.update({"connected": False, "message": f"Neo4j connection failed: {exc}"})
    return neo4j_status

def extract_text_from_pdf(filepath):
    text = ""
    with fitz.open(filepath) as doc:
        for page in doc:
            text += page.get_text()
    return text.strip()

def summarize_text(text):
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_API_KEY_HERE":
        return "API Key is missing."

    try:
        model_name = get_best_model()
        model = genai.GenerativeModel(model_name)
        prompt = f"Summarize the following PDF text in simple terms with bullet points:\n\n{text[:8000]}"
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error during summarization: {str(e)}"

def generate_quiz(summary):
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_API_KEY_HERE":
        return ["API Key is missing."]

    try:
        model_name = get_best_model()
        model = genai.GenerativeModel(model_name)
        prompt = f"Create 5 quiz questions from this summary. Format: Q1. Question? Answer: Short answer\n\nSummary:\n{summary[:5000]}"
        response = model.generate_content(prompt)
        return [line.strip() for line in response.text.splitlines() if line.strip()]
    except Exception as e:
        return [f"Error generating quiz: {str(e)}"]

# --- GRAPH LOGIC ---
def extract_key_concepts(summary):
    words = re.findall(r"\b[A-Za-z][A-Za-z-]{3,}\b", summary.lower())
    counts = {w: words.count(w) for w in set(words) if w not in STOP_WORDS}
    sorted_concepts = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    return [c[0].title() for c in sorted_concepts[:10]]

def build_knowledge_graph(summary):
    concepts = extract_key_concepts(summary)
    nodes = [{"name": "Summary", "important": True}]
    edges = []
    
    for i, concept in enumerate(concepts):
        nodes.append({"name": concept, "important": i < 5})
        edges.append({"subject": "Summary", "relation": "explains" if i < 3 else "related to", "object": concept})
        if i < len(concepts) - 1:
            edges.append({"subject": concept, "relation": "next topic", "object": concepts[i+1]})
            
    return {"nodes": nodes, "edges": edges}

def save_graph_to_neo4j(graph_data):
    try:
        with get_neo4j_driver() as driver:
            with driver.session() as session:
                for node in graph_data["nodes"]:
                    session.run("MERGE (c:Concept {name: $n}) SET c.important = $i", n=node["name"], i=node["important"])
                for edge in graph_data["edges"]:
                    rel = edge["relation"].upper().replace(" ", "_")
                    session.run(f"MATCH (s:Concept {{name: $s}}), (o:Concept {{name: $o}}) MERGE (s)-[:{rel}]->(o)", 
                                s=edge["subject"], o=edge["object"])
        neo4j_status["message"] = "Graph saved to Neo4j."
    except Exception as e:
        neo4j_status["message"] = f"Neo4j Error: {e}"

# --- ROUTES ---
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/upload", methods=["GET", "POST"])
def upload():
    summary, error = None, None
    if request.method == "POST":
        file = request.files.get("file")
        if file and file.filename.lower().endswith(".pdf"):
            path = os.path.join(UPLOAD_FOLDER, secure_filename(file.filename))
            file.save(path)
            try:
                text = extract_text_from_pdf(path)
                summary = summarize_text(text)
                graph_data = build_knowledge_graph(summary)
                knowledge_graph.update(graph_data)
                latest_quiz.clear()
                latest_quiz.extend(generate_quiz(summary))
                save_graph_to_neo4j(graph_data)
            except Exception as e:
                error = str(e)
    return render_template("upload.html", summary=summary, error=error, quiz=latest_quiz, neo4j_status=neo4j_status)

@app.route("/graph")
def graph():
    check_neo4j_connection()
    return render_template("graph.html", graph=knowledge_graph, neo4j_status=neo4j_status)

@app.route("/quiz")
def quiz():
    return render_template("quiz.html", quiz=latest_quiz)

if __name__ == "__main__":
    app.run(debug=True)

