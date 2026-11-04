import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, File, HTTPException, Path, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app import badges, claims, ledger, photos, places, settings, stages
from app.auth import current_guest
from app.db import get_db
from app.models import Claim, Guest, Submission, Task
from app.places import SUBMIT_METHODS
from app.routers.feed import TaskOut, _done, _open, task_out, task_reason

# Sending a photo or text in two steps, so a phone that drops the network or is closed loses nothing: first a small
# claim with the phone's submission ID, which the server checks and times; then the files. Points are paid when the
# files arrive (a text-only claim pays at once), so a claim that lapses pays nothing
router = APIRouter()

TEXT_MAX = 500
# Made on the phone and repeated on every retry of that send; it becomes a path segment, so letters, digits, - and _
CLAIM_ID = r"^[A-Za-z0-9_-]{1,64}$"
PHOTO_METHODS = {"photo", "photo_text"}


class ClaimIn(BaseModel):
    id: str = Field(pattern=CLAIM_ID)
    # Checked below, after line breaks are counted as the guest's counter counts them
    text: str = Field(default="", max_length=4 * TEXT_MAX)


class ClaimOut(BaseModel):
    # claimed: place held, the photo comes next · awarded: points added · already: done before, nothing added ·
    # stage_closed: its stage isn't on · time_up: its window has closed · limit: all its places are taken
    result: str
    task: TaskOut


def _result(db: DbSession, guest: Guest, t: Task, result: str) -> ClaimOut:
    return ClaimOut(result=result, task=task_out(db, guest, t))


def _repeat(db: DbSession, guest: Guest, t: Task, c: Claim) -> ClaimOut:
    """A claim or files upload the server has seen before: the first result again, nothing paid twice."""
    if claims.expired(c):
        c.state = "lapsed"
        db.commit()
        raise HTTPException(410, "claim_lapsed")
    if c.state == "open":
        return _result(db, guest, t, "claimed")
    s = db.scalar(select(Submission).where(Submission.guest_id == guest.id, Submission.upload == c.id)
                  .order_by(Submission.id.desc()).limit(1))
    # A late retry of a send a moderator already sent back is not a new send, even with the same photo or text
    if s is not None and s.status == "retake":
        raise HTTPException(409, "sent_back")
    return _result(db, guest, t, "awarded" if s is not None else "already")


def _pay(db: DbSession, guest: Guest, t: Task, c: Claim, photo: bytes | None = None,
         thumb: bytes | None = None) -> ClaimOut:
    """Pay the task once, for the claim's stage and at its multiplier even if either has changed since, and keep what
    the guest sent."""
    added = ledger.write(db, guest.id, task_reason(t.id), "task", t.points, t.coins, multiplier=c.multiplier,
                         stage_id=c.stage_id) is not None
    if added:
        db.add(Submission(guest_id=guest.id, task_id=t.id, photo=photo, thumb=thumb, text=c.text, upload=c.id,
                          photo_token=secrets.token_urlsafe(24) if photo is not None else None))
        db.flush()
        badges.sync(db, [guest.id], actor=guest.id)
    c.state = "done"
    db.commit()
    return _result(db, guest, t, "awarded" if added else "already")


@router.post("/api/tasks/{task_id}/claim")
def claim(task_id: int, body: ClaimIn, guest: Guest = Depends(current_guest),
          db: DbSession = Depends(get_db)) -> ClaimOut:
    t = db.get(Task, task_id)
    if t is None:
        raise HTTPException(404, "task_not_found")
    if t.method not in SUBMIT_METHODS:
        raise HTTPException(400, "wrong_method")
    # The guest's claims go one after another: a retry racing its first try, or a second phone, finds the first
    ledger.lock(db, guest.id)
    c = db.get(Claim, body.id)
    if c is not None:
        if c.guest_id != guest.id or c.task_id != t.id:
            raise HTTPException(409, "claim_taken")
        return _repeat(db, guest, t, c)
    # Browsers may send line breaks as \r\n; the guest's counter saw one character each
    text = body.text.replace("\r\n", "\n").strip() if t.method != "photo" else ""
    if len(text) > TEXT_MAX:
        raise HTTPException(400, "text_too_long")
    if t.method != "photo" and not text:
        raise HTTPException(400, "text_required")
    if task_reason(t.id) in _done(db, guest):
        return _result(db, guest, t, "already")
    # The claim's server time sets the stage
    d, now = stages.day(db), stages.now()
    if not t.active or d.current is None or t.stage_id != d.current.id:
        return _result(db, guest, t, "stage_closed")
    if not _open(t, now):
        return _result(db, guest, t, "time_up" if t.window_end and now >= t.window_end else "stage_closed")
    # One place per task: a claim from another phone still waiting for its photo holds it, unless it has lapsed
    held = db.scalar(select(Claim).where(Claim.guest_id == guest.id, Claim.task_id == t.id, Claim.state == "open"))
    if held is not None:
        if not claims.expired(held):
            raise HTTPException(409, "claim_open")
        held.state = "lapsed"
    # The place is checked and taken in one locked step: of two guests after the last place, one gets it. A guest
    # sent back for a retake still holds theirs, so their claim passes even when the task is full
    if not places.take(db, guest.id, t):
        db.rollback()
        return _result(db, guest, t, "limit")
    c = Claim(id=body.id, guest_id=guest.id, task_id=t.id, text=text, created_at=now, stage_id=d.current.id,
              multiplier=d.current.multiplier, expires_at=now + timedelta(minutes=settings.number(db, "claim_minutes")),
              state="open")
    db.add(c)
    # A text-only task has no files step: it counts now
    if t.method not in PHOTO_METHODS:
        return _pay(db, guest, t, c)
    db.commit()
    return _result(db, guest, t, "claimed")


def _read(upload: UploadFile, max_bytes: int, max_side: int, too_large: str) -> bytes:
    """The upload as a JPEG (checked by its content) within the limits, its metadata segments dropped."""
    data = upload.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(413, too_large)
    size = photos.jpeg_size(data)
    if size is None:
        raise HTTPException(400, "not_a_jpeg")
    if max(size) > max_side:
        raise HTTPException(400, too_large)
    # The phone's redraw already drops GPS and camera data; this keeps an old cached app version from storing it
    return photos.strip_metadata(data)


@router.post("/api/claims/{claim_id}/files")
def files(claim_id: str = Path(pattern=CLAIM_ID), photo: UploadFile = File(), thumb: UploadFile = File(),
          guest: Guest = Depends(current_guest), db: DbSession = Depends(get_db)) -> ClaimOut:
    # A plain def runs in the thread pool, so reading the spooled upload and the database don't stall other guests
    photo_data = _read(photo, photos.MAX_BYTES, photos.MAX_SIDE, "photo_too_large")
    thumb_data = _read(thumb, photos.THUMB_MAX_BYTES, photos.THUMB_SIDE, "thumb_too_large")
    ledger.lock(db, guest.id)
    c = db.get(Claim, claim_id)
    # Another guest's claim ID is unknown here, as if it didn't exist
    if c is None or c.guest_id != guest.id:
        raise HTTPException(404, "claim_not_found")
    t = db.get(Task, c.task_id)
    if t.method not in PHOTO_METHODS:
        raise HTTPException(400, "wrong_method")
    if c.state != "open" or claims.expired(c):
        return _repeat(db, guest, t, c)
    return _pay(db, guest, t, c, photo_data, thumb_data)
