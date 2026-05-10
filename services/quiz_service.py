import json

from services.gemini_service import clean_json_text, safe_generate


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

