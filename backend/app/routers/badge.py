from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app import config, ledger, push, settings
from app.auth import current_guest, start_session
from app.db import get_db
from app.models import Guest, ScoreEvent

router = APIRouter()

ARRIVAL = "forum_arrival"


class Me(BaseModel):
    first_name: str
    consented: bool
    arrival_points: int
    # The app's web push key; empty when pushes aren't set up, and then the app never asks
    vapid_public_key: str


def _me(db: DbSession, guest: Guest) -> Me:
    points = db.scalar(select(ScoreEvent.points).where(
        ScoreEvent.guest_id == guest.id, ScoreEvent.reason == ARRIVAL))
    return Me(first_name=guest.first_name, consented=guest.consented_at is not None,
              arrival_points=points or 0, vapid_public_key=config.VAPID_PUBLIC_KEY if push.ready() else "")


@router.get("/b/{code}")
def open_badge(code: str, db: DbSession = Depends(get_db)) -> RedirectResponse:
    guest = db.scalar(select(Guest).where(Guest.code == code))
    if not guest:
        return RedirectResponse(f"{config.FRONTEND_URL}/app/welcome?error=badge", status_code=302)
    token = start_session(db, guest_id=guest.id)
    # The fragment never reaches a server log; the app moves the token to its storage
    return RedirectResponse(f"{config.FRONTEND_URL}/app/welcome#token={token}", status_code=302)


@router.get("/api/me")
def me(guest: Guest = Depends(current_guest), db: DbSession = Depends(get_db)) -> Me:
    return _me(db, guest)


@router.post("/api/consent")
def consent(guest: Guest = Depends(current_guest), db: DbSession = Depends(get_db)) -> Me:
    if guest.consented_at is None:
        guest.consented_at = datetime.now(timezone.utc)
    ledger.write(db, guest.id, ARRIVAL, "arrival", settings.number(db, "arrival_points"), 0)
    db.commit()
    return _me(db, guest)
