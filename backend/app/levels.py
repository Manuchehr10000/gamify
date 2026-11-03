"""Levels by points: the thresholds come from the file's «Уровни» sheet, never from the code."""
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from app.models import Guest, Level


def load(db: DbSession) -> list[Level]:
    return list(db.scalars(select(Level).order_by(Level.min_points)))


@dataclass
class Place:
    # The level's place in the list, from 0
    index: int
    name: str
    # The level's «Баллов от»
    min_points: int
    # Points still needed for the next level; None at the top
    to_next: int | None


def place(levels: list[Level], points: int) -> Place | None:
    """The highest level the points reach; None when no levels are loaded."""
    if not levels:
        return None
    i = max((n for n, lv in enumerate(levels) if lv.min_points <= points), default=0)
    nxt = levels[i + 1].min_points - points if i + 1 < len(levels) else None
    return Place(i, levels[i].name, levels[i].min_points, nxt)


def name(levels: list[Level], points: int) -> str:
    p = place(levels, points)
    return p.name if p else ""


def climbed(db: DbSession, guest: Guest, p: Place | None) -> bool:
    """Remember the level the guest is shown. True once per climb past the last one seen: a drop after a rejection
    lowers the mark quietly, so climbing again shows the moment again. Conditional updates, so two loads at once
    can't both show it."""
    if p is None:
        return False
    up = db.execute(update(Guest).where(Guest.id == guest.id, Guest.level_shown < p.min_points)
                    .values(level_shown=p.min_points)).rowcount
    db.execute(update(Guest).where(Guest.id == guest.id, Guest.level_shown > p.min_points)
               .values(level_shown=p.min_points))
    db.commit()
    return bool(up)


def dropped(db: DbSession, guest_id: int) -> None:
    """Lower the mark where points go down (a moderator's rejection), so climbing back shows the moment again even
    when the guest never opened the feed in between. The caller commits."""
    points = db.scalar(select(Guest.points).where(Guest.id == guest_id))
    p = place(load(db), points)
    if p is not None:
        db.execute(update(Guest).where(Guest.id == guest_id, Guest.level_shown > p.min_points)
                   .values(level_shown=p.min_points))
