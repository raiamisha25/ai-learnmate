import json

from services.groq_service import safe_groq_generate


def clean_json_text(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()
    start = text.find("[")
    end = text.rfind("]")
    return text[start : end + 1] if start != -1 and end != -1 else text


def fallback_quiz(topic):
    return [
        {
            "question": f"What is the main purpose of {topic}?",
            "options": [
                "To solve a specific learning or computing problem",
                "To store random words",
                "To avoid practice",
                "To replace all other topics",
            ],
            "answer": "To solve a specific learning or computing problem",
            "explanation": f"{topic} is best understood by learning what problem it solves.",
            "difficulty": "easy",
        }
    ]


def generate_quiz(topic, context_text=None):
    system_prompt = """
You create high-quality beginner quizzes.
Return JSON only. Each question must test the topic directly.
"""
    user_prompt = f"""
Generate 5 multiple choice questions for: {topic}

Context:
{(context_text or topic)[:5000]}

Return JSON only:
[
  {{
    "question": "...",
    "options": ["A", "B", "C", "D"],
    "answer": "exact correct option",
    "explanation": "short beginner-friendly explanation",
    "difficulty": "easy | medium | hard"
  }}
]
"""
    response_text, error = safe_groq_generate(system_prompt, user_prompt, max_tokens=1600)

    if error:
        print(f"Quiz generation failed: {error}")
        return fallback_quiz(topic)

    try:
        questions = json.loads(clean_json_text(response_text or "[]"))
    except (json.JSONDecodeError, TypeError, AttributeError) as exc:
        print(f"Quiz generation failed: could not parse Groq JSON response: {exc}")
        return fallback_quiz(topic)

    valid_questions = []

    for item in questions:
        question = item.get("question")
        options = item.get("options", [])
        answer = item.get("answer")
        explanation = item.get("explanation") or "Review this idea in the learning guide."
        difficulty = item.get("difficulty") or "easy"

        if question and len(options) == 4 and answer in options:
            valid_questions.append(
                {
                    "question": question,
                    "options": options,
                    "answer": answer,
                    "explanation": explanation,
                    "difficulty": difficulty,
                }
            )

    if not valid_questions:
        print("Quiz generation failed: Groq response did not contain valid MCQs.")
        return fallback_quiz(topic)

    return valid_questions[:5]
