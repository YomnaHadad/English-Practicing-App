from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import assessment, schemas
from ..db import get_db
from ..models import Assessment, User
from ..security import get_current_user

router = APIRouter(prefix="/assessments", tags=["assessment"])


@router.get("/questions")
def questions(user: User = Depends(get_current_user)):
    return assessment.public_questions()


@router.post("/", response_model=schemas.AssessmentOut, status_code=201)
def submit(body: schemas.AssessmentSubmit, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = Assessment(user_id=user.id, **assessment.score(body.answers))
    db.add(row)
    db.commit()
    return row


@router.get("/me", response_model=list[schemas.AssessmentOut])
def mine(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(Assessment)
        .where(Assessment.user_id == user.id)
        .order_by(Assessment.created_at.desc(), Assessment.id.desc())
    ).all()
