"""Learner profile logic: progress summary, recommendations, review exercises.

Everything here is plain rules over the user's stored activity - no ML.
"""
import random
import re
from collections import Counter
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .assessment import SKILLS
from .models import (
    Assessment,
    CompletedChapter,
    PronunciationAttempt,
    TutorSession,
    VocabItem,
    utcnow,
)

PRONUNCIATION_TARGET = 70
REASSESS_AFTER_DAYS = 30
TUTOR_EVERY_DAYS = 7


# ---------- review exercises ----------

def build_review_exercises(db: Session, user_id: int, n: int = 5) -> list[dict]:
    """Cloze questions from saved words. Weakest words come first."""
    items = db.scalars(select(VocabItem).where(VocabItem.user_id == user_id)).all()
    if len(items) < 2:  # need distractors
        return []

    def has_word(i: VocabItem) -> bool:
        return re.search(rf"\b{re.escape(i.word)}\b", i.sentence, re.I) is not None

    usable = sorted(
        (i for i in items if has_word(i)),
        key=lambda i: (i.correct - i.wrong, random.random()),
    )
    exercises = []
    for item in usable[:n]:
        others = [i.word for i in items if i.id != item.id]
        options = random.sample(others, k=min(3, len(others))) + [item.word]
        random.shuffle(options)
        exercises.append(
            {
                "vocab_id": item.id,
                "sentence": re.sub(rf"\b{re.escape(item.word)}\b", "_____", item.sentence, count=1, flags=re.I),
                "options": options,
            }
        )
    return exercises


# ---------- profile helpers (used by the tutor) ----------

def current_level(db: Session, user_id: int) -> str:
    """Latest assessed CEFR level; A2 until the learner has taken the test."""
    level = db.scalar(
        select(Assessment.cefr_level)
        .where(Assessment.user_id == user_id)
        .order_by(Assessment.created_at.desc(), Assessment.id.desc())
    )
    return level or "A2"


def study_words(db: Session, user_id: int, n: int = 4) -> list[str]:
    """Saved words the learner knows least well - the tutor works them into conversation."""
    items = db.scalars(select(VocabItem).where(VocabItem.user_id == user_id)).all()
    items.sort(key=lambda i: (i.correct - i.wrong, -i.id))
    return [i.word for i in items[:n]]


def _weak_areas(s: dict) -> list[str]:
    areas = []
    weak = s["weakest_skill"]
    if weak and s["latest_skill_scores"][weak] < 70:
        areas.append(f"{weak.capitalize()} (placement score {s['latest_skill_scores'][weak]}/100)")
    pron = s["pronunciation"]
    if pron["attempts"] >= 3 and pron["average_recent"] < PRONUNCIATION_TARGET:
        areas.append(f"Pronunciation (recent average {pron['average_recent']}/100)")
    acc = s["vocab"]["review_accuracy"]
    if acc is not None and acc < 60:
        areas.append(f"Vocabulary retention ({acc}% correct in reviews)")
    if s["tutor"]["recent_mistakes"]:
        areas.append("Mistakes from recent speaking sessions (see below)")
    return areas


# ---------- progress ----------

def progress_summary(db: Session, user_id: int) -> dict:
    assessments = db.scalars(
        select(Assessment)
        .where(Assessment.user_id == user_id)
        .order_by(Assessment.created_at, Assessment.id)
    ).all()
    latest = assessments[-1] if assessments else None
    previous = assessments[-2] if len(assessments) > 1 else None

    weakest_skill = None
    if latest:
        weakest_skill = min(SKILLS, key=lambda s: getattr(latest, f"{s}_score"))

    vocab = db.scalars(select(VocabItem).where(VocabItem.user_id == user_id)).all()
    reviewed = sum(v.correct + v.wrong for v in vocab)
    answered_right = sum(v.correct for v in vocab)

    attempts = db.scalars(
        select(PronunciationAttempt)
        .where(PronunciationAttempt.user_id == user_id)
        .order_by(PronunciationAttempt.id.desc())
        .limit(50)
    ).all()
    recent_scores = [a.score for a in attempts[:20]]
    weak_words = Counter(w for a in attempts for w in a.unclear_words)

    chapters = db.scalars(select(CompletedChapter).where(CompletedChapter.user_id == user_id)).all()
    last_session = db.scalar(
        select(func.max(TutorSession.created_at)).where(TutorSession.user_id == user_id)
    )
    recent_sessions = db.scalars(
        select(TutorSession).where(TutorSession.user_id == user_id).order_by(TutorSession.id.desc()).limit(3)
    ).all()
    session_count = db.scalar(
        select(func.count()).select_from(TutorSession).where(TutorSession.user_id == user_id)
    )

    summary = {
        "cefr_level": latest.cefr_level if latest else None,
        "previous_cefr_level": previous.cefr_level if previous else None,
        "latest_assessment_at": latest.created_at if latest else None,
        "weakest_skill": weakest_skill,
        "latest_skill_scores": (
            {s: getattr(latest, f"{s}_score") for s in SKILLS} if latest else None
        ),
        "assessments": [
            {
                "cefr_level": a.cefr_level,
                "created_at": a.created_at,
                **{f"{s}_score": getattr(a, f"{s}_score") for s in SKILLS},
            }
            for a in assessments
        ],
        "vocab": {
            "total": len(vocab),
            "mastered": sum(1 for v in vocab if v.correct >= 3 and v.correct > v.wrong),
            "due": sum(1 for v in vocab if v.wrong > v.correct or v.correct + v.wrong == 0),
            "review_accuracy": round(100 * answered_right / reviewed) if reviewed else None,
        },
        "pronunciation": {
            "attempts": len(attempts),
            "average_recent": round(sum(recent_scores) / len(recent_scores)) if recent_scores else None,
            "weak_words": [w for w, _ in weak_words.most_common(5)],
        },
        "movies": {
            "chapters_completed": len(chapters),
            "movies": sorted({c.movie_title for c in chapters}),
        },
        "tutor": {
            "sessions": session_count,
            "last_session": last_session,
            "recent_mistakes": [m for t in recent_sessions for m in t.mistakes][:5],
        },
    }
    summary["weak_areas"] = _weak_areas(summary)
    return summary


# ---------- recommendations ----------

def _days_since(when: datetime | None, now: datetime) -> float | None:
    return None if when is None else (now - when).total_seconds() / 86400


def _rec(action: str, title: str, reason: str) -> dict:
    return {"action": action, "title": title, "reason": reason}


_WEAK_SKILL_ADVICE = {
    "vocab": ("review", "Review your saved words", "Vocabulary was your lowest placement-test skill."),
    "grammar": ("tutor", "Talk with the AI tutor", "Grammar was your lowest placement-test skill; conversation practice with corrections helps."),
    "listening": ("shadowing", "Shadow more movie dialogue", "Listening was your lowest placement-test skill."),
    "reading": ("shadowing", "Read along with movie dialogue", "Reading was your lowest placement-test skill."),
}


def recommendations(summary: dict, now: datetime | None = None, limit: int = 3) -> list[dict]:
    """Ordered next-step suggestions from a progress summary."""
    now = now or utcnow()
    if summary["cefr_level"] is None:
        return [_rec("assessment", "Take the placement test", "We need your level to tailor activities.")]

    recs = []
    age = _days_since(summary["latest_assessment_at"], now)
    if age is not None and age >= REASSESS_AFTER_DAYS:
        recs.append(_rec("assessment", "Retake the placement test", f"Your last test was {int(age)} days ago."))

    if summary["vocab"]["due"] >= 5:
        recs.append(_rec("review", "Review your vocabulary", f"{summary['vocab']['due']} saved words need practice."))

    pron = summary["pronunciation"]
    if pron["attempts"] >= 3 and pron["average_recent"] < PRONUNCIATION_TARGET:
        words = ", ".join(pron["weak_words"][:3])
        reason = f"Recent pronunciation average is {pron['average_recent']}/100."
        if words:
            reason += f" Trouble words: {words}."
        recs.append(_rec("shadowing", "Practise pronunciation", reason))

    tutor_age = _days_since(summary["tutor"]["last_session"], now)
    if tutor_age is None or tutor_age >= TUTOR_EVERY_DAYS:
        recs.append(_rec("tutor", "Have a speaking session with the AI tutor", "Regular conversation practice builds fluency."))

    weak = summary["weakest_skill"]
    if weak and summary["latest_skill_scores"][weak] < 60:
        action, title, reason = _WEAK_SKILL_ADVICE[weak]
        if all(r["action"] != action for r in recs):
            recs.append(_rec(action, title, reason))

    if not recs:
        recs.append(_rec("shadowing", "Continue with a movie", "You're on track - keep shadowing."))
    return recs[:limit]
