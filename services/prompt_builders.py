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
- APPLICATION_OF
- USED_IN
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
- APPLICATION_OF (destination is a real-world software/engineering application of source)
- USED_IN (source is utilized within destination production environment)

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
You are an expert University Curriculum Director and Knowledge Graph Architect.
Your task is to construct a rigorous, domain-agnostic educational knowledge graph for a given learning topic.
Return JSON ONLY. Do not include markdown wrappers, explanations, or long lecture paragraphs.

CRITICAL ARCHITECTURAL DIRECTIVE:
You act as a knowledge graph constructor, NOT a template generator.
Every generated node MUST be an independently meaningful, standalone educational concept that could exist as a standalone Wikipedia article, textbook chapter, or university course lecture title (e.g., 'AVL Tree', 'Plasma Confinement', 'Calvin Cycle', 'Stellar Nucleosynthesis', 'Fourier Transform', 'Macroeconomics').

STRICTLY FORBIDDEN TEMPLATE PATTERNS (NEVER GENERATE THESE):
- NEVER generate placeholder names matching: 'Basic <Topic>', 'Intermediate <Topic>', 'Advanced <Topic>', 'Applied <Topic>', 'Practical <Topic>', 'Implementation of <Topic>', 'Introduction to <Topic>', 'Core <Topic>', 'Mastering <Topic>', 'Expert <Topic>', '<Topic> Concept', '<Topic> Applications', '<Topic> Optimization'.
- If you cannot identify a genuine distinct educational concept for a list, return an empty list [].

POSITIVE MULTI-DOMAIN KNOWLEDGE GRAPH EXAMPLES:
- Computer Science: Linked List -> Prerequisites: [Arrays, Pointer] -> Successors: [Doubly Linked List, Circular Linked List, Skip List]
- Computer Science: Binary Tree -> Prerequisites: [Recursion, Pointer] -> Successors: [Tree Traversal, Binary Search Tree, AVL Tree]
- Physics: Electron -> Prerequisites: [Atomic Structure] -> Successors: [Electron Configuration, Atomic Orbitals, Chemical Bonding]
- Physics: Nuclear Fusion -> Prerequisites: [Nuclear Physics] -> Successors: [Plasma Physics, Magnetic Confinement, Tokamak Reactor]
- Biology: Photosynthesis -> Prerequisites: [Chloroplast, Plant Cell] -> Successors: [Light Dependent Reactions, Calvin Cycle, Cellular Respiration]
- Mathematics: Linear Algebra -> Prerequisites: [Matrix, Vector] -> Successors: [Eigenvalues and Eigenvectors, Singular Value Decomposition]
"""
    user_prompt = f"""
Construct a Knowledge Graph Roadmap for the educational concept: {topic}

Context / Study Material:
{(context_text or topic)[:6000]}

Return JSON ONLY in this exact shape:
{{
  "prerequisites": [
    {{
      "topic": "Real Prerequisite Concept 1",
      "why": "Pedagogical explanation of why this prerequisite is required."
    }}
  ],
  "next_topics": [
    {{
      "topic": "Real Successor Concept 1",
      "why": "Pedagogical explanation of why this is a logical next topic."
    }}
  ],
  "related_topics": [
    {{
      "topic": "Real Related Concept 1",
      "why": "Explanation of how this connects to the main topic."
    }}
  ]
}}

Rules:
1. Every item in 'prerequisites', 'next_topics', and 'related_topics' MUST be a dictionary containing 'topic' (a real, distinct educational concept name) and 'why' (a clear relationship explanation of at least 10 characters).
2. NEVER produce template phrases like 'Basic {topic}', 'Applied {topic}', 'Intermediate {topic} Implementation', or 'Advanced {topic} Applications'.
3. If no genuine distinct concept exists for a list, return [].
"""
    return system_prompt, user_prompt


def build_topic_lecture_prompt(topic):
    system_prompt = """
You are an experienced, patient university professor specializing in beginner education.
Teach the requested topic as a coherent, engaging classroom lecture for a first-year undergraduate student.

Pedagogical Principles:
- Conversational, encouraging tone: Guide the student smoothly from simple intuition toward deeper technical understanding.
- Plain-language opening: Explain the concept in everyday language. Avoid jargon in the opening.
- Explain WHY before HOW: Explain the real-world engineering problem that motivated the concept before diving into mechanics or code.
- Build Intuition First: Use vivid mental models and relatable real-life analogies to make abstract ideas concrete before showing syntax or formulas.
- Annotated Code Logic: When presenting code, explain line-by-line why statements exist and what happens in memory.
- Intuitive Complexity Reasoning: Explain Time and Space Complexity by detailing the memory allocations and loop mechanics under the hood (e.g. why traversal takes O(N) or why hash lookup averages O(1)).
- Student Misconceptions & Interview Expectations: Highlight common beginner mistakes and practical exam/interview questions naturally.
- Zero generic filler: Avoid phrases like "X is a fundamental educational concept" or Wikipedia-style summaries. Every paragraph must contribute real learning value.
Return ONLY valid JSON.
"""
    user_prompt = f"""
Deliver a comprehensive, high-quality university lecture for: {topic}

Teach this concept assuming the learner is studying it for the first time.
Structure your lecture around these educational dimensions (feel free to flow naturally between related ideas):

- definition: Clear, beginner-friendly 1-2 paragraph introduction in plain everyday language without opening jargon.
- why_needed: The real-world problem {topic} solves and practical engineering motivation (explain WHY before HOW).
- intuition: Intuitive mental model to help the learner picture the core concept.
- analogy: A vivid, relatable real-life analogy simplifying the core idea.
- steps: Detailed, step-by-step walkthrough of how {topic} works under the hood.
- visual: Descriptive mental imagery guiding what the student should visualize in memory.
- example: A clear conceptual example walkthrough before introducing code.
- code: Clean code implementation with line-by-line comments explaining key logic and memory behavior.
- complexity: Time and Space Complexity analysis explaining *WHY* those complexities occur based on loop iterations or memory space.
- advantages: Key strengths and situations where {topic} performs exceptionally well.
- limitations: Trade-offs, drawbacks, and scenarios where alternative approaches are better.
- mistakes: Frequent beginner misconceptions, off-by-one errors, and implementation pitfalls.
- interview: Core exam and technical interview questions with key answer points.
- summary: Short, encouraging recap of key takeaways.
- next_steps: Recommended successor topics and why they naturally build upon {topic}.

Return ONLY JSON in this exact shape:
{{
  "topic": "{topic}",
  "definition": "Clear, beginner-friendly 1-2 paragraph introduction in plain everyday language.",
  "why_needed": "Real-world engineering problem solved by {topic} and practical motivation.",
  "intuition": "Intuitive mental model building conceptual understanding.",
  "analogy": "Vivid real-life analogy relating {topic} to familiar everyday objects.",
  "steps": "1. First step...\\n2. Second step...\\n3. Third step...",
  "visual": "Visual description guiding mental imagination.",
  "example": "Detailed conceptual walkthrough step by step.",
  "code": "Clean, commented code block with line-by-line logic explanations.",
  "complexity": "Time and Space Complexity breakdown explaining *WHY* those complexities occur.",
  "advantages": "Main strengths and scenarios where {topic} performs best.",
  "limitations": "Trade-offs and situations where alternative approaches are better.",
  "mistakes": "Frequent student mistakes and anti-patterns.",
  "interview": "Exam and interview questions with key answer points.",
  "summary": "Short recap of key takeaways.",
  "next_steps": "Logical successor topics to study next."
}}
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
