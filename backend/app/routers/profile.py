from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app import badges, ledger, levels
from app.auth import current_guest
from app.db import get_db
from app.models import Guest, Prize, ScoreEvent, Submission, Task
from app.routers.badge import ARRIVAL
from app.routers.feed import totals
from app.routers.market import local
from app.routers.quiz import settle

router = APIRouter()


class Entry(BaseModel):
    # task (done, with what it earned) · buy (a market purchase, coins spent) · arrival (points for coming)
    kind: str
    # The task's text or the prize's name; empty for arrival
    text: str
    points: int
    coins: int
    # A moderator's bonus on the task's photo or text, or a blitz's speed bonus; 0 without one
    bonus: int = 0
    # A moderator rejected it: its points and coins were taken back
    rejected: bool = False
    at: datetime


class ShelfBadge(BaseModel):
    code: str
    # The admin's name for it
    name: str
    # The rule and its numbers and filters: the page writes the greyed condition from them
    rule: str
    count: int | None
    kinds: str
    partner: str
    any_partner: bool
    # «Первые N»: the task's text
    task: str
    held: bool


class Profile(BaseModel):
    level: str
    to_next: int | None
    points: int
    # Below zero when a rejection took back coins already spent
    coins: int
    # Every badge switched on, in the order guests see them; the page greys out the ones not held
    badges: list[ShelfBadge]
    # Newest first
    history: list[Entry]


@router.get("/api/profile")
def profile(guest: Guest = Depends(current_guest), db: DbSession = Depends(get_db)) -> Profile:
    settle(db, guest.id)
    points, coins = totals(db, guest)
    lv = levels.place(levels.load(db), points)
    # An award a retake reversed, and its reversal, leave the history together
    events = list(db.scalars(select(ScoreEvent).where(ScoreEvent.guest_id == guest.id, ledger.standing())
                             .order_by(ScoreEvent.created_at.desc(), ScoreEvent.id.desc())))
    ids = {kind: {int(e.reason.split(":")[1]) for e in events if e.reason.startswith(kind + ":")}
           for kind in ("task", "bonus", "penalty", "buy")}
    # Rows hidden from the file since stay in the history
    tasks = dict(db.execute(select(Task.id, Task.text).where(Task.id.in_(ids["task"]))).all())
    prizes = dict(db.execute(select(Prize.id, Prize.name).where(Prize.id.in_(ids["buy"]))).all())
    # A moderator's decision is keyed by the submission; it belongs to the submission's task
    of_task = dict(db.execute(select(Submission.id, Submission.task_id)
                              .where(Submission.id.in_(ids["bonus"] | ids["penalty"]))).all())
    entries: dict[str, Entry] = {}
    history: list[Entry] = []
    for e in events:
        kind, _, ref = e.reason.partition(":")
        if kind == "task":
            entries[e.reason] = Entry(kind="task", text=tasks.get(int(ref), ""), points=e.points, coins=e.coins,
                                      at=local(e.created_at))
            history.append(entries[e.reason])
        elif kind == "buy":
            history.append(Entry(kind="buy", text=prizes.get(int(ref), ""), points=e.points, coins=e.coins,
                                 at=local(e.created_at)))
        elif e.reason == ARRIVAL:
            history.append(Entry(kind="arrival", text="", points=e.points, coins=e.coins, at=local(e.created_at)))
    for e in events:
        kind, _, ref = e.reason.partition(":")
        # A blitz's speed bonus belongs to its quiz, as a moderator's bonus to its submission's task
        entry = (entries.get(f"task:{of_task.get(int(ref))}") if kind in ("bonus", "penalty")
                 else entries.get(f"task:{ref}") if kind == "speed" else None)
        if entry is None:
            continue
        if kind in ("bonus", "speed"):
            entry.bonus += e.points
        else:
            entry.rejected = True
    return Profile(level=lv.name if lv else "", to_next=lv.to_next if lv else None, points=points, coins=coins,
                   badges=[ShelfBadge(**vars(b)) for b in badges.shelf(db, guest.id)], history=history)
