from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..db import get_db
from ..models import User
from ..security import create_token, get_current_user, hash_password, verify_password

router = APIRouter(tags=["auth"])


@router.post("/auth/register", response_model=schemas.UserOut, status_code=201)
def register(body: schemas.UserCreate, db: Session = Depends(get_db)):
    taken = db.scalar(select(User).where((User.username == body.username) | (User.email == body.email)))
    if taken:
        raise HTTPException(409, "Username or email already registered")
    user = User(
        username=body.username,
        email=body.email,
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    return user


@router.post("/auth/token", response_model=schemas.Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == form.username))
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(401, "Incorrect username or password")
    return {"access_token": create_token(user.id)}


@router.get("/users/me", response_model=schemas.UserOut)
def me(user: User = Depends(get_current_user)):
    return user
