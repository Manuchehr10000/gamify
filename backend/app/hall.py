"""The hall screen's slides: its mode, when «Эфир» starts, the partner logos, the next countdown and the push to show.
The screens hold no state of their own: every screen open on /hall polls GET /api/hall and shows the same."""
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DbSession

from app import push, settings, stages
from app.models import HallState, LogoShow, Partner, Stage, Staff, Task

# The packages from biggest to smallest; a partner with no package shows like the smallest
PACKAGES = ("general", "headliner", "mf_partner", "supporters")
# What the server accepts from a screen's logo log
SHOW_SECONDS = (1, 30)
SHOW_MAX_AGE = timedelta(hours=2)
# A screen's clock a little ahead of the server's still counts
SHOW_SKEW = timedelta(minutes=1)


def mode(db: DbSession) -> str:
    return db.scalar(select(HallState.mode).where(HallState.id == 1)) or "auto"


def set_mode(db: DbSession, staff: Staff, new: str) -> HallState:
    """The caller checked the mode is auto, live, logos or pause. Commits."""
    stmt = insert(HallState).values(id=1, mode=new, staff_name=staff.name, changed_at=stages.now())
    db.execute(stmt.on_conflict_do_update(index_elements=["id"], set_={
        "mode": stmt.excluded.mode, "staff_name": stmt.excluded.staff_name, "changed_at": stmt.excluded.changed_at}))
    db.commit()
    return db.get(HallState, 1, populate_existing=True)


@dataclass
class Look:
    # Each slide's seconds and the smallest text on the screen, from the settings
    slide_seconds: int
    min_font_px: int


def look(db: DbSession) -> Look:
    return Look(settings.number(db, "hall_slide_seconds"), settings.number(db, "hall_min_font_px"))


def live_from(db: DbSession) -> datetime | None:
    """«Эфир» starts this long before the last stage ends, read fresh each poll, so moving the last stage moves it.
    It has no end: after the last stage it stays on until a switch. None without a schedule."""
    end = db.scalar(select(Stage.ends_at).where(Stage.active).order_by(Stage.number.desc()).limit(1))
    return end - timedelta(minutes=settings.number(db, "hall_live_minutes")) if end else None


@dataclass
class Target:
    # quiz · market · stage
    kind: str
    name: str
    at: datetime


def next_target(db: DbSession) -> Target | None:
    """The countdown slide's target: the next quiz window, the market opening or the next stage start, whichever
    comes first. None with nothing ahead."""
    t = stages.now()
    found: list[Target] = []
    quiz = db.execute(select(Task.text, Task.window_start).join(Stage, Stage.id == Task.stage_id)
                      .where(Task.active, Task.method == "quiz", Stage.active, Task.window_start > t)
                      .order_by(Task.window_start).limit(1)).first()
    if quiz:
        found.append(Target("quiz", quiz.text, quiz.window_start))
    market = stages.market_opens_at(db)
    if market and market > t:
        found.append(Target("market", "", market))
    stage = db.execute(select(Stage.name, Stage.starts_at).where(Stage.active, Stage.starts_at > t)
                       .order_by(Stage.starts_at).limit(1)).first()
    if stage:
        found.append(Target("stage", stage.name, stage.starts_at))
    return min(found, key=lambda x: x.at) if found else None


@dataclass
class Logo:
    id: int
    name: str
    # 1 small · 2 medium · 3 large
    size: int
    # Shown on every Nth logo slide
    every: int
    url: str


def logos(db: DbSession) -> list[Logo]:
    """Active partners with a logo, biggest package first. The URL carries the partner's version, so a new logo is a
    new address the screen loads afresh."""
    rows = db.execute(select(Partner.id, Partner.name, Partner.package, Partner.version)
                      .where(Partner.active, Partner.logo.is_not(None)).order_by(Partner.id)).all()
    out = []
    for r in sorted(rows, key=lambda r: PACKAGES.index(_package(r.package))):
        package = _package(r.package)
        out.append(Logo(r.id, r.name, settings.number(db, f"hall_{package}_size"),
                        settings.number(db, f"hall_{package}_every"), f"/api/partners/{r.id}/logo?v={r.version}"))
    return out


def _package(package: str) -> str:
    return package if package in PACKAGES else PACKAGES[-1]


@dataclass
class Push:
    id: int
    text: str


# How long a push stays in the hall body: the screen shows each push once, for 15 seconds
PUSH_SECONDS = timedelta(seconds=15)


def latest_push(db: DbSession) -> Push | None:
    """The latest push sent in the last 15 seconds (or due then while pushes were off), title and text together."""
    m = push.latest(db, PUSH_SECONDS)
    if m is None:
        return None
    return Push(m.id, f"{m.title}\n{m.text}" if m.text else m.title)


@dataclass
class Show:
    partner_id: int
    started_at: datetime
    seconds: int


def log_shows(db: DbSession, shows: list[Show]) -> int:
    """Keep the shows that pass the checks (an active partner, 1–30 seconds, started within the last 2 hours) and
    drop the rest. A show sent twice is kept once. Commits; returns how many were new."""
    t = stages.now()
    active = set(db.scalars(select(Partner.id).where(Partner.active,
                                                     Partner.id.in_({s.partner_id for s in shows}))))
    rows = [{"partner_id": s.partner_id, "started_at": s.started_at, "seconds": s.seconds} for s in shows
            if s.partner_id in active and SHOW_SECONDS[0] <= s.seconds <= SHOW_SECONDS[1]
            and s.started_at.tzinfo is not None and t - SHOW_MAX_AGE <= s.started_at <= t + SHOW_SKEW]
    if not rows:
        return 0
    kept = db.execute(insert(LogoShow).values(rows).on_conflict_do_nothing().returning(LogoShow.id)).all()
    db.commit()
    return len(kept)
