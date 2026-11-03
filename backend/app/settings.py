"""Game settings the admin edits in the form, kept in the settings table. The code holds each key's default, limits
and effect rule; the app's start adds missing keys with their default and refreshes the limits, never the value.
A later piece adds its keys to SETTINGS instead of a new table or environment value."""
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DbSession

from app.models import Setting


@dataclass(frozen=True)
class Spec:
    default: Decimal
    min: Decimal
    max: Decimal
    # Shown beside the field: now (from now on) · recheck (past activity checked again) · locked (refused while
    # running)
    effect: str = "now"
    integer: bool = True
    # Changing it while a stage runs asks for confirmation first
    live: bool = False


SETTINGS: dict[str, Spec] = {
    # Points for arriving (accepting the terms on the badge link)
    "arrival_points": Spec(Decimal(10), Decimal(0), Decimal(1000)),
    # A partner task's coins when its coins cell is blank: points × this, rounded up
    "partner_coin_multiplier": Spec(Decimal("1.5"), Decimal(1), Decimal(5), integer=False, live=True),
    # A moderator's «Бонус»: this share of the points the submission earned, rounded up
    "moderator_bonus_percent": Spec(Decimal(50), Decimal(0), Decimal(200), live=True),
    # Places in the guests' ranking
    "rating_top": Spec(Decimal(20), Decimal(5), Decimal(100)),
    # The moderation queue's «top guests first» filter
    "moderation_top": Spec(Decimal(20), Decimal(5), Decimal(100)),
    # Places on the hall screen and in the host's frozen list
    "hall_top": Spec(Decimal(10), Decimal(3), Decimal(30)),
    # A guest counts as active on /admin/live for this many minutes after doing something
    "active_window_minutes": Spec(Decimal(15), Decimal(1), Decimal(120)),
}

# Raised by every admin save; phones and screens poll it and reload when it moves
VERSION = "config_version"


def ensure(db: DbSession) -> None:
    """Run at every start: add missing keys with their default; limits and effect follow the code."""
    rows = [{"key": k, "value": s.default, "min_value": s.min, "max_value": s.max, "effect": s.effect}
            for k, s in SETTINGS.items()]
    rows.append({"key": VERSION, "value": Decimal(1), "min_value": Decimal(0), "max_value": Decimal(10) ** 9,
                 "effect": ""})
    stmt = insert(Setting).values(rows)
    db.execute(stmt.on_conflict_do_update(index_elements=["key"], set_={
        "min_value": stmt.excluded.min_value, "max_value": stmt.excluded.max_value, "effect": stmt.excluded.effect}))
    db.commit()


def get(db: DbSession, key: str) -> Decimal:
    """Read fresh on every request, so a saved change applies at once."""
    return db.scalar(select(Setting.value).where(Setting.key == key))


def number(db: DbSession, key: str) -> int:
    return int(get(db, key))


def bump(db: DbSession) -> None:
    """Move the config version in the same transaction as the save. The caller commits."""
    db.execute(update(Setting).where(Setting.key == VERSION).values(value=Setting.value + 1))


def version(db: DbSession) -> int:
    return number(db, VERSION)
