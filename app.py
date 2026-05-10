import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError

import fitz
import networkx as nx
from dotenv import load_dotenv
from flask import Flask, render_template, request
from google import genai
from neo4j import GraphDatabase
from werkzeug.utils import secure_filename


load_dotenv()

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY missing")
else:
    print("AI LearnMate startup: GEMINI_API_KEY loaded")

try:
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
except Exception:
    client = None

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "whatif@12")

knowledge_graph = {"nodes": [], "edges": [], "triples": []}
latest_quiz = []
latest_result = {}
neo4j_status = {"connected": False, "message": "Neo4j has not been checked yet."}

STOP_WORDS = {
    "about", "after", "also", "because", "before", "between", "could",
    "depend", "depends", "explain", "explains", "from", "have", "into",
    "more", "most", "other", "should", "such", "summary", "their",
    "there", "these", "this", "that", "they", "through", "used",
    "using", "when", "where", "which", "while", "with", "would",
    "and", "are", "can", "for", "has", "the", "was", "will",
}


def get_neo4j_driver():
    return GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USERNAME, NEO4J_PASSWORD),
    )


def check_neo4j_connection():
    try:
        with get_neo4j_driver() as driver:
            driver.verify_connectivity()

        neo4j_status.update({"connected": True, "message": "Connected to Neo4j."})
    except Exception as exc:
        neo4j_status.update(
            {"connected": False, "message": f"Neo4j connection failed: {exc}"}
        )

    return neo4j_status


def get_gemini_client():
    return client


def friendly_ai_error(error_text):
    error_text = (error_text or "").lower()

    if "timeout" in error_text or "timed out" in error_text:
        return "Request timed out. Try again."
    if (
        "api key" in error_text
        or "expired" in error_text
        or "permission" in error_text
        or "unauthorized" in error_text
        or "authentication" in error_text
    ):
        return "AI service is temporarily unavailable. Please check your Gemini API key."
    if "quota" in error_text or "resource_exhausted" in error_text or "429" in error_text:
        return "AI service quota exceeded. Please try again later."
    if (
        "network" in error_text
        or "connection" in error_text
        or "connect" in error_text
        or "dns" in error_text
        or "resolve" in error_text
        or "ssl" in error_text
    ):
        return "Could not connect to AI service."

    return "AI service is temporarily unavailable. Please check your Gemini API key."


def safe_generate(prompt, timeout_seconds=20):
    if not client:
        return None, "AI service is temporarily unavailable. Please check your Gemini API key."

    def call_gemini():
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt,
        )
        return response.text

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(call_gemini)

    try:
        response_text = future.result(timeout=timeout_seconds)
        return response_text, None
    except TimeoutError:
        future.cancel()
        return None, "Request timed out. Try again."
    except Exception as exc:
        return None, friendly_ai_error(str(exc))
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def check_gemini_startup():
    if not GEMINI_API_KEY:
        return

    response_text, error = safe_generate("Say OK.", timeout_seconds=8)

    if error:
        print(f"Gemini startup check failed: {error}")
    elif response_text:
        print("Gemini connection successful")


def extract_text_from_pdf(filepath):
    text = ""

    with fitz.open(filepath) as doc:
        for page in doc:
            text += page.get_text()

    return text.strip()


def summarize_text(text):
    prompt = f"""
Summarize the following PDF text in simple terms.
Use short paragraphs and bullet points where helpful.

PDF text:
{text[:8000]}
"""
    response_text, error = safe_generate(prompt)

    if error:
        return error

    return response_text or "Could not process response."


def clean_json_text(text):
    text = text.strip()

    if text.startswith("```"):
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"^```\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    start = text.find("[")
    end = text.rfind("]")

    if start != -1 and end != -1:
        return text[start : end + 1]

    return text


def clean_json_object_text(text):
    text = text.strip()

    if text.startswith("```"):
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"^```\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1:
        return text[start : end + 1]

    return text


def generate_quiz(topic, context_text=None):
    context = context_text or topic
    prompt = f"""
Generate 5 multiple choice questions.
Format strictly as JSON:
[
  {{
    "question": "...",
    "options": ["A", "B", "C", "D"],
    "answer": "correct option"
  }}
]

Topic:
{topic}

Context:
{context[:5000]}
"""
    response_text, error = safe_generate(prompt)

    if error:
        return []

    try:
        questions = json.loads(clean_json_text(response_text or "[]"))
    except (json.JSONDecodeError, TypeError, AttributeError):
        return []

    valid_questions = []

    for item in questions:
        question = item.get("question")
        options = item.get("options", [])
        answer = item.get("answer")

        if question and len(options) == 4 and answer in options:
            valid_questions.append(
                {"question": question, "options": options, "answer": answer}
            )

    return valid_questions[:5]


def generate_simple_explanation(topic, context_text=None):
    prompt = f"""
Explain "{topic}" in simple beginner-friendly language.
Keep it short, clear, and useful for revision.

Context:
{(context_text or topic)[:5000]}
"""
    response_text, error = safe_generate(prompt)

    if error:
        return context_text or f"Study {topic} step by step."

    return response_text or context_text or f"Study {topic} step by step."


def infer_main_topic(text):
    concepts = extract_key_concepts(text)
    return concepts[0] if concepts else "Uploaded PDF"


def clean_concept_name(text):
    return " ".join(word.capitalize() for word in text.split())


def is_meaningful_phrase(words):
    return (
        len(words) >= 2
        and not any(word in STOP_WORDS for word in words)
        and all(len(word) > 2 for word in words)
    )


def extract_key_concepts(summary):
    phrase_counts = {}
    sentences = re.split(r"[.!?;:\n]+", summary.lower())

    for sentence in sentences:
        words = re.findall(r"\b[A-Za-z][A-Za-z-]{2,}\b", sentence)
        chunk = []

        for word in words:
            if word in STOP_WORDS:
                if len(chunk) >= 2:
                    add_phrases_from_chunk(chunk, phrase_counts)
                chunk = []
            else:
                chunk.append(word)

        if len(chunk) >= 2:
            add_phrases_from_chunk(chunk, phrase_counts)

    sorted_phrases = sorted(
        phrase_counts.items(),
        key=lambda item: (item[1], -len(item[0].split())),
        reverse=True,
    )

    concepts = []

    for phrase, count in sorted_phrases:
        concept = clean_concept_name(phrase)

        if concept not in concepts:
            concepts.append(concept)

        if len(concepts) == 10:
            break

    return concepts


def add_phrases_from_chunk(chunk, phrase_counts):
    for phrase_size in (2, 3):
        for index in range(len(chunk) - phrase_size + 1):
            phrase_words = chunk[index : index + phrase_size]

            if is_meaningful_phrase(phrase_words):
                phrase = " ".join(phrase_words)
                phrase_counts[phrase] = phrase_counts.get(phrase, 0) + 1


def build_knowledge_graph(summary):
    concepts = extract_key_concepts(summary)
    graph = nx.MultiDiGraph()
    edges = []
    triples = []

    graph.add_node("Summary", important=True)

    for index, concept in enumerate(concepts):
        graph.add_node(concept, important=index < 5)

        relation = "EXPLAINS" if index < 3 else "RELATED_TO"
        graph.add_edge("Summary", concept, relation=relation)
        triples.append(("Summary", relation, concept))
        edges.append({"subject": "Summary", "relation": relation, "object": concept})

    for index in range(len(concepts) - 1):
        previous_concept = concepts[index]
        next_concept = concepts[index + 1]

        graph.add_edge(previous_concept, next_concept, relation="NEXT_TOPIC")
        graph.add_edge(next_concept, previous_concept, relation="PREREQUISITE")
        triples.append((previous_concept, "NEXT_TOPIC", next_concept))
        triples.append((next_concept, "PREREQUISITE", previous_concept))
        edges.append(
            {
                "subject": previous_concept,
                "relation": "NEXT_TOPIC",
                "object": next_concept,
            }
        )
        edges.append(
            {
                "subject": next_concept,
                "relation": "PREREQUISITE",
                "object": previous_concept,
            }
        )

    nodes = [
        {"name": node, "important": graph.nodes[node].get("important", False)}
        for node in graph.nodes
    ]

    return {"nodes": nodes, "edges": edges, "triples": triples}


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

        neo4j_status.update({"connected": True, "message": "Graph saved to Neo4j."})
    except Exception as exc:
        neo4j_status.update(
            {"connected": False, "message": f"Could not save graph to Neo4j: {exc}"}
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
                    relation = record["relation"] or "is related to"

                    nodes_by_name[subject] = {
                        "name": subject,
                        "important": bool(record["subject_important"]),
                    }
                    nodes_by_name[object_name] = {
                        "name": object_name,
                        "important": bool(record["object_important"]),
                    }
                    edges.append(
                        {
                            "subject": subject,
                            "relation": relation,
                            "object": object_name,
                        }
                    )
                    triples.append((subject, relation, object_name))

        graph_data = {
            "nodes": list(nodes_by_name.values()),
            "edges": edges,
            "triples": triples,
        }

        if graph_data["nodes"]:
            knowledge_graph.update(graph_data)

        neo4j_status.update({"connected": True, "message": "Graph loaded from Neo4j."})
        return graph_data
    except Exception as exc:
        neo4j_status.update(
            {"connected": False, "message": f"Could not load graph from Neo4j: {exc}"}
        )
        return knowledge_graph


def clean_topic_list(topics):
    return sorted({topic for topic in topics if topic})


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
            result = driver.execute_query(
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

        if not result.records:
            return [], []

        record = result.records[0]
        before = clean_topic_list(record["before_topics"])
        after = clean_topic_list(record["after_topics"])
        return before, after
    except Exception:
        return [], []


def parse_ai_topic_suggestions(text):
    before = []
    after = []
    mode = None

    for line in text.splitlines():
        clean_line = line.strip()
        lower_line = clean_line.lower()

        if "prerequisite" in lower_line or "before" in lower_line:
            mode = "before"
        elif "next" in lower_line or "after" in lower_line:
            mode = "after"
        elif clean_line.startswith(("-", "*")) and mode:
            topic_name = clean_line.lstrip("-* ").strip()
            topic_name = re.sub(r"^\d+[\).\s]+", "", topic_name).strip()

            if topic_name:
                if mode == "before":
                    before.append(clean_concept_name(topic_name))
                elif mode == "after":
                    after.append(clean_concept_name(topic_name))

    return clean_topic_list(before)[:5], clean_topic_list(after)[:5]


def generate_topic_suggestions_with_ai(topic):
    prompt = f"""
For the topic "{topic}", give:
1. Prerequisites (topics to learn before)
2. Next topics (what to learn after)

Keep answers short (max 5 each).
Use bullet points under headings "Before" and "After".
"""
    response_text, error = safe_generate(prompt)

    if error:
        return [], []

    return parse_ai_topic_suggestions(response_text or "")


def save_topic_suggestions(topic, before, after):
    clean_topic = clean_concept_name(topic)

    try:
        with get_neo4j_driver() as driver:
            for before_topic in before:
                driver.execute_query(
                    """
                    MERGE (before:Concept {name: $before_topic})
                    MERGE (topic:Concept {name: $topic})
                    MERGE (before)-[:NEXT_TOPIC]->(topic)
                    MERGE (topic)-[:PREREQUISITE]->(before)
                    """,
                    before_topic=before_topic,
                    topic=clean_topic,
                )

            for after_topic in after:
                driver.execute_query(
                    """
                    MERGE (topic:Concept {name: $topic})
                    MERGE (after:Concept {name: $after_topic})
                    MERGE (topic)-[:NEXT_TOPIC]->(after)
                    MERGE (after)-[:PREREQUISITE]->(topic)
                    """,
                    topic=clean_topic,
                    after_topic=after_topic,
                )
    except Exception:
        pass


def get_or_create_topic_suggestions(topic):
    clean_topic = clean_concept_name(topic)
    before, after = fetch_suggestions_for_topic(clean_topic)

    if before or after:
        return clean_topic, before, after

    before, after = generate_topic_suggestions_with_ai(clean_topic)

    if before or after:
        save_topic_suggestions(clean_topic, before, after)

    return clean_topic, before, after


def check_topic_ambiguity(topic):
    prompt = f"""
The topic "{topic}" may have multiple meanings.

Return JSON format:
{{
  "ambiguous": true,
  "options": [
    "option1",
    "option2"
  ]
}}

If topic is clearly academic and specific,
set ambiguous=false.
"""
    response_text, error = safe_generate(prompt)

    if error:
        return {"ambiguous": False, "options": [], "error": error}

    try:
        data = json.loads(clean_json_object_text(response_text or "{}"))
    except (json.JSONDecodeError, TypeError, AttributeError):
        return {
            "ambiguous": False,
            "options": [],
            "error": "Could not process response.",
        }

    clean_options = []

    for option in data.get("options", []):
        if isinstance(option, str):
            clean_option = clean_concept_name(option)
            if clean_option and clean_option not in clean_options:
                clean_options.append(clean_option)

    return {
        "ambiguous": bool(data.get("ambiguous")) and len(clean_options) > 1,
        "options": clean_options[:3],
        "error": None,
    }


def process_input(topic=None, text=None):
    summary = None
    context_text = text
    graph_data = None

    if text:
        summary = summarize_text(text)
        topic = infer_main_topic(summary or text)
        context_text = summary
        graph_data = build_knowledge_graph(summary or text)
        knowledge_graph.update(graph_data)
        save_graph_to_neo4j(graph_data)
    elif topic:
        topic = clean_concept_name(topic)
        summary = generate_simple_explanation(topic)
        context_text = summary
    else:
        topic = "Learning Topic"
        summary = "No topic or PDF content was provided."

    topic, before, after = get_or_create_topic_suggestions(topic)

    quiz_data = generate_quiz(topic, context_text)
    latest_quiz.clear()
    latest_quiz.extend(quiz_data)

    result = {
        "topic": topic,
        "summary": summary,
        "before": before[:5],
        "after": after[:5],
        "quiz": quiz_data,
    }
    latest_result.clear()
    latest_result.update(result)

    return result


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/upload", methods=["GET", "POST"])
def upload():
    error = None

    if request.method == "POST":
        uploaded_file = request.files.get("file")

        if not uploaded_file or not uploaded_file.filename:
            error = "Please choose a PDF file first."
        elif not uploaded_file.filename.lower().endswith(".pdf"):
            error = "Please upload a PDF file."
        else:
            filepath = os.path.join(
                UPLOAD_FOLDER,
                secure_filename(uploaded_file.filename),
            )
            uploaded_file.save(filepath)

            try:
                text = extract_text_from_pdf(filepath)

                if not text:
                    error = "No readable text was found in this PDF."
                else:
                    result = process_input(text=text)
                    return render_template("result.html", result=result)
            except Exception:
                error = "Something went wrong while processing the file. Please try again."

    return render_template(
        "upload.html",
        error=error,
        neo4j_status=neo4j_status,
    )


@app.route("/graph")
def graph():
    if latest_result:
        return render_template("result.html", result=latest_result)

    return render_template("result_empty.html")


@app.route("/quiz")
def quiz():
    return render_template("quiz.html", quiz=latest_quiz)


@app.route("/topic", methods=["GET", "POST"])
def topic():
    if request.method == "POST":
        user_topic = request.form.get("topic", "").strip()
        selected_topic = request.form.get("selected_topic", "").strip()

        if selected_topic:
            result = process_input(topic=selected_topic)
            return render_template("result.html", result=result)

        if not user_topic:
            return render_template(
                "topic_input.html",
                error="Please enter a topic.",
            )

        ambiguity = check_topic_ambiguity(user_topic)

        if ambiguity.get("error"):
            return render_template(
                "topic_input.html",
                error=ambiguity["error"],
            )

        if ambiguity.get("ambiguous"):
            return render_template(
                "topic_options.html",
                topic=user_topic,
                options=ambiguity["options"],
            )

        chosen_topic = ambiguity["options"][0] if ambiguity.get("options") else user_topic
        result = process_input(topic=chosen_topic)
        return render_template("result.html", result=result)

    return render_template("topic_input.html")


check_gemini_startup()


if __name__ == "__main__":
    app.run(debug=True)
