"""The points and coins record. Every change to a guest's points or coins goes through write(): it adds one
score_events row and moves the guest's stored totals in the same transaction. Rows are never edited or deleted;
a retake adds a reversal row that points at the award it takes back."""
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy import ColumnElement, exists, select, update
from sqlalchemy.orm import Session as DbSession, aliased

from app import stages
from app.models import Guest, ScoreEvent

ACTIONS = {"arrival", "task", "bonus", "retake", "penalty", "buy", "speed", "badge", "withdraw"}
# Actions that pay once per reason while the award stands: a double scan or a second phone adds nothing
AWARDS = {"arrival", "task", "badge", "speed"}


def standing() -> ColumnElement[bool]:
    """A row that counts: not a reversal, and no reversal points at it. A penalty or withdraw row has no reversal
    target, so the award it takes points from still counts as done."""
    reversal = aliased(ScoreEvent)
    return ScoreEvent.reverses_id.is_(None) & ~exists().where(reversal.reverses_id == ScoreEvent.id)


def award(db: DbSession, guest_id: int, reason: str) -> ScoreEvent | None:
    """The guest's standing award for the reason, if any."""
    return db.scalar(select(ScoreEvent).where(ScoreEvent.guest_id == guest_id, ScoreEvent.reason == reason, standing())
                     .order_by(ScoreEvent.id.desc()).limit(1))


def done(db: DbSession, guest_id: int) -> set[str]:
    """The reasons of the guest's standing rows: task:{id} in it means the task is done."""
    return set(db.scalars(select(ScoreEvent.reason).where(ScoreEvent.guest_id == guest_id, standing())))


def lock(db: DbSession, guest_id: int) -> None:
    """The guest's row, locked until commit: writes for one guest go one after another."""
    db.execute(select(Guest.id).where(Guest.id == guest_id).with_for_update())


def points_of(base_points: int, multiplier: Decimal) -> int:
    """base × multiplier, rounded to whole points, halves up."""
    return int((Decimal(base_points) * multiplier).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def write(db: DbSession, guest_id: int, reason: str, action: str, base_points: int, coins: int,
          multiplier: Decimal = Decimal(1), reverses: ScoreEvent | None = None,
          stage_id: int | None | Literal["now"] = "now") -> ScoreEvent | None:
    """Add one row and move the guest's totals by it. An award (arrival, task, badge) is written only when no
    standing one has the same reason; None then. A reversal is always written. stage_id: a claim's stage, for an
    award paid after it, kept as given even when that stage was deleted since (None); "now": the stage running now.
    The caller commits."""
    assert action in ACTIONS
    lock(db, guest_id)
    if action in AWARDS and reverses is None and award(db, guest_id, reason) is not None:
        return None
    if stage_id == "now":
        d = stages.day(db)
        stage_id = d.current.id if d.current else None
    points = points_of(base_points, multiplier)
    event = ScoreEvent(guest_id=guest_id, reason=reason, action=action, base_points=base_points,
                       multiplier=multiplier, points=points, coins=coins,
                       stage_id=stage_id,
                       reverses_id=reverses.id if reverses else None)
    db.add(event)
    db.execute(update(Guest).where(Guest.id == guest_id)
               .values(points=Guest.points + points, coins=Guest.coins + coins))
    db.flush()
    return event


def take_back(db: DbSession, event: ScoreEvent, reason: str, action: str, reverse: bool) -> ScoreEvent:
    """A row that takes an award's points and coins back. reverse=True (a retake) points at the award, which then
    no longer counts as done; a penalty doesn't, so the task stays closed."""
    # Negated as written, not re-multiplied: rounding a negative product could miss by a point
    return write(db, event.guest_id, reason, action, -event.points, -event.coins,
                 reverses=event if reverse else None)
