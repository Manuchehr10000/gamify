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
    # A text setting: its default text; min and max are then its length
    text: str | None = None
    # A text setting holding a date (YYYY-MM-DD) or blank
    date: bool = False
    # A text setting holding one of these ids
    choices: tuple[str, ...] | None = None


# The event's look: each skin has a dark theme for guests and the hall and a light one for staff and admins
SKINS = ("console", "steampunk", "space", "ornament")


def _text(default: str) -> Spec:
    return Spec(Decimal(0), Decimal(1), Decimal(200), text=default)


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
    # A photo's claim holds the guest's place this many minutes; files that come later are refused
    "claim_minutes": Spec(Decimal(60), Decimal(10), Decimal(240)),
    # Submissions one phone keeps waiting to send; beyond that «Дождитесь загрузки предыдущих фото»
    "upload_queue_size": Spec(Decimal(5), Decimal(1), Decimal(10)),
    # The hall screen: each slide's seconds, «Эфир» this many minutes before the last stage ends, and the smallest
    # text it shows
    "hall_slide_seconds": Spec(Decimal(8), Decimal(4), Decimal(30)),
    "hall_live_minutes": Spec(Decimal(30), Decimal(5), Decimal(120)),
    "hall_min_font_px": Spec(Decimal(40), Decimal(24), Decimal(80)),
    # Each partner package's logo size (1 small, 2 medium, 3 large) and how often it shows (every Nth logo slide)
    "hall_general_size": Spec(Decimal(3), Decimal(1), Decimal(3)),
    "hall_general_every": Spec(Decimal(1), Decimal(1), Decimal(10)),
    "hall_headliner_size": Spec(Decimal(2), Decimal(1), Decimal(3)),
    "hall_headliner_every": Spec(Decimal(1), Decimal(1), Decimal(10)),
    "hall_mf_partner_size": Spec(Decimal(2), Decimal(1), Decimal(3)),
    "hall_mf_partner_every": Spec(Decimal(2), Decimal(1), Decimal(10)),
    "hall_supporters_size": Spec(Decimal(1), Decimal(1), Decimal(3)),
    "hall_supporters_every": Spec(Decimal(3), Decimal(1), Decimal(10)),
    # Pushes to phones on (1) or off (0); off, the banner still shows in open apps and on the hall screen
    "push_enabled": Spec(Decimal(1), Decimal(0), Decimal(1)),
    # The push titles per kind, in Russian; the stage push takes the stage's banner instead
    "push_text_quiz_before": _text("Через 5 минут — квиз"),
    "push_text_quiz_open": _text("Квиз открыт: 5 минут"),
    "push_text_market": _text("Маркет открыт — обменяйте монеты на призы"),
    "push_text_one_off": _text("Сообщение организаторов"),
    # The day partners' photo links stop working (and piece 22 deletes the photos); blank: photos.delete_date's
    # default, the last stage's end + 30 days
    "photo_delete_date": Spec(Decimal(0), Decimal(0), Decimal(10), text="", date=True),
    # The skin every page shows; saving it always asks first, as it changes every screen at once
    "skin": Spec(Decimal(0), Decimal(1), Decimal(20), text=SKINS[0], choices=SKINS),
}

# Raised by every admin save; phones and screens poll it and reload when it moves
VERSION = "config_version"


def ensure(db: DbSession) -> None:
    """Run at every start: add missing keys with their default; limits and effect follow the code."""
    rows = [{"key": k, "value": s.default, "min_value": s.min, "max_value": s.max, "effect": s.effect,
             "text_value": s.text} for k, s in SETTINGS.items()]
    rows.append({"key": VERSION, "value": Decimal(1), "min_value": Decimal(0), "max_value": Decimal(10) ** 9,
                 "effect": "", "text_value": None})
    stmt = insert(Setting).values(rows)
    db.execute(stmt.on_conflict_do_update(index_elements=["key"], set_={
        "min_value": stmt.excluded.min_value, "max_value": stmt.excluded.max_value, "effect": stmt.excluded.effect}))
    db.commit()


def get(db: DbSession, key: str) -> Decimal:
    """Read fresh on every request, so a saved change applies at once."""
    return db.scalar(select(Setting.value).where(Setting.key == key))


def number(db: DbSession, key: str) -> int:
    return int(get(db, key))


def text(db: DbSession, key: str) -> str:
    """A text setting's value, read fresh."""
    return db.scalar(select(Setting.text_value).where(Setting.key == key)) or ""


def skin(db: DbSession) -> str:
    return text(db, "skin") or SKINS[0]


def bump(db: DbSession) -> None:
    """Move the config version in the same transaction as the save. The caller commits."""
    db.execute(update(Setting).where(Setting.key == VERSION).values(value=Setting.value + 1))


def version(db: DbSession) -> int:
    return number(db, VERSION)
