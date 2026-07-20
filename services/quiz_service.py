import json

from services.groq_service import safe_groq_generate
from services.prompt_builders import build_quiz_prompt
from utils.topic_validator import logger


QUESTION_COUNTS = {
    1: 8,
    3: 18,
    5: 30,
    10: 45,
}

LEVEL_RULES = {
    "easy": [
        (90, "LEARNER", "Look at you collecting knowledge points!"),
        (75, "STARTER", "Okay, you definitely studied... a little."),
        (60, "NEW", "Your brain just logged in!"),
    ],
    "medium": [
        (80, "PRO", "Are you secretly a quiz machine?"),
        (65, "SKILLED", "Your brain is leveling up fast!"),
        (50, "PLAYER", "Now the game is getting serious!"),
    ],
    "hard": [
        (75, "MASTER", "What are you gonna do with so much knowledge?!"),
        (60, "CHAMPION", "Save some intelligence for others!"),
        (45, "EXPERT", "Big brain energy detected!"),
    ],
}


def clean_json_text(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()
    start = text.find("[")
    end = text.rfind("]")
    return text[start : end + 1] if start != -1 and end != -1 else text


def fallback_quiz(topic, difficulty="easy", count=8):
    base_questions = [
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
            "cognitive_level": "Recall",
            "difficulty": difficulty,
        },
        {
            "question": f"What is the best way to master {topic}?",
            "options": [
                "Start with core concepts, then practice hands-on examples",
                "Memorize random definitions only",
                "Skip prerequisites",
                "Avoid quizzes",
            ],
            "answer": "Start with core concepts, then practice hands-on examples",
            "explanation": "Strong learning comes from combining theoretical understanding with practical application.",
            "cognitive_level": "Understanding",
            "difficulty": difficulty,
        },
    ]

    questions = []
    while len(questions) < count:
        questions.extend(base_questions)

    return questions[:count]


def question_count_for_duration(duration_minutes):
    return QUESTION_COUNTS.get(int(duration_minutes), 18)


def generate_quiz(topic, context_text=None, difficulty="easy", duration_minutes=3):
    difficulty = (difficulty or "easy").lower()
    question_count = question_count_for_duration(duration_minutes)

    system_prompt, user_prompt = build_quiz_prompt(topic, difficulty, question_count)
    response_text, error = safe_groq_generate(
        system_prompt,
        user_prompt,
        max_tokens=min(12000, question_count * 420),
    )

    if error:
        logger.error(f"[AI RESPONSE] Quiz generation failed for '{topic}': {error}")
        return fallback_quiz(topic, difficulty, question_count)

    try:
        logger.info(f"[JSON PARSING] Attempting to parse JSON for quiz on topic '{topic}'...")
        questions = json.loads(clean_json_text(response_text or "[]"))
        if isinstance(questions, dict):
            questions = questions.get("questions", [])
        logger.info(f"[JSON PARSING] Success parsing JSON for quiz on topic '{topic}'.")
    except (json.JSONDecodeError, TypeError, AttributeError) as exc:
        logger.error(f"[JSON PARSING] Failed parsing JSON for quiz on topic '{topic}': {exc}")
        return fallback_quiz(topic, difficulty, question_count)

    valid_questions = []

    for item in questions:
        question = item.get("question")
        options = item.get("options", [])
        answer = item.get("answer")
        explanation = item.get("explanation") or f"Review key concepts of {topic}."
        cognitive_level = item.get("cognitive_level") or "Understanding"

        if isinstance(answer, str) and answer.strip().upper() in ("A", "B", "C", "D"):
            answer_index = ord(answer.strip().upper()) - ord("A")
            if len(options) > answer_index:
                answer = options[answer_index]

        if question and len(options) == 4 and answer in options:
            valid_questions.append(
                {
                    "question": question,
                    "options": options,
                    "answer": answer,
                    "explanation": explanation,
                    "cognitive_level": cognitive_level,
                    "difficulty": difficulty,
                }
            )

    if not valid_questions:
        logger.info(f"[VALIDATION] Groq response did not contain valid MCQs for '{topic}'. Using fallback quiz.")
        return fallback_quiz(topic, difficulty, question_count)

    return valid_questions[:question_count]


def calculate_level(difficulty, accuracy):
    difficulty = (difficulty or "easy").lower()

    for threshold, level, comment in LEVEL_RULES.get(difficulty, LEVEL_RULES["easy"]):
        if accuracy >= threshold:
            return level, comment

    return "KEEP GOING", "Warm-up complete. Now your brain knows the controls."


def generate_quiz_comments(topic, difficulty, score, level):
    system_prompt = """
You write short, funny, family-friendly learning feedback.
Return JSON only. Maximum 20 words per comment.
"""
    user_prompt = f"""
Topic: {topic}
Difficulty: {difficulty}
Score percentage: {score}
Level: {level}

Return JSON only:
{{
  "funny_comment": "one funny educational comment",
  "motivational_comment": "one encouraging sentence",
  "topic_joke": "one topic-specific joke"
}}
"""
    response_text, error = safe_groq_generate(system_prompt, user_prompt, max_tokens=400)

    if error:
        logger.error(f"[AI RESPONSE] Quiz comment generation failed: {error}")
        return {
            "funny_comment": f"{topic} is starting to respect you.",
            "motivational_comment": "Keep practicing. Every attempt sharpens the idea.",
            "topic_joke": "Your neurons deserve a promotion.",
        }

    try:
        comments = json.loads(response_text.strip().replace("```json", "").replace("```", ""))
        return {
            "funny_comment": short_comment(comments.get("funny_comment")),
            "motivational_comment": short_comment(comments.get("motivational_comment")),
            "topic_joke": short_comment(comments.get("topic_joke")),
        }
    except (json.JSONDecodeError, TypeError) as exc:
        logger.error(f"[JSON PARSING] Failed parsing quiz comments: {exc}")
        return {
            "funny_comment": f"{topic} is beginning to fear your progress.",
            "motivational_comment": "Nice work. Keep the streak alive.",
            "topic_joke": "Your neurons just asked for a coffee break.",
        }


def short_comment(text):
    words = (text or "").replace("\n", " ").split()
    return " ".join(words[:20])
