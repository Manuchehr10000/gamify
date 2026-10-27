from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DbSession

from app import config
from app.auth import current_guest, start_session
from app.db import get_db
from app.models import Guest, ScoreEvent

router = APIRouter()

ARRIVAL = "forum_arrival"
ARRIVAL_POINTS = 10


class Me(BaseModel):
    first_name: str
    consented: bool
    arrival_points: int


def _me(db: DbSession, guest: Guest) -> Me:
    points = db.scalar(select(ScoreEvent.points).where(
        ScoreEvent.guest_id == guest.id, ScoreEvent.reason == ARRIVAL))
    return Me(first_name=guest.first_name, consented=guest.consented_at is not None,
              arrival_points=points or 0)


@router.get("/b/{code}")
def open_badge(code: str, db: DbSession = Depends(get_db)) -> RedirectResponse:
    guest = db.scalar(select(Guest).where(Guest.code == code))
    if not guest:
        return RedirectResponse(f"{config.FRONTEND_URL}/app/welcome?error=badge", status_code=302)
    token = start_session(db, "guest", guest.id)
    # The fragment never reaches a server log; the app moves the token to its storage
    return RedirectResponse(f"{config.FRONTEND_URL}/app/welcome#token={token}", status_code=302)


@router.get("/api/me")
def me(guest: Guest = Depends(current_guest), db: DbSession = Depends(get_db)) -> Me:
    return _me(db, guest)


@router.post("/api/consent")
def consent(guest: Guest = Depends(current_guest), db: DbSession = Depends(get_db)) -> Me:
    if guest.consented_at is None:
        guest.consented_at = datetime.now(timezone.utc)
    db.execute(insert(ScoreEvent).values(guest_id=guest.id, reason=ARRIVAL, points=ARRIVAL_POINTS)
               .on_conflict_do_nothing(index_elements=["guest_id", "reason"]))
    db.commit()
    return _me(db, guest)
