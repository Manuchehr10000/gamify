"""The ranking by points: live from score_events, or the places the admin froze before the ceremony."""
from dataclasses import dataclass

from sqlalchemy import Select, func, select, text, update
from sqlalchemy.orm import Session as DbSession

from app import ledger
from app.models import Guest, ScoreEvent


def guest_name(first: str, last: str) -> str:
    """First name and last initial: what guests agreed to show in the rating."""
    return f"{first} {last[:1]}." if last else first


def ranking() -> Select:
    """(guest_id, points) best first. Ties go to whoever reached the score first: the time of the guest's last
    event that changed their points (market buys change only coins; an award a retake reversed, and its reversal,
    cancel out). Guests marked «В рейтинге: нет» are left out."""
    points = func.sum(ScoreEvent.points)
    reached = func.max(ScoreEvent.created_at).filter(ScoreEvent.points != 0, ledger.standing())
    return (select(ScoreEvent.guest_id, points.label("points"))
            .join(Guest, Guest.id == ScoreEvent.guest_id).where(Guest.in_rating)
            .group_by(ScoreEvent.guest_id)
            .order_by(points.desc(), reached.asc().nulls_last(), ScoreEvent.guest_id))


@dataclass
class Row:
    place: int
    guest: Guest
    points: int


def frozen(db: DbSession) -> bool:
    return db.scalar(select(Guest.id).where(Guest.frozen_place.is_not(None)).limit(1)) is not None


def rows(db: DbSession) -> tuple[bool, list[Row]]:
    """Every ranked guest with their place: the frozen places while frozen, else live."""
    if frozen(db):
        guests = db.scalars(select(Guest).where(Guest.frozen_place.is_not(None), Guest.in_rating)
                            .order_by(Guest.frozen_place))
        return True, [Row(g.frozen_place, g, g.frozen_points) for g in guests]
    ranked = db.execute(ranking()).all()
    guests = {g.id: g for g in db.scalars(select(Guest).where(Guest.id.in_([gid for gid, _ in ranked])))}
    return False, [Row(n, guests[gid], int(points)) for n, (gid, points) in enumerate(ranked, start=1)]


class NothingToFreeze(Exception):
    """Nobody is ranked yet, so there are no places to keep."""


# One freeze or unfreeze at a time, so two presses at once can't overwrite the first freeze
FREEZE_LOCK = 7007


def freeze(db: DbSession) -> None:
    """Keep every ranked guest's place and points as they are now. Freezing again keeps the first freeze."""
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": FREEZE_LOCK})
    if frozen(db):
        db.commit()
        return
    places = [{"id": gid, "frozen_place": n, "frozen_points": int(points)}
              for n, (gid, points) in enumerate(db.execute(ranking()).all(), start=1)]
    if not places:
        db.rollback()
        raise NothingToFreeze
    db.execute(update(Guest), places)
    db.commit()


def unfreeze(db: DbSession) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": FREEZE_LOCK})
    db.execute(update(Guest).where(Guest.frozen_place.is_not(None)).values(frozen_place=None, frozen_points=None))
    db.commit()
