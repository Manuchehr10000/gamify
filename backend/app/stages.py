"""Which stage of the day is on now. The schedule lives in the stages table (uploaded by the admin)."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models import Stage

# Dushanbe is UTC+5 all year (no daylight saving). Times in the admin's file are read in this zone.
EVENT_TZ = timezone(timedelta(hours=5))


def now() -> datetime:
    """The server clock; tests replace it to stand inside a stage."""
    return datetime.now(timezone.utc)


@dataclass
class Day:
    # none: no schedule uploaded · before: stage 1 not started · running · over: last stage ended
    state: str
    stages: list[Stage]
    current: Stage | None = None


def day(db: DbSession) -> Day:
    stages = list(db.scalars(select(Stage).order_by(Stage.number)))
    if not stages:
        return Day("none", stages)
    t = now()
    if t < stages[0].starts_at:
        return Day("before", stages)
    if t >= stages[-1].ends_at:
        return Day("over", stages)
    # Between two stages (a gap in the schedule) the earlier one stays on
    current = [s for s in stages if s.starts_at <= t][-1]
    return Day("running", stages, current)


def advance(db: DbSession) -> bool:
    """Start the next stage now. False when there is no next stage (schedule empty, last stage on, or over)."""
    d = day(db)
    t = now()
    if d.state == "before":
        d.stages[0].starts_at = t
    elif d.state == "running":
        i = d.stages.index(d.current)
        if i + 1 >= len(d.stages):
            return False
        d.current.ends_at = t
        d.stages[i + 1].starts_at = t
    else:
        return False
    db.commit()
    return True
