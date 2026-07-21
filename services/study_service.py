"""
study_service.py

Responsible ONLY for orchestrating the learning workflow:
- Coordinating roadmap generation
- Lazy on-demand lecture generation & application-level caching
- Coordinating semantic recommendation categorization and quiz service
"""

import json
import re

from models.state import latest_quiz, latest_result
from services.groq_service import safe_groq_generate
from services.neo4j_service import fetch_prerequisite_chain_from_neo4j, fetch_raw_suggestions_from_neo4j
from services.prompt_builders import build_topic_lecture_prompt
from services.quiz_service import generate_quiz
from services.recommendation_service import categorize_and_rank_recommendations
from services.roadmap_service import get_or_create_roadmap
from utils.topic_validator import canonicalize_concept_name, logger


LECTURE_CACHE = {}


def clean_json_text(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    # Handle common unescaped string issue in LLM code blocks
    return text.replace("\t", "    ")


def try_extract_lecture_keys(response_text):
    """
    Regex fallback extractor to salvage rich JSON section content if json.loads() fails due to syntax cutoffs.
    """
    extracted = {}
    keys = [
        "definition", "why_needed", "why_it_matters", "motivation",
        "intuition", "analogy", "real_world_analogy",
        "steps", "step_by_step_explanation", "visual", "visual_thinking",
        "example", "simple_example", "code", "code_example", "complexity", "time_space_complexity",
        "advantages", "limitations", "mistakes", "common_mistakes",
        "interview", "interview_perspective", "summary", "next_steps"
    ]
    for key in keys:
        pattern = rf'"{key}"\s*:\s*"([^"]+)"'
        match = re.search(pattern, response_text, re.DOTALL)
        if match:
            extracted[key] = match.group(1).strip()

    return extracted if len(extracted) >= 3 else None


def get_or_create_topic_lecture(topic):
    clean_t = canonicalize_concept_name(topic)
    cache_key = clean_t.lower()

    if cache_key in LECTURE_CACHE:
        logger.info(f"[VALIDATION] Retrieved lecture for '{clean_t}' from application-level cache.")
        return LECTURE_CACHE[cache_key]

    system_prompt, user_prompt = build_topic_lecture_prompt(clean_t)
    response_text, error = safe_groq_generate(system_prompt, user_prompt, max_tokens=2500)

    if error:
        logger.error(f"[AI RESPONSE] Topic lecture generation failed for '{clean_t}': {error}")
        lecture_data = generate_fallback_lecture(clean_t)
        LECTURE_CACHE[cache_key] = lecture_data
        return lecture_data

    lecture_data = None
    try:
        logger.info(f"[JSON PARSING] Parsing JSON for university professor lecture on '{clean_t}'...")
        cleaned = clean_json_text(response_text)
        lecture_data = json.loads(cleaned)
        logger.info(f"[JSON PARSING] Success parsing lecture JSON for '{clean_t}'.")
    except (json.JSONDecodeError, TypeError) as exc:
        logger.error(f"[JSON PARSING] Standard JSON parsing failed for '{clean_t}': {exc}. Attempting regex recovery...")
        recovered = try_extract_lecture_keys(response_text)
        if recovered:
            logger.info(f"[JSON PARSING] Recovered {len(recovered)} key sections via regex for '{clean_t}'.")
            lecture_data = recovered
        else:
            logger.error(f"[JSON PARSING] Could not recover lecture text for '{clean_t}'. Using dynamic educational fallback.")
            lecture_data = generate_fallback_lecture(clean_t)

    formatted_explanation = format_rich_lecture_explanation(lecture_data)
    lecture_data["explanation"] = formatted_explanation
    LECTURE_CACHE[cache_key] = lecture_data
    return lecture_data


def generate_fallback_lecture(topic):
    clean_t = canonicalize_concept_name(topic)
    
    definition_text = (
        f"**{clean_t}** is an essential data and computational structure designed to organize, manage, and process information efficiently.\n\n"
        f"At its core, {clean_t} establishes clear rules for how data items relate to one another in memory and how operations like searching, insertion, and deletion are executed."
    )
    why_text = (
        f"Without **{clean_t}**, software applications would struggle with high computational latency, unorganized data storage, and poor memory utilization.\n\n"
        f"Engineers choose {clean_t} when building production systems to achieve predictable execution time and scalable memory architecture."
    )
    intuition_text = (
        f"To build a mental model of **{clean_t}**, think of it as a specialized physical workspace where every item has a specific place and retrieval rule.\n\n"
        f"Rather than searching randomly through unsorted items, {clean_t} provides a structured path directly to the needed resource."
    )
    analogy_text = (
        f"Using **{clean_t}** is like using a well-organized index in a library or train coaches connected sequentially.\n\n"
        f"Each component links predictably to the next, allowing you to traverse or access items without getting lost."
    )
    steps_text = (
        f"1. **Initialization**: Memory space or reference pointers are allocated for {clean_t}.\n"
        f"2. **Insertion & Lookup**: New elements are placed following the structure's positional rules (e.g. key hashing, node links, or index offsets).\n"
        f"3. **Traversal & Processing**: Algorithms iterate through elements systematically to inspect or update data.\n"
        f"4. **Deletion & Cleanup**: Removed items are decoupled cleanly to avoid memory leaks."
    )
    visual_text = (
        f"Imagine a series of labeled boxes placed in order on a shelf.\n\n"
        f"Each box contains data and an arrow pointing to where the next relevant box is located in memory."
    )
    example_text = (
        f"Consider storing a sequence of 5 elements using {clean_t}.\n\n"
        f"When inserting a new element, {clean_t} updates internal references or indices in place, preserving structural integrity."
    )
    code_text = (
        f"// Conceptual implementation of {clean_t}\n"
        f"class {clean_t.replace(' ', '')}Node {{\n"
        f"    constructor(value) {{\n"
        f"        this.value = value;\n"
        f"        this.next = null;\n"
        f"    }}\n"
        f"}}\n\n"
        f"// Usage Example:\n"
        f"const node1 = new {clean_t.replace(' ', '')}Node('Data A');\n"
        f"const node2 = new {clean_t.replace(' ', '')}Node('Data B');\n"
        f"node1.next = node2; // Connect nodes"
    )
    advantages_text = (
        f"- **Predictable Performance**: Optimizes runtime for frequent operations.\n"
        f"- **Dynamic Memory Allocation**: Adapts efficiently to changing data sizes.\n"
        f"- **Modularity**: Simplifies complex system architecture into reusable operations."
    )
    limitations_text = (
        f"- **Memory Overhead**: Requires extra pointer/metadata storage per element.\n"
        f"- **Access Trade-offs**: Random access may require O(N) traversal compared to static arrays."
    )
    mistakes_text = (
        f"- **Null Pointer Errors**: Forgetting to check if references exist before accessing properties.\n"
        f"- **Off-by-One Errors**: Miscalculating boundary conditions during loop iteration."
    )
    interview_text = (
        f"**Question**: Explain how {clean_t} works and state its time complexity for core operations.\n\n"
        f"**Answer**: Describe the node/index structure, explain time complexity (e.g., O(1) vs O(N)), and compare it with alternative data structures."
    )
    summary_text = f"**{clean_t}** combines structured memory organization with efficient algorithms to solve core computer science problems."
    next_text = f"Study advanced variations, balancing techniques, and real-world system applications of **{clean_t}**."

    fallback = {
        "topic": clean_t,
        "definition": definition_text,
        "why_needed": why_text,
        "why_it_matters": why_text,
        "intuition": intuition_text,
        "analogy": analogy_text,
        "real_world_analogy": analogy_text,
        "steps": steps_text,
        "step_by_step_explanation": steps_text,
        "visual": visual_text,
        "visual_thinking": visual_text,
        "example": example_text,
        "simple_example": example_text,
        "code": code_text,
        "code_example": code_text,
        "advantages": advantages_text,
        "limitations": limitations_text,
        "mistakes": mistakes_text,
        "common_mistakes": mistakes_text,
        "interview": interview_text,
        "interview_perspective": interview_text,
        "summary": summary_text,
        "next_steps": next_text,
        "what_to_learn_next": next_text,
    }
    fallback["explanation"] = format_rich_lecture_explanation(fallback)
    return fallback


def format_rich_lecture_explanation(data):
    def get_val(*keys):
        for k in keys:
            v = data.get(k)
            if v and isinstance(v, str) and len(v.strip()) > 0:
                return v.strip()
        return ""

    definition = get_val("definition", "summary", "overview")
    why_needed = get_val("why_needed", "why_it_matters", "motivation", "problem_solved")
    intuition = get_val("intuition", "mental_model", "core_idea")
    analogy = get_val("analogy", "real_world_analogy", "real_life_analogy")
    steps = get_val("steps", "step_by_step_explanation", "step_by_step", "working")
    visual = get_val("visual", "visual_thinking", "visualization")
    example = get_val("example", "simple_example", "examples", "walkthrough")
    code = get_val("code", "code_example", "code_walkthrough")
    complexity = get_val("complexity", "time_space_complexity", "complexity_analysis")
    advantages = get_val("advantages", "benefits", "strengths")
    limitations = get_val("limitations", "drawbacks", "tradeoffs")
    mistakes = get_val("mistakes", "common_mistakes", "student_mistakes")
    interview = get_val("interview", "interview_perspective", "interview_questions", "exam_questions")
    summary = get_val("summary", "revision_summary", "recap")
    next_steps = get_val("next_steps", "what_to_learn_next", "learning_tips", "next_topics")

    sections = [
        f"### Simple Definition\n{definition}",
        f"### Why Do We Need It?\n{why_needed}",
        f"### Intuition & Mental Model\n{intuition}",
        f"### Real-Life Analogy\n{analogy}",
        f"### Step-by-Step Working\n{steps}",
        f"### Visual Representation\n{visual}",
        f"### Practical Example\n{example}",
        f"### Code Walkthrough & Line-by-Line Logic\n{code}",
        f"### Time & Space Complexity Breakdown\n{complexity}",
        f"### Key Strengths & Advantages\n{advantages}",
        f"### Trade-offs & Limitations\n{limitations}",
        f"### Common Beginner Mistakes\n{mistakes}",
        f"### Exam & Interview Perspective\n{interview}",
        f"### Summary & Key Takeaways\n{summary}",
        f"### What To Learn Next\n{next_steps}",
    ]
    return "\n\n".join(s for s in sections if len(s.split("\n", 1)[-1].strip()) > 0)


def infer_topic_from_text(text):
    system_prompt = "You extract one main educational topic. Return only the topic name."
    user_prompt = f"Identify the ONE main study topic from this text:\n\n{text[:4000]}"
    response_text, error = safe_groq_generate(system_prompt, user_prompt, max_tokens=80)

    if error:
        logger.error(f"[AI RESPONSE] Main topic inference failed: {error}")
        return "Uploaded PDF"

    return (response_text or "Uploaded PDF").strip().strip('"')


def process_input(topic=None, text=None):
    raw_query = topic or (text[:30] if text else "Learning Topic")
    if text:
        topic = infer_topic_from_text(text)
        context_text = text
    else:
        context_text = topic or ""
        topic = topic or "Learning Topic"

    roadmap = get_or_create_roadmap(topic, context_text)
    canonical_topic = roadmap["topic"]

    # Diagnostic Logging: Pipeline Entry
    logger.info(f"\n--- [DIAGNOSTIC LEARN NEXT RECOMMENDATIONS] ---")
    logger.info(f"User Query: '{raw_query}'")
    logger.info(f"Canonical Topic: '{canonical_topic}'")

    lecture = get_or_create_topic_lecture(canonical_topic)

    # Collect raw candidates by source direction and relationship type
    raw_candidates_by_source = {
        "before": [],
        "after": [],
        "related": [],
    }

    # Populate from roadmap tiers
    for item in roadmap.get("prerequisites", []) + roadmap.get("foundation_topics", []) + roadmap.get("beginner_topics", []):
        if isinstance(item, dict) and item.get("topic"):
            raw_candidates_by_source["before"].append({"topic": item["topic"], "relation": "PREREQUISITE_OF", "why": item.get("why", "")})

    for item in roadmap.get("next_topics", []) + roadmap.get("intermediate_topics", []) + roadmap.get("advanced_topics", []):
        if isinstance(item, dict) and item.get("topic"):
            raw_candidates_by_source["after"].append({"topic": item["topic"], "relation": "BUILDS_ON", "why": item.get("why", "")})

    for item in roadmap.get("related_topics", []) + roadmap.get("optional_reading", []):
        if isinstance(item, dict) and item.get("topic"):
            raw_candidates_by_source["related"].append({"topic": item["topic"], "relation": "RELATED_TO", "why": item.get("why", "")})

    # Retrieve graph relationships from Neo4j
    neo4j_records = fetch_raw_suggestions_from_neo4j(canonical_topic)
    if neo4j_records:
        g_item = neo4j_records[0]
        raw_candidates_by_source["before"].extend(g_item.get("before", []))
        raw_candidates_by_source["after"].extend(g_item.get("after", []))

    # Retrieve multi-hop prerequisite chain from Neo4j
    multihop_chain = fetch_prerequisite_chain_from_neo4j(canonical_topic, max_depth=5)
    for chain_topic in multihop_chain:
        raw_candidates_by_source["before"].append({
            "topic": chain_topic,
            "relation": "PREREQUISITE_OF",
            "why": f"{chain_topic} is a foundational prerequisite in the learning graph for {canonical_topic}."
        })

    # Diagnostic Logging: Raw Outgoing Relationships Retrieved
    retrieved_after = [c["topic"] for c in raw_candidates_by_source["after"]]
    logger.info(f"Neo4j Query: Multi-hop outgoing NEXT_TOPIC/BUILDS_ON paths up to 5 levels for '{canonical_topic}'")
    logger.info(f"Relationships Retrieved (After): {retrieved_after}")

    # Categorize and rank recommendations into distinct sections with cross-section deduplication
    categorized = categorize_and_rank_recommendations(
        raw_candidates_by_source, canonical_topic, limit=5
    )

    ranked_before = categorized["before"]
    ranked_after = categorized["after"]
    ranked_related = categorized["related"]
    ranked_applications = categorized["applications"]

    # Diagnostic Logging: Final Learn Next Recommendations after Deduplication & Ranking
    final_next_names = [f"{item['topic']} (score: {item['score']}, conf: {item['confidence']})" for item in ranked_after]
    logger.info(f"Final Learn Next Recommendations: {final_next_names}")
    logger.info(f"---------------------------------------------------\n")

    quiz_context = "\n".join(
        [
            lecture.get("explanation", ""),
            lecture.get("analogy", "") or lecture.get("real_world_analogy", ""),
            "Prerequisites: " + ", ".join(item["topic"] for item in ranked_before),
            "Next topics: " + ", ".join(item["topic"] for item in ranked_after),
        ]
    )

    quiz_data = generate_quiz(canonical_topic, quiz_context)
    latest_quiz.clear()
    latest_quiz.extend(quiz_data)

    result = {
        "topic": canonical_topic,
        "summary": lecture.get("explanation"),
        "analogy": lecture.get("analogy") or lecture.get("real_world_analogy"),
        "definition": lecture.get("definition"),
        "why_it_matters": lecture.get("why_needed") or lecture.get("why_it_matters") or lecture.get("motivation"),
        "example": lecture.get("example") or lecture.get("simple_example") or lecture.get("code"),
        "difficulty": roadmap.get("difficulty"),
        "estimated_time": roadmap.get("estimated_study_time"),
        "before": ranked_before,
        "after": ranked_after,
        "related": ranked_related,
        "applications": ranked_applications,
        "quiz": quiz_data,
        "cached": roadmap.get("cached", False),
    }
    latest_result.clear()
    latest_result.update(result)

    return result
