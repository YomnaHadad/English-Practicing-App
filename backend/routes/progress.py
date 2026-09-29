from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import learning
from ..db import get_db
from ..models import User
from ..security import get_current_user

router = APIRouter(tags=["progress"])


@router.get("/progress")
def progress(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return learning.progress_summary(db, user.id)


@router.get("/recommendations")
def recommendations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return learning.recommendations(learning.progress_summary(db, user.id))
