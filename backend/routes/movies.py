from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import ai, pronunciation, schemas, subtitles, tts
from ..db import get_db
from ..models import CompletedChapter, PronunciationAttempt, SubtitleCache, User
from ..security import get_current_user
from .common import read_audio

router = APIRouter(tags=["movies"])


@router.get("/movies/search")
def search(q: str = Query(min_length=2, max_length=100), user: User = Depends(get_current_user)):
    return subtitles.search_movies(q)


@router.get("/movies/completed")
def completed(movie_title: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Chapter indexes the learner has finished for a movie."""
    return db.scalars(
        select(CompletedChapter.chapter_idx).where(
            CompletedChapter.user_id == user.id, CompletedChapter.movie_title == movie_title
        )
    ).all()


@router.get("/movies/{file_id}")
def chapters(file_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(SubtitleCache, file_id)
    if row is None:
        row = SubtitleCache(file_id=file_id, lines=subtitles.download_subtitle(file_id))
        db.add(row)
        try:
            db.commit()
        except IntegrityError:  # another request cached it first
            db.rollback()
    return {"chapters": subtitles.group_into_chapters(row.lines)}


@router.post("/chapters/complete")
def complete_chapter(body: schemas.ChapterIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Idempotent: completing the same chapter twice is fine."""
    db.add(CompletedChapter(user_id=user.id, **body.model_dump()))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    return {"saved": True}


@router.post("/tts")
async def speak(body: schemas.TtsIn, user: User = Depends(get_current_user)):
    return Response(await tts.synthesize(body.text, body.accent), media_type="audio/mpeg")


@router.post("/pronunciation")
def check_pronunciation(
    audio: UploadFile = File(...),
    target: str = Form(min_length=1, max_length=500),
    movie_title: str = Form("", max_length=255),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    transcript = ai.transcribe(read_audio(audio), audio.filename or "speech.webm")
    result = pronunciation.score_pronunciation(target, transcript)
    db.add(
        PronunciationAttempt(
            user_id=user.id,
            movie_title=movie_title,
            line_text=target,
            score=result["score"],
            unclear_words=result["unclear_words"],
        )
    )
    db.commit()
    return result
