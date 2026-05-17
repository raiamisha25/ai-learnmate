import json

from services.gemini_service import clean_json_text, safe_generate


def generate_quiz(topic, context_text=None):
    context = context_text or topic
    prompt = f"""
Generate 5 multiple choice questions for a beginner learning app.
Format strictly as JSON:
[
  {{
    "question": "...",
    "options": ["A", "B", "C", "D"],
    "answer": "correct option",
    "explanation": "one short reason why the answer is correct",
    "difficulty": "easy"
  }}
]

Topic:
{topic}

Context:
{context[:5000]}
"""
    response_text, error = safe_generate(prompt)

    if error:
        print(f"Quiz generation failed: {error}")
        return []

    try:
        questions = json.loads(clean_json_text(response_text or "[]"))
    except (json.JSONDecodeError, TypeError, AttributeError) as exc:
        print(f"Quiz generation failed: could not parse Gemini JSON response: {exc}")
        return []

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
        print("Quiz generation failed: Gemini response did not contain valid MCQs.")

    return valid_questions[:5]
