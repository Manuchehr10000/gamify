from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.auth import current_guest
from app.db import get_db
from app.models import Guest, Partner, Stage, Submission, Task
from app import badges, ledger, levels, settings, stages
from app.stages import EVENT_TZ
from app.task_file import PACKAGES

router = APIRouter()

PACKAGE_ORDER = list(PACKAGES)


def task_reason(task_id: int) -> str:
    """The score_events reason for doing a task: one award per task per guest."""
    return f"task:{task_id}"


class StageOut(BaseModel):
    number: int
    name: str
    starts_at: datetime
    ends_at: datetime
    message: str


class TaskOut(BaseModel):
    id: int
    type: str
    text: str
    points: int
    coins: int
    partner_name: str
    window_end: datetime | None
    done: bool
    # qr, link, market, photo, text, photo_text, quiz or "" (not doable yet)
    method: str
    link: str
    # A quiz's countdown in seconds; None without one
    timer_seconds: int | None = None
    # A quiz with «Требует» whose hall QR the guest hasn't scanned yet
    locked: bool = False
    # A moderator's word on the guest's submission: retake (send again) · penalty (rejected, task closed) · ""
    review: str = ""


class Feed(BaseModel):
    points: int
    coins: int
    # The level the current points reach and the points to the next one (None at the top or with no levels)
    level: str
    to_next: int | None
    # Set once, when the guest has just climbed past the level they last saw: the full-screen moment
    new_level: str | None
    # Badges just earned and not seen before, in badges.BADGES order: a full-screen moment each, after the level's
    new_badges: list[str]
    # How many photos and texts the phone may keep waiting to send (the admin's setting)
    queue_size: int
    state: str
    stage_count: int
    starts_at: datetime | None
    stage: StageOut | None
    tasks: list[TaskOut]


def stage_out(s: Stage) -> StageOut:
    return StageOut(number=s.number, name=s.name, starts_at=s.starts_at.astimezone(EVENT_TZ),
                    ends_at=s.ends_at.astimezone(EVENT_TZ), message=s.message)


def _done(db: DbSession, guest: Guest) -> set[str]:
    return ledger.done(db, guest.id)


# What the guest is told about a decision; accepted and bonus need no word
REVIEWS = {"retake", "penalty"}


def _reviews(db: DbSession, guest: Guest) -> dict[int, str]:
    """Each task's latest submission status: a new submission after a retake replaces the old word."""
    rows = db.execute(select(Submission.task_id, Submission.status).where(Submission.guest_id == guest.id)
                      .order_by(Submission.id))
    return {task_id: status for task_id, status in rows}


def partners(db: DbSession) -> dict[int, Partner]:
    return {p.id: p for p in db.scalars(select(Partner))}


def _out(t: Task, done: set[str], reviews: dict[int, str] | None = None,
         by_id: dict[int, Partner] | None = None) -> TaskOut:
    review = (reviews or {}).get(t.id, "")
    partner = (by_id or {}).get(t.partner_id)
    return TaskOut(id=t.id, type=t.type, text=t.text, points=t.points, coins=t.coins,
                   partner_name=partner.name if partner else "", done=task_reason(t.id) in done, method=t.method, link=t.link,
                   window_end=t.window_end.astimezone(EVENT_TZ) if t.window_end else None,
                   timer_seconds=t.timer_seconds,
                   locked=t.requires_task_id is not None and task_reason(t.requires_task_id) not in done,
                   review=review if review in REVIEWS else "")


def _order(t: Task, by_id: dict[int, Partner]) -> tuple:
    # Tasks with a time window first (soonest to close on top), then partners by package, then the rest
    if t.window_end or t.window_start:
        return (0, t.window_end or t.window_start, t.position)
    partner = by_id.get(t.partner_id)
    if partner:
        rank = PACKAGE_ORDER.index(partner.package) if partner.package else len(PACKAGE_ORDER)
        return (1, rank, t.position)
    return (2, 0, t.position)


def _open(t: Task, at: datetime) -> bool:
    """A time-window task is on only while its window is open."""
    return (t.window_start is None or t.window_start <= at) and (t.window_end is None or at < t.window_end)


def totals(db: DbSession, guest: Guest) -> tuple[int, int]:
    """Points and coins: everything earned, less the coins spent in the market. The stored totals, read fresh."""
    row = db.execute(select(Guest.points, Guest.coins).where(Guest.id == guest.id)).one()
    return row[0], row[1]


@router.get("/api/feed")
def feed(guest: Guest = Depends(current_guest), db: DbSession = Depends(get_db)) -> Feed:
    # The quiz router builds on this one, so it is imported here, not at the top
    from app.routers.quiz import settle
    settle(db, guest.id)
    d = stages.day(db)
    points, coins = totals(db, guest)
    lv = levels.place(levels.load(db), points)
    mine = {"points": points, "coins": coins, "level": lv.name if lv else "", "to_next": lv.to_next if lv else None,
            "new_level": lv.name if levels.climbed(db, guest, lv) else None,
            "new_badges": badges.fresh(db, guest.id), "queue_size": settings.number(db, "upload_queue_size")}
    first = d.stages[0].starts_at.astimezone(EVENT_TZ) if d.stages else None
    if d.current is None:
        return Feed(**mine, state=d.state, stage_count=len(d.stages), starts_at=first, stage=None, tasks=[])
    t = stages.now()
    tasks = [x for x in db.scalars(select(Task).where(Task.active, Task.stage_id == d.current.id)) if _open(x, t)]
    done, reviews, by_id = _done(db, guest), _reviews(db, guest), partners(db)
    return Feed(**mine, state=d.state, stage_count=len(d.stages), starts_at=first, stage=stage_out(d.current), tasks=[_out(x, done, reviews, by_id) for x in sorted(tasks, key=lambda x: _order(x, by_id))])


@router.get("/api/tasks/{task_id}")
def task(task_id: int, guest: Guest = Depends(current_guest), db: DbSession = Depends(get_db)) -> TaskOut:
    t = db.get(Task, task_id)
    if t is None or not t.active:
        raise HTTPException(404, "task_not_found")
    return _out(t, _done(db, guest), _reviews(db, guest), partners(db))


class Award(BaseModel):
    # awarded: points added now · already: done before, nothing added · unavailable: not on at this moment
    result: str
    task: TaskOut


# Tasks done by sending something: a claim, then the photo (app.routers.claims)
SUBMIT_METHODS = {"photo", "text", "photo_text"}


def available(db: DbSession, t: Task) -> bool:
    """A task can be done now: its stage is the current one and its window is open."""
    d = stages.day(db)
    return t.active and d.current is not None and t.stage_id == d.current.id and _open(t, stages.now())


def _award(db: DbSession, guest: Guest, t: Task) -> Award:
    """Award a QR or link task once per guest, only while it is on: its stage is the current one and its window is
    open."""
    reason = task_reason(t.id)
    by_id = partners(db)
    if reason in _done(db, guest):
        return Award(result="already", task=_out(t, {reason}, _reviews(db, guest), by_id))
    if not available(db, t):
        return Award(result="unavailable", task=_out(t, set(), _reviews(db, guest), by_id))
    # Two phones of the same guest scanning at once still award once: the ledger checks under the guest's lock
    added = ledger.write(db, guest.id, reason, "task", t.points, t.coins) is not None
    db.commit()
    return Award(result="awarded" if added else "already", task=_out(t, {reason}, by_id=by_id))


class Scan(BaseModel):
    code: str


@router.post("/api/scan")
def scan(body: Scan, guest: Guest = Depends(current_guest), db: DbSession = Depends(get_db)) -> Award:
    t = db.scalar(select(Task).where(Task.qr_code == body.code.strip(), Task.method == "qr"))
    if t is None:
        raise HTTPException(404, "qr_not_found")
    return _award(db, guest, t)


@router.post("/api/tasks/{task_id}/complete")
def complete(task_id: int, guest: Guest = Depends(current_guest), db: DbSession = Depends(get_db)) -> Award:
    t = db.get(Task, task_id)
    if t is None or not t.active:
        raise HTTPException(404, "task_not_found")
    # Only link tasks are confirmed by the guest; QR tasks need the code from the venue
    if t.method != "link":
        raise HTTPException(400, "not_a_link_task")
    return _award(db, guest, t)
