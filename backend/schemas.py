"""Request/response models."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=255)
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(default="", max_length=100)


class UserOut(ORM):
    id: int
    username: str
    email: str
    full_name: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AssessmentSubmit(BaseModel):
    answers: dict[str, int]  # question_id -> chosen option index


class AssessmentOut(ORM):
    id: int
    cefr_level: str
    vocab_score: int
    grammar_score: int
    reading_score: int
    listening_score: int
    created_at: datetime


class VocabIn(BaseModel):
    word: str = Field(min_length=1, max_length=100)
    sentence: str = Field(min_length=1)
    meaning: str = ""
    movie_title: str = ""


class VocabOut(ORM):
    id: int
    word: str
    sentence: str
    meaning: str
    movie_title: str
    correct: int
    wrong: int


class ReviewAnswer(BaseModel):
    vocab_id: int
    answer: str


class ExplainIn(BaseModel):
    word: str = Field(min_length=1, max_length=50)
    sentence: str = Field(min_length=1, max_length=500)
    movie_title: str = Field(default="", max_length=255)


class TtsIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    accent: str = "us"


class ChapterIn(BaseModel):
    movie_title: str = Field(min_length=1)
    chapter_idx: int = Field(ge=0)


class TutorSessionOut(ORM):
    id: int
    topic: str
    cefr_level: str
    transcript: list[dict]
    mistakes: list[dict]
    summary: str
    created_at: datetime


class TutorFinishIn(BaseModel):
    topic: str = Field(default="", max_length=255)
    transcript: list[dict]
