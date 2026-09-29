"""Turn-based speaking tutor: record -> transcribe -> LLM reply -> (browser asks /tts).

The conversation lives in the browser and is sent with each turn, so the server
stays stateless until the session is finished and saved.
"""
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import ai, learning, schemas
from ..db import get_db
from ..models import TutorSession, User
from ..security import get_current_user
from .common import read_audio

router = APIRouter(prefix="/tutor", tags=["tutor"])

MAX_USER_TURNS = 15
MAX_HISTORY = 30


def clean_history(items) -> list[dict]:
    if not isinstance(items, list):
        raise HTTPException(400, "Bad transcript")
    return [
        {"role": m["role"], "text": m["text"][:1000]}
        for m in items[-MAX_HISTORY:]
        if isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("text"), str)
    ]


@router.post("/turn")
def turn(
    transcript: str = Form("[]"),
    topic: str = Form("", max_length=255),
    text: str = Form("", max_length=1000),
    audio: UploadFile | None = File(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """One conversational turn. With no audio and no text (empty history) the tutor opens the chat."""
    try:
        history = clean_history(json.loads(transcript))
    except ValueError:
        raise HTTPException(400, "Bad transcript")

    if audio is not None:
        text = ai.transcribe(read_audio(audio), audio.filename or "speech.webm")
        if not text:
            raise HTTPException(400, "Couldn't hear anything - please try again.")
    text = text.strip()

    if text:
        if sum(m["role"] == "user" for m in history) >= MAX_USER_TURNS:
            raise HTTPException(400, "Session limit reached - please finish the session.")
        history.append({"role": "user", "text": text})
    elif history:
        raise HTTPException(400, "Nothing to send")

    level = learning.current_level(db, user.id)
    weak_skill = learning.progress_summary(db, user.id)["weakest_skill"]
    reply = ai.tutor_reply(level, topic, history, learning.study_words(db, user.id), weak_skill)
    return {"user_text": text, "reply": reply, "level": level}


@router.post("/finish")
def finish(body: schemas.TutorFinishIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Analyse the conversation, save the session, and suggest what to do next."""
    history = clean_history(body.transcript)
    if not any(m["role"] == "user" for m in history):
        raise HTTPException(400, "Say something first, then finish the session.")

    level = learning.current_level(db, user.id)
    feedback = ai.tutor_feedback(level, body.topic, history)
    session = TutorSession(
        user_id=user.id,
        topic=body.topic,
        cefr_level=level,
        transcript=history,
        mistakes=feedback["mistakes"],
        summary=feedback["summary"],
    )
    db.add(session)
    db.commit()
    return {
        "session": schemas.TutorSessionOut.model_validate(session),
        "next_steps": learning.recommendations(learning.progress_summary(db, user.id)),
    }


@router.get("/sessions", response_model=list[schemas.TutorSessionOut])
def sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(TutorSession).where(TutorSession.user_id == user.id).order_by(TutorSession.id.desc()).limit(20)
    ).all()
