from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
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
    """The score_events reason for doing a task: one award per task per guest. Piece 3 writes it."""
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


class Feed(BaseModel):
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
                   partner_name=t.partner_name, done=task_reason(t.id) in done,
                   window_end=t.window_end.astimezone(EVENT_TZ) if t.window_end else None)


def _order(t: Task) -> tuple:
    # Tasks with a time window first (soonest to close on top), then partners by package, then the rest
    if t.window_end or t.window_start:
        return (0, t.window_end or t.window_start, t.position)
    if t.partner_name:
        rank = PACKAGE_ORDER.index(t.partner_package) if t.partner_package else len(PACKAGE_ORDER)
        return (1, rank, t.position)
    return (2, 0, t.position)


@router.get("/api/feed")
def feed(guest: Guest = Depends(current_guest), db: DbSession = Depends(get_db)) -> Feed:
    d = stages.day(db)
    first = d.stages[0].starts_at.astimezone(EVENT_TZ) if d.stages else None
    if d.current is None:
        return Feed(state=d.state, stage_count=len(d.stages), starts_at=first, stage=None, tasks=[])
    t = stages.now()
    tasks = [x for x in db.scalars(select(Task).where(Task.active, Task.stage_id == d.current.id))
             # A time-window task shows only while its window is open
             if (x.window_start is None or x.window_start <= t) and (x.window_end is None or t < x.window_end)]
    done = _done(db, guest)
    return Feed(state=d.state, stage_count=len(d.stages), starts_at=first, stage=stage_out(d.current),
                tasks=[_out(x, done) for x in sorted(tasks, key=_order)])


@router.get("/api/tasks/{task_id}")
def task(task_id: int, guest: Guest = Depends(current_guest), db: DbSession = Depends(get_db)) -> TaskOut:
    t = db.get(Task, task_id)
    if t is None or not t.active:
        raise HTTPException(404, "task_not_found")
    return _out(t, _done(db, guest))
