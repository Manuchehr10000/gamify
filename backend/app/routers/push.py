"""A phone's push subscription, its arrival reports, and the admin's «send now». The schedule itself is the push list
in /admin/settings (app.admin_lists), and the switch and texts are settings."""
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DbSession

from app import changes, push, stages
from app.auth import current_guest, require_role
from app.db import get_db
from app.models import Guest, PushMessage, PushSubscription, Staff

router = APIRouter(prefix="/api")
ADMIN = require_role("admin")


class Keys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=200)
    auth: str = Field(min_length=1, max_length=100)


class Subscription(BaseModel):
    # As the browser's PushSubscription.toJSON() gives it
    endpoint: str = Field(min_length=1, max_length=1000)
    keys: Keys


@router.post("/push/subscribe")
def subscribe(body: Subscription, guest: Guest = Depends(current_guest), db: DbSession = Depends(get_db)) -> dict:
    """The phone said yes. A browser sending the same address again (a new login on it) moves it to this guest."""
    if not push.ready():
        raise HTTPException(503, "push_unavailable")
    if not body.endpoint.startswith("https://"):
        raise HTTPException(400, "bad_endpoint")
    stmt = insert(PushSubscription).values(key=secrets.token_urlsafe(16), guest_id=guest.id, endpoint=body.endpoint,
                                           p256dh=body.keys.p256dh, auth=body.keys.auth)
    db.execute(stmt.on_conflict_do_update(index_elements=["endpoint"], set_={
        "guest_id": stmt.excluded.guest_id, "p256dh": stmt.excluded.p256dh, "auth": stmt.excluded.auth,
        "active": True}))
    db.commit()
    return {"subscribed": True}


class Received(BaseModel):
    # The subscription's key from the push itself
    subscription: str = Field(min_length=1, max_length=32)


@router.post("/push/{push_id}/received")
def received(push_id: int, body: Received, db: DbSession = Depends(get_db)) -> dict:
    """The phone's service worker reports the push arrived. No login: a service worker can't read the app's stored
    login, so the push's own id and subscription key are the proof; each subscription counts once per push."""
    counted = push.receive(db, push_id, body.subscription)
    db.commit()
    return {"counted": counted}


@router.post("/admin/push/{push_id}/send")
def send_now(push_id: int, admin: Staff = Depends(ADMIN), db: DbSession = Depends(get_db)) -> dict:
    """Send any push now, whatever its state or time. Refused while pushes are switched off. A push that already went
    out to open apps and /hall goes again as a copy with its own id, so its banner shows again there."""
    if not push.ready():
        raise HTTPException(503, "push_unavailable")
    if not push.enabled(db):
        raise HTTPException(409, "push_off")
    m = db.get(PushMessage, push_id, with_for_update=True, populate_existing=True)
    if m is None:
        raise HTTPException(404, "not_found")
    old = m.state
    if m.shown_at is not None:
        m = PushMessage(kind=m.kind, task_id=m.task_id, at=stages.now(), title=m.title, text=m.text,
                        text_tg=m.text_tg, title_tg=m.title_tg, text_edited=True)
        db.add(m)
        db.flush()
        old = ""
    changes.record(db, admin, "push", m.id, changes.label(db, m), "state", old, "sent")
    push.send(db, m)
    db.refresh(m)
    return {"id": m.id, "state": m.state, "sends": m.sends, "failures": m.failures}
