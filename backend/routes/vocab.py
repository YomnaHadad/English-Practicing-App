from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import ai, learning, schemas
from ..db import get_db
from ..models import User, VocabItem
from ..security import get_current_user

router = APIRouter(tags=["vocab"])


def save_word(db: Session, user_id: int, word: str, sentence: str, meaning: str, movie_title: str) -> VocabItem:
    """Insert a word once per user; saving it again returns the existing entry."""
    word = word.strip().lower()
    item = db.scalar(select(VocabItem).where(VocabItem.user_id == user_id, VocabItem.word == word))
    if item is None:
        item = VocabItem(user_id=user_id, word=word, sentence=sentence, meaning=meaning, movie_title=movie_title)
        db.add(item)
        db.commit()
    return item


@router.post("/vocab", response_model=schemas.VocabOut)
def add(body: schemas.VocabIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return save_word(db, user.id, body.word, body.sentence, body.meaning, body.movie_title)


@router.get("/vocab", response_model=list[schemas.VocabOut])
def mine(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(VocabItem).where(VocabItem.user_id == user.id).order_by(VocabItem.id.desc())).all()


@router.post("/vocab/explain")
def explain(body: schemas.ExplainIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Explain a word in context and add it to the learner's review list."""
    result = ai.explain_word(body.word, body.sentence)
    meaning = f"{result['easy_word']} - {result['meaning_in_sentence']}"
    save_word(db, user.id, body.word, body.sentence, meaning, body.movie_title)
    return result


@router.get("/review/exercises")
def exercises(n: int = Query(5, ge=1, le=20), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return learning.build_review_exercises(db, user.id, n)


@router.post("/review/answer")
def answer(body: schemas.ReviewAnswer, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.get(VocabItem, body.vocab_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(404, "Word not found")
    correct = body.answer.strip().lower() == item.word
    if correct:
        item.correct += 1
    else:
        item.wrong += 1
    db.commit()
    return {"correct": correct, "answer": item.word}
