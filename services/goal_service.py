from services.roadmap_service import get_or_create_roadmap
from utils.topic_validator import normalize_topic_name


GOAL_TEMPLATES = {
    "learn python": [
        "Programming Basics",
        "Python Syntax",
        "Control Flow",
        "Functions",
        "Data Structures",
        "Object Oriented Programming",
        "File Handling",
        "Error Handling",
        "Python Projects",
    ],
    "backend development": [
        "Programming Basics",
        "HTTP",
        "Databases",
        "SQL",
        "APIs",
        "Authentication",
        "Backend Frameworks",
        "Deployment",
        "System Design Basics",
    ],
    "data science": [
        "Python Programming",
        "Statistics",
        "Data Cleaning",
        "Pandas",
        "Data Visualization",
        "SQL",
        "Machine Learning",
        "Model Evaluation",
    ],
    "machine learning": [
        "Python Programming",
        "Linear Algebra",
        "Statistics",
        "Data Preprocessing",
        "Supervised Learning",
        "Unsupervised Learning",
        "Model Evaluation",
        "Neural Network",
    ],
    "upsc": [
        "Indian Polity",
        "Modern History",
        "Geography",
        "Economy",
        "Environment",
        "Current Affairs",
        "Ethics",
        "Answer Writing",
    ],
    "gate": [
        "Engineering Mathematics",
        "Programming",
        "Data Structures",
        "Algorithms",
        "Computer Networks",
        "Operating System",
        "Database Management System",
        "Previous Year Questions",
    ],
    "cat": [
        "Arithmetic",
        "Algebra",
        "Geometry",
        "Reading Comprehension",
        "Verbal Ability",
        "Logical Reasoning",
        "Data Interpretation",
        "Mock Test Strategy",
    ],
    "learn spanish": [
        "Spanish Pronunciation",
        "Basic Vocabulary",
        "Present Tense",
        "Common Phrases",
        "Grammar Basics",
        "Listening Practice",
        "Speaking Practice",
        "Reading Practice",
    ],
    "cybersecurity": [
        "Computer Networks",
        "Operating System",
        "Linux Basics",
        "Web Security",
        "Cryptography",
        "Threat Modeling",
        "Vulnerability Assessment",
        "Incident Response",
    ],
}


def build_goal_roadmap(goal_title):
    clean_goal = normalize_topic_name(goal_title)
    topics = GOAL_TEMPLATES.get(clean_goal.lower())

    if not topics:
        roadmap = get_or_create_roadmap(clean_goal)
        topics = []
        topics.extend(item["topic"] for item in roadmap.get("prerequisites", []))
        topics.append(roadmap["topic"])
        topics.extend(item["topic"] for item in roadmap.get("next_topics", []))

    cleaned_topics = []
    for topic in topics:
        clean_topic = normalize_topic_name(topic)
        if clean_topic and clean_topic not in cleaned_topics:
            cleaned_topics.append(clean_topic)

    roadmap_items = []
    for index, topic in enumerate(cleaned_topics):
        prerequisites = cleaned_topics[:index][-2:]
        roadmap_items.append(
            {
                "topic": topic,
                "order": index + 1,
                "prerequisites": prerequisites,
                "why": goal_topic_reason(topic, clean_goal, index),
            }
        )

    return {
        "goal": clean_goal,
        "topics": roadmap_items,
    }


def goal_topic_reason(topic, goal_title, index):
    if index == 0:
        return f"{topic} gives you the starting foundation for {goal_title}."
    return f"{topic} builds on earlier topics and moves you closer to {goal_title}."
