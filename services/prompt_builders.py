"""
prompt_builders.py

Responsible ONLY for constructing system and user prompts for AI services.
No business logic, database queries, or network calls should exist here.
"""

import json


def build_topic_extraction_prompt(text):
    system_prompt = """
You are an expert curriculum designer. Your task is to extract core educational learning concepts from study material.
Return ONLY valid JSON. Do not include markdown, prose, or conversational text.
Only extract domain-specific educational concepts (e.g. ArrayList, Linked List, Binary Tree, Heap, Graph, DFS, Gradient Descent, Random Forest, Cell, Mitochondria, DNA).
Do not extract generic English words, pronouns, UI elements, verbs, adjectives, or sentence fragments.
"""
    user_prompt = f"""
Extract the key learning concepts from this study material.

Return ONLY JSON in this exact shape:
{{
  "concepts": [
    {{
      "name": "ArrayList",
      "definition": "short definition",
      "importance": "why it matters",
      "prerequisites": ["Arrays"],
      "next_topics": ["Linked List"]
    }}
  ]
}}

Rules:
- Include only real study concepts.
- Reject words like Learn, Your, Environment, Initial, Important, Example, Simple, Next, Topic, Step, Continue, Before, After, This, That, Understanding, Elements, and Size.
- If there are no domain concepts, return {{"concepts":[]}}.

Study material:
{(text or "")[:7000]}
"""
    return system_prompt, user_prompt


def build_relationship_extraction_prompt(summary, concepts):
    system_prompt = """
You classify educational relationships between learning concepts.
Return ONLY valid JSON. Do not include markdown, prose, or comments.
Use ONLY allowed relationship types representing true pedagogical dependency:
- PREREQUISITE_OF
- BUILDS_ON
- USES
- IMPLEMENTS
- PART_OF
- EXTENDS
- SPECIAL_CASE_OF
- ALTERNATIVE_TO
"""
    user_prompt = f"""
Classify meaningful educational relationships between these concepts.

Allowed relationship labels:
- PREREQUISITE_OF (source is required before destination)
- BUILDS_ON (destination expands upon source)
- USES (source utilizes destination)
- IMPLEMENTS (source is an implementation of destination)
- PART_OF (source is a subcomponent of destination)
- EXTENDS (source adds functionality to destination)
- SPECIAL_CASE_OF (source is a specific instance of destination)
- ALTERNATIVE_TO (source is an alternative approach to destination)

Return ONLY JSON in this exact shape:
{{
  "relationships": [
    {{
      "subject": "Binary Tree",
      "relation": "PREREQUISITE_OF",
      "object": "AVL Tree",
      "why": "AVL Tree is a self-balancing binary search tree, so basic Binary Tree mechanics must be understood first."
    }}
  ]
}}

Rules:
- Use only the concepts listed below as subject and object values.
- Every relationship must include a non-trivial 'why' explanation (>10 characters) detailing the educational reason.
- Do not create relationships just because concepts appear in the same text.
- If no meaningful relationship exists, return {{"relationships":[]}}.

Concepts:
{json.dumps(concepts)}

Study material:
{(summary or "")[:7000]}
"""
    return system_prompt, user_prompt


def build_pdf_analysis_prompt(text):
    system_prompt = """
You are an expert university professor performing chapter analysis on educational material.
Do NOT simply summarize the text. Perform a structured academic breakdown.
Return ONLY valid JSON. No markdown wrappers.
"""
    user_prompt = f"""
Analyze this study document as a university textbook chapter.

Study Material:
{(text or "")[:8000]}

Return ONLY JSON in this exact shape:
{{
  "title": "Inferred Chapter Title",
  "subject": "Academic Domain (e.g. Computer Science, Data Structures)",
  "chapter_overview": "Comprehensive 3-4 sentence overview of what this chapter teaches.",
  "learning_objectives": [
    "Specific learning objective 1",
    "Specific learning objective 2"
  ],
  "important_concepts": [
    {{
      "name": "Concept Name",
      "definition": "Clear 2-sentence definition",
      "importance": "Why this concept is fundamental"
    }}
  ],
  "definitions": [
    {{"term": "Term", "definition": "Definition"}}
  ],
  "algorithms": [
    {{"name": "Algorithm Name", "purpose": "What it accomplishes", "complexity": "Time/Space complexity"}}
  ],
  "formulas": [
    {{"formula": "Mathematical or logic expression", "explanation": "What it calculates"}}
  ],
  "examples": [
    {{"title": "Example Title", "description": "Worked example breakdown"}}
  ],
  "prerequisites": [
    {{"topic": "Prerequisite Concept", "why": "Why needed before studying this chapter"}}
  ],
  "learning_sequence": [
    "Step 1: Concept A",
    "Step 2: Concept B"
  ],
  "important_interview_topics": [
    "Key question or concept frequently tested"
  ],
  "common_mistakes": [
    "Common misconception or anti-pattern"
  ],
  "revision_notes": [
    "Concise key takeaway 1",
    "Concise key takeaway 2"
  ]
}}
"""
    return system_prompt, user_prompt


def build_roadmap_prompt(topic, context_text=None):
    system_prompt = """
You are a university curriculum director.
Design a structured, lightweight learning roadmap for a semester course.
Return JSON only. Do not include long lecture paragraphs.
Organize topics strictly into progressive educational levels.
"""
    user_prompt = f"""
Create a university semester-style learning roadmap for: {topic}

Context:
{(context_text or topic)[:6000]}

Return JSON only in this exact shape:
{{
  "topic": "{topic}",
  "estimated_study_time": "3-5 weeks (approx. 20-30 hours)",
  "difficulty": "Beginner | Intermediate | Advanced",
  "foundation_topics": [
    {{"topic": "Foundation Concept", "why": "Essential prerequisite foundation"}}
  ],
  "beginner_topics": [
    {{"topic": "Introductory Concept", "why": "Core starting building block"}}
  ],
  "intermediate_topics": [
    {{"topic": "Core Implementation Concept", "why": "Intermediate operational skill"}}
  ],
  "advanced_topics": [
    {{"topic": "Advanced Concept", "why": "Advanced optimization or variation"}}
  ],
  "optional_reading": [
    {{"topic": "Specialized Subtopic", "why": "Deep dive research topic"}}
  ],
  "learning_milestones": [
    "Milestone 1: Can implement basic structure",
    "Milestone 2: Understands time & space complexity"
  ],
  "prerequisites": [
    {{"topic": "Prerequisite Concept", "why": "Why needed first"}}
  ],
  "next_topics": [
    {{"topic": "Next Concept", "why": "Logical next step"}}
  ],
  "related_topics": [
    {{"topic": "Related Concept", "why": "Complementary topic"}}
  ]
}}

Rules:
- Extract only real study concepts.
- Keep explanations in 'why' fields concise (1-2 sentences).
- Do not include long lecture paragraphs.
"""
    return system_prompt, user_prompt


def build_topic_lecture_prompt(topic):
    system_prompt = """
You are an award-winning university professor teaching an in-depth lecture.
Explain the requested topic thoroughly, clearly, and engagingly.
Return ONLY valid JSON containing all 14 required educational sections. Target 300-700 words of rich content.
"""
    user_prompt = f"""
Deliver a comprehensive university lecture for the topic: {topic}

Return ONLY JSON in this exact shape:
{{
  "topic": "{topic}",
  "definition": "Rigorous academic yet clear definition",
  "intuition": "Intuitive mental model and core idea",
  "motivation": "Why this topic was developed and why computer scientists/engineers study it",
  "real_world_analogy": "Vivid, memorable real-world analogy",
  "step_by_step_explanation": "Detailed step-by-step breakdown of how it works under the hood",
  "examples": "Concrete worked example with code logic or step breakdown",
  "applications": "Real-world production applications and software industry use cases",
  "advantages": "Key strengths and benefits",
  "limitations": "Trade-offs, limitations, and edge-case drawbacks",
  "time_and_space_complexity": "Time complexity (Best, Average, Worst) and space complexity analysis",
  "common_mistakes": "Common student misconceptions and anti-patterns to avoid",
  "interview_questions": "2-3 popular university exam or technical interview questions with key answer points",
  "revision_summary": "Concise 3-sentence summary for rapid review",
  "learning_tips": "Practical advice on practicing and mastering this topic"
}}

Rules:
- Make every section thorough and educational. Do not return 1-sentence placeholders.
- Target 300-700 words of total educational content across sections.
"""
    return system_prompt, user_prompt


def build_quiz_prompt(topic, difficulty="easy", question_count=8):
    system_prompt = """
You are a senior university examiner. Create high-quality multiple-choice questions (MCQs) testing different cognitive levels.
Return ONLY valid JSON. No markdown wrappers.
"""
    user_prompt = f"""
Generate {question_count} multiple-choice questions for: {topic}

Target Difficulty: {difficulty}

Cognitive Levels to cover:
- Recall (testing definitions & terms)
- Conceptual Understanding (testing core mechanics & reasoning)
- Application (testing code logic & scenario outputs)
- Analysis (testing complexity trade-offs & edge cases)

Return ONLY JSON in this exact shape:
[
  {{
    "question": "Clear, precise question stem",
    "options": ["Option A", "Option B", "Option C", "Option D"],
    "answer": "Exact text matching one option",
    "explanation": "Detailed explanation of why this option is correct and why others are wrong.",
    "cognitive_level": "Recall | Understanding | Application | Analysis",
    "difficulty": "{difficulty}"
  }}
]

Rules:
- Options must be plausible distractors.
- Answer MUST exactly match one of the 4 options.
- Explanations must be thorough and educational.
"""
    return system_prompt, user_prompt
