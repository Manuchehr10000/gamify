import hmac
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from app import config
from app.auth import start_session
from app.db import get_db

router = APIRouter(prefix="/api/staff")


class Login(BaseModel):
    role: Literal["desk", "admin"]
    secret: str


class Token(BaseModel):
    token: str


@router.post("/login")
def login(body: Login, db: DbSession = Depends(get_db)) -> Token:
    expected = config.DESK_PIN if body.role == "desk" else config.ADMIN_PASSWORD
    # An unset PIN or password locks the screen rather than opening it
    if not expected or not hmac.compare_digest(body.secret.encode(), expected.encode()):
        raise HTTPException(401, "wrong_secret")
    return Token(token=start_session(db, body.role))
