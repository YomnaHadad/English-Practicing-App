"""Placement test: a fixed question bank, scored on the server.

Scoring is deliberately simple and explainable:
  * Each level (A1..C2) has 4 questions (one per skill).
  * The CEFR estimate is the highest level reached by passing levels in order,
    where "passing" means >= 50% correct; the first failed level stops the walk.
  * Skill scores (0-100) weight harder questions more (A1=1 ... C2=6).
This is a quick placement estimate, not a certified exam.
"""
import json
from pathlib import Path

LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
SKILLS = ["vocab", "grammar", "reading", "listening"]
PASS_RATE = 0.5

QUESTIONS = json.loads((Path(__file__).parent / "questions.json").read_text(encoding="utf-8"))


def public_questions() -> list[dict]:
    """Questions without the answer key."""
    return [{k: v for k, v in q.items() if k != "answer"} for q in QUESTIONS]


def score(answers: dict[str, int]) -> dict:
    """Grade {question_id: chosen_option_index}. Unanswered counts as wrong."""
    right = dict.fromkeys(LEVELS, 0)
    total = dict.fromkeys(LEVELS, 0)
    points = dict.fromkeys(SKILLS, 0)
    max_points = dict.fromkeys(SKILLS, 0)

    for q in QUESTIONS:
        weight = LEVELS.index(q["level"]) + 1
        total[q["level"]] += 1
        max_points[q["skill"]] += weight
        if answers.get(q["id"]) == q["answer"]:
            right[q["level"]] += 1
            points[q["skill"]] += weight

    cefr = "A1"
    for level in LEVELS:
        if right[level] / total[level] >= PASS_RATE:
            cefr = level
        else:
            break

    return {
        "cefr_level": cefr,
        **{f"{s}_score": round(100 * points[s] / max_points[s]) for s in SKILLS},
    }
