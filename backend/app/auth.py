import hashlib
import secrets
from collections.abc import Callable

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.db import get_db
from app.models import Guest, Session, Staff


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(db: DbSession, account: Staff | None = None, guest_id: int | None = None) -> str:
    """A guest's session (guest_id) or a staff account's, which records who is acting."""
    token = secrets.token_urlsafe(32)
    if account is None:
        db.add(Session(token_hash=_hash(token), role="guest", guest_id=guest_id))
    else:
        db.add(Session(token_hash=_hash(token), role=account.role, staff_id=account.id, staff_name=account.name))
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


def _staff(db: DbSession, authorization: str | None, roles: tuple[str, ...]) -> Staff:
    """The staff account acting, checked on the server against the roles the endpoint allows."""
    s = _session(db, authorization)
    account = db.get(Staff, s.staff_id) if s and s.staff_id is not None else None
    if account is None or account.role not in roles:
        raise HTTPException(401, "not_logged_in")
    return account


def require_role(*roles: str) -> Callable[..., Staff]:
    """A dependency that lets in only the given roles, e.g. require_role("admin", "moderator")."""
    def check(authorization: str | None = Header(default=None), db: DbSession = Depends(get_db)) -> Staff:
        return _staff(db, authorization, roles)

    return check


def current_moderator(authorization: str | None = Header(default=None), db: DbSession = Depends(get_db)) -> str:
    """The logged-in moderator's name."""
    return _staff(db, authorization, ("moderator",)).name
