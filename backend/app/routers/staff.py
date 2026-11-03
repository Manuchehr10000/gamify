from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from app import accounts
from app.auth import start_session
from app.db import get_db

router = APIRouter(prefix="/api/staff")


class Login(BaseModel):
    role: Literal["desk", "admin", "stand"]
    secret: str


class Token(BaseModel):
    token: str


@router.post("/login")
def login(body: Login, db: DbSession = Depends(get_db)) -> Token:
    # The PIN or password alone says which account it is; with no account of the role the screen stays locked
    account = accounts.find(db, body.role, body.secret)
    if account is None:
        raise HTTPException(401, "wrong_secret")
    return Token(token=start_session(db, account))
