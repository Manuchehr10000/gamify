from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DbSession

from app.auth import current_guest
from app.db import get_db
from app.models import Guest, ScoreEvent, Stage, Task
from app import stages
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
    # qr, link or "" (not doable yet)
    method: str
    link: str


class Feed(BaseModel):
    points: int
    coins: int
    state: str
    stage_count: int
    starts_at: datetime | None
    stage: StageOut | None
    tasks: list[TaskOut]


def stage_out(s: Stage) -> StageOut:
    return StageOut(number=s.number, name=s.name, starts_at=s.starts_at.astimezone(EVENT_TZ),
                    ends_at=s.ends_at.astimezone(EVENT_TZ), message=s.message)


def _done(db: DbSession, guest: Guest) -> set[str]:
    return set(db.scalars(select(ScoreEvent.reason).where(ScoreEvent.guest_id == guest.id)))


def _out(t: Task, done: set[str]) -> TaskOut:
    return TaskOut(id=t.id, type=t.type, text=t.text, points=t.points, coins=t.coins,
                   partner_name=t.partner_name, done=task_reason(t.id) in done, method=t.method, link=t.link,
                   window_end=t.window_end.astimezone(EVENT_TZ) if t.window_end else None)


def _order(t: Task) -> tuple:
    # Tasks with a time window first (soonest to close on top), then partners by package, then the rest
    if t.window_end or t.window_start:
        return (0, t.window_end or t.window_start, t.position)
    if t.partner_name:
        rank = PACKAGE_ORDER.index(t.partner_package) if t.partner_package else len(PACKAGE_ORDER)
        return (1, rank, t.position)
    return (2, 0, t.position)


def _open(t: Task, at: datetime) -> bool:
    """A time-window task is on only while its window is open."""
    return (t.window_start is None or t.window_start <= at) and (t.window_end is None or at < t.window_end)


def totals(db: DbSession, guest: Guest) -> tuple[int, int]:
    """Points and coins: everything earned, less the coins spent in the market."""
    row = db.execute(select(func.coalesce(func.sum(ScoreEvent.points), 0), func.coalesce(func.sum(ScoreEvent.coins), 0))
                     .where(ScoreEvent.guest_id == guest.id)).one()
    return int(row[0]), int(row[1])


@router.get("/api/feed")
def feed(guest: Guest = Depends(current_guest), db: DbSession = Depends(get_db)) -> Feed:
    d = stages.day(db)
    points, coins = totals(db, guest)
    first = d.stages[0].starts_at.astimezone(EVENT_TZ) if d.stages else None
    if d.current is None:
        return Feed(points=points, coins=coins, state=d.state, stage_count=len(d.stages), starts_at=first,
                    stage=None, tasks=[])
    t = stages.now()
    tasks = [x for x in db.scalars(select(Task).where(Task.active, Task.stage_id == d.current.id)) if _open(x, t)]
    done = _done(db, guest)
    return Feed(points=points, coins=coins, state=d.state, stage_count=len(d.stages), starts_at=first,
                stage=stage_out(d.current), tasks=[_out(x, done) for x in sorted(tasks, key=_order)])


@router.get("/api/tasks/{task_id}")
def task(task_id: int, guest: Guest = Depends(current_guest), db: DbSession = Depends(get_db)) -> TaskOut:
    t = db.get(Task, task_id)
    if t is None or not t.active:
        raise HTTPException(404, "task_not_found")
    return _out(t, _done(db, guest))


class Award(BaseModel):
    # awarded: points added now · already: done before, nothing added · unavailable: not on at this moment
    result: str
    task: TaskOut


def _award(db: DbSession, guest: Guest, t: Task) -> Award:
    """Award a task once per guest, only while it is on: its stage is the current one and its window is open."""
    reason = task_reason(t.id)
    if reason in _done(db, guest):
        return Award(result="already", task=_out(t, {reason}))
    d = stages.day(db)
    if not t.active or d.current is None or t.stage_id != d.current.id or not _open(t, stages.now()):
        return Award(result="unavailable", task=_out(t, set()))
    # Two phones of the same guest scanning at once still award once
    added = db.execute(insert(ScoreEvent).values(guest_id=guest.id, reason=reason, points=t.points, coins=t.coins)
                       .on_conflict_do_nothing(index_elements=["guest_id", "reason"])).rowcount
    db.commit()
    return Award(result="awarded" if added else "already", task=_out(t, {reason}))


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
