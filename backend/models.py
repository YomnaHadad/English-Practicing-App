"""All tables. Timestamps are naive UTC."""
from datetime import datetime, timezone

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    full_name: Mapped[str] = mapped_column(String(100), default="")
    hashed_password: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Assessment(Base):
    __tablename__ = "assessments"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    cefr_level: Mapped[str] = mapped_column(String(2))
    vocab_score: Mapped[int]
    grammar_score: Mapped[int]
    reading_score: Mapped[int]
    listening_score: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class VocabItem(Base):
    """A word the learner looked up. `correct`/`wrong` count review answers."""
    __tablename__ = "vocab_items"
    __table_args__ = (UniqueConstraint("user_id", "word"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    word: Mapped[str] = mapped_column(String(100))
    sentence: Mapped[str] = mapped_column(Text)
    meaning: Mapped[str] = mapped_column(Text, default="")
    movie_title: Mapped[str] = mapped_column(String(255), default="")
    correct: Mapped[int] = mapped_column(default=0)
    wrong: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class PronunciationAttempt(Base):
    __tablename__ = "pronunciation_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    movie_title: Mapped[str] = mapped_column(String(255), default="")
    line_text: Mapped[str] = mapped_column(Text)
    score: Mapped[int]
    unclear_words: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class CompletedChapter(Base):
    __tablename__ = "completed_chapters"
    __table_args__ = (UniqueConstraint("user_id", "movie_title", "chapter_idx"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    movie_title: Mapped[str] = mapped_column(String(255))
    chapter_idx: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class TutorSession(Base):
    __tablename__ = "tutor_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    topic: Mapped[str] = mapped_column(String(255), default="")
    cefr_level: Mapped[str] = mapped_column(String(2), default="")
    transcript: Mapped[list] = mapped_column(JSON, default=list)  # [{role, text}]
    mistakes: Mapped[list] = mapped_column(JSON, default=list)  # [{said, correction, explanation}]
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class SubtitleCache(Base):
    """Parsed subtitles by OpenSubtitles file_id (their download quota is small)."""
    __tablename__ = "subtitle_cache"
    file_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    lines: Mapped[list] = mapped_column(JSON)
