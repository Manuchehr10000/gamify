import hashlib
import secrets
from collections.abc import Callable

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.db import get_db
from app.models import Guest, Session


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(db: DbSession, role: str, guest_id: int | None = None) -> str:
    token = secrets.token_urlsafe(32)
    db.add(Session(token_hash=_hash(token), role=role, guest_id=guest_id))
    db.commit()
    return token


def _session(db: DbSession, authorization: str | None) -> Session | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return db.scalar(select(Session).where(Session.token_hash == _hash(authorization[7:])))


def current_guest(
    authorization: str | None = Header(default=None), db: DbSession = Depends(get_db)
) -> Guest:
    s = _session(db, authorization)
    if not s or s.role != "guest" or s.guest_id is None:
        raise HTTPException(401, "not_logged_in")
    return db.get(Guest, s.guest_id)


def require_role(role: str) -> Callable[..., None]:
    def check(authorization: str | None = Header(default=None), db: DbSession = Depends(get_db)) -> None:
        s = _session(db, authorization)
        if not s or s.role != role:
            raise HTTPException(401, "not_logged_in")

    return check
