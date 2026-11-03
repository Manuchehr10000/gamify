from dataclasses import dataclass
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DbSession

from app.auth import current_guest
from app.db import get_db
from app.models import FeedRotation, Guest, Partner, Stage, Submission, Task
from app import badges, ledger, levels, places, push, settings, stages
from app.places import SUBMIT_METHODS
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
    # Points multiplier: the cards and the day bar show «×2» when it isn't 1
    multiplier: float


class TaskOut(BaseModel):
    id: int
    type: str
    text: str
    points: int
    coins: int
    partner_name: str
    window_end: datetime | None
    done: bool
    # The card's label: available «Доступно» · review «На проверке» (sent, the moderator hasn't decided; paid
    # already) · done «Выполнено» · full «Временно недоступно» (all its places are taken)
    state: str
    # qr, link, market, photo, text, photo_text, quiz or "" (not doable yet)
    method: str
    link: str
    # A quiz's countdown in seconds; None without one
    timer_seconds: int | None = None
    # A quiz with «Требует» whose hall QR the guest hasn't scanned yet
    locked: bool = False
    # A moderator's word on the guest's submission: retake (send again) · penalty (rejected, task closed) · ""
    review: str = ""


class FeedPush(BaseModel):
    id: int
    # stage · market · quiz_before · quiz_open · one_off; a stage push is the stage banner the app already shows
    kind: str
    title: str
    text: str
    # Where tapping it leads: a quiz's task page, or the feed
    url: str


class NewBadge(BaseModel):
    code: str
    # The admin's name for it
    name: str
    # Its rule type: the icon for a badge without one of its own
    rule: str


class Feed(BaseModel):
    points: int
    coins: int
    # The level the current points reach and the points to the next one (None at the top or with no levels)
    level: str
    to_next: int | None
    # Set once, when the guest has just climbed past the level they last saw: the full-screen moment
    new_level: str | None
    # Badges just earned and not seen before, in the order guests see them: a full-screen moment each, after the level's
    new_badges: list[NewBadge]
    # How many photos and texts the phone may keep waiting to send (the admin's setting)
    queue_size: int
    # The latest push still inside its 10-minute life: the banner for anyone with the app open, push or not
    push: FeedPush | None
    # The guest has earned task points: the app may ask (once per phone, which the phone itself remembers)
    ask_push: bool
    state: str
    stage_count: int
    starts_at: datetime | None
    stage: StageOut | None
    tasks: list[TaskOut]


def stage_out(s: Stage) -> StageOut:
    return StageOut(number=s.number, name=s.name, starts_at=s.starts_at.astimezone(EVENT_TZ),
                    ends_at=s.ends_at.astimezone(EVENT_TZ), message=s.message,
                    multiplier=float(s.multiplier))


def _done(db: DbSession, guest: Guest) -> set[str]:
    return ledger.done(db, guest.id)


# What the guest is told about a decision; accepted and bonus need no word
REVIEWS = {"retake", "penalty"}


def _reviews(db: DbSession, guest: Guest) -> dict[int, str]:
    """Each task's latest submission status: a new submission after a retake replaces the old word."""
    rows = db.execute(select(Submission.task_id, Submission.status).where(Submission.guest_id == guest.id)
                      .order_by(Submission.id))
    return {task_id: status for task_id, status in rows}


def partners(db: DbSession) -> dict[int, Partner]:
    return {p.id: p for p in db.scalars(select(Partner))}


@dataclass
class View:
    """What one guest's cards are worked out from, read once per request."""
    done: set[str]
    # Each task's latest submission status
    reviews: dict[int, str]
    by_id: dict[int, Partner]
    # The stage running now: an undecided submission is «На проверке» only in it, «Выполнено» once it has ended
    stage_id: int | None
    # Tasks whose places are all taken by others
    full: set[int]

    def done_task(self, t: Task) -> bool:
        return task_reason(t.id) in self.done

    def undecided(self, t: Task) -> bool:
        return t.method in SUBMIT_METHODS and self.reviews.get(t.id) == "" and self.done_task(t)

    def pinned(self, t: Task) -> bool:
        """Undecided in the current stage, or sent back for a retake: above the batch, outside its count."""
        if self.undecided(t):
            return t.stage_id == self.stage_id
        return self.reviews.get(t.id) == "retake" and not self.done_task(t)


def view(db: DbSession, guest: Guest, tasks: list[Task]) -> View:
    d = stages.day(db)
    return View(_done(db, guest), _reviews(db, guest), partners(db), d.current.id if d.current else None,
                places.full(db, guest.id, tasks))


def _state(t: Task, v: View) -> str:
    if v.done_task(t):
        return "review" if v.undecided(t) and t.stage_id == v.stage_id else "done"
    return "full" if t.id in v.full else "available"


def _out(t: Task, v: View) -> TaskOut:
    review = v.reviews.get(t.id, "")
    partner = v.by_id.get(t.partner_id)
    return TaskOut(id=t.id, type=t.type, text=t.text, points=t.points, coins=t.coins,
                   partner_name=partner.name if partner else "", done=v.done_task(t), state=_state(t, v),
                   method=t.method, link=t.link,
                   window_end=t.window_end.astimezone(EVENT_TZ) if t.window_end else None,
                   timer_seconds=t.timer_seconds,
                   locked=t.requires_task_id is not None and task_reason(t.requires_task_id) not in v.done,
                   review=review if review in REVIEWS else "")


def task_out(db: DbSession, guest: Guest, t: Task) -> TaskOut:
    return _out(t, view(db, guest, [t]))


def _order(t: Task, by_id: dict[int, Partner]) -> tuple:
    # Tasks with a time window first (soonest to close on top), then partners by package, then the rest
    if t.window_end or t.window_start:
        return (0, t.window_end or t.window_start, t.position, t.id)
    partner = by_id.get(t.partner_id)
    if partner:
        rank = PACKAGE_ORDER.index(partner.package) if partner.package else len(PACKAGE_ORDER)
        return (1, rank, t.position, t.id)
    return (2, 0, t.position, t.id)


def _open(t: Task, at: datetime) -> bool:
    """A time-window task is on only while its window is open."""
    return (t.window_start is None or t.window_start <= at) and (t.window_end is None or at < t.window_end)


def totals(db: DbSession, guest: Guest) -> tuple[int, int]:
    """Points and coins: everything earned, less the coins spent in the market. The stored totals, read fresh."""
    row = db.execute(select(Guest.points, Guest.coins).where(Guest.id == guest.id)).one()
    return row[0], row[1]


@router.get("/api/feed")
def feed(guest: Guest = Depends(current_guest), db: DbSession = Depends(get_db)) -> Feed:
    """The batch on screen: polls, coming back to the screen and returning from a task keep it."""
    return _feed(db, guest, advance=False)


def _windowed(t: Task) -> bool:
    return t.window_start is not None or t.window_end is not None


@dataclass
class Batch:
    tasks: list[Task]
    # The last rotating card in it: where the next batch starts after; None when it has none
    last: Task | None


def _batch(stage: Stage, tasks: list[Task], v: View, after: Task | None) -> Batch:
    """The cards one guest sees in the stage: pinned ones (undecided, or sent back for a retake) above, then B cards:
    open time windows first, then the rotation from the card after `after`, wrapping at the end. Done cards leave
    the batch (a decided one shows «Выполнено» on its page and on the phone's saved copy); full ones stay with
    their label, since places can free up."""
    def order(x: Task) -> tuple:
        return _order(x, v.by_id)

    pinned = sorted((x for x in tasks if v.pinned(x)), key=order)
    rest = [x for x in tasks if not v.pinned(x) and not v.done_task(x)]
    windows = sorted((x for x in rest if _windowed(x)), key=order)[:stage.batch_size]
    rotating = sorted((x for x in rest if not _windowed(x)), key=order)
    if after is not None:
        # By its place in the current order, so a card done, added or switched off since doesn't skip or repeat others
        mark = order(after)
        split = next((i for i, x in enumerate(rotating) if order(x) > mark), len(rotating))
        rotating = rotating[split:] + rotating[:split]
    shown = rotating[:max(0, stage.batch_size - len(windows))]
    return Batch(pinned + windows + shown, shown[-1] if shown else None)


def _further(card: Task, last: Task | None, after: Task | None, v: View) -> bool:
    """Whether `card` comes later than `last` in the rotation that starts after `after`."""
    if last is None:
        return True

    def place(x: Task) -> tuple:
        key = _order(x, v.by_id)
        return (after is not None and key <= _order(after, v.by_id), key)
    return place(card) > place(last)


def _push(db: DbSession) -> FeedPush | None:
    m = push.latest(db, push.LIFE)
    return FeedPush(id=m.id, kind=m.kind, title=m.title, text=m.text, url=push.url(m)) if m else None


def _feed(db: DbSession, guest: Guest, advance: bool) -> Feed:
    # The quiz router builds on this one, so it is imported here, not at the top
    from app.routers.quiz import settle
    settle(db, guest.id)
    d = stages.day(db)
    points, coins = totals(db, guest)
    lv = levels.place(levels.load(db), points)
    mine = {"points": points, "coins": coins, "level": lv.name if lv else "", "to_next": lv.to_next if lv else None,
            "new_level": lv.name if levels.climbed(db, guest, lv) else None,
            "new_badges": [NewBadge(code=b.code, name=b.name, rule=b.rule) for b in badges.fresh(db, guest.id)], "queue_size": settings.number(db, "upload_queue_size"),
            "push": _push(db), "ask_push": push.should_ask(db, guest.id)}
    first = d.stages[0].starts_at.astimezone(EVENT_TZ) if d.stages else None
    if d.current is None:
        return Feed(**mine, state=d.state, stage_count=len(d.stages), starts_at=first, stage=None, tasks=[])
    t = stages.now()
    tasks = [x for x in db.scalars(select(Task).where(Task.active, Task.stage_id == d.current.id)) if _open(x, t)]
    v = view(db, guest, tasks)
    rotation = db.get(FeedRotation, (guest.id, d.current.id))
    # The first page load in a stage shows the top of the rotation; each later one the cards after the last shown
    mark = (rotation.last_task_id if advance else rotation.after_task_id) if rotation else None
    after = db.get(Task, mark) if mark else None
    batch = _batch(d.current, tasks, v, after)
    if advance:
        last = batch.last or after
        stmt = insert(FeedRotation).values(guest_id=guest.id, stage_id=d.current.id,
                                           after_task_id=after.id if after else None,
                                           last_task_id=last.id if last else None)
        db.execute(stmt.on_conflict_do_update(index_elements=["guest_id", "stage_id"], set_={
            "after_task_id": stmt.excluded.after_task_id, "last_task_id": stmt.excluded.last_task_id}))
        db.commit()
    elif rotation and batch.last is not None and _further(batch.last, db.get(Task, rotation.last_task_id)
                                                          if rotation.last_task_id else None, after, v):
        # A card done since the page load let the batch fill from the next one: that card has been shown now, so
        # the next page load starts after it. Only the last card shown moves; this batch stays as it is
        db.execute(update(FeedRotation).where(
            FeedRotation.guest_id == guest.id, FeedRotation.stage_id == d.current.id,
            FeedRotation.after_task_id.is_not_distinct_from(after.id if after else None),
        ).values(last_task_id=batch.last.id))
        db.commit()
    return Feed(**mine, state=d.state, stage_count=len(d.stages), starts_at=first, stage=stage_out(d.current),
                tasks=[_out(x, v) for x in batch.tasks])


@router.post("/api/feed/next")
def feed_next(guest: Guest = Depends(current_guest), db: DbSession = Depends(get_db)) -> Feed:
    """A page load of /app (opening the app or a reload): the next batch of the rotation."""
    return _feed(db, guest, advance=True)


@router.get("/api/tasks/{task_id}")
def task(task_id: int, guest: Guest = Depends(current_guest), db: DbSession = Depends(get_db)) -> TaskOut:
    t = db.get(Task, task_id)
    if t is None or not t.active:
        raise HTTPException(404, "task_not_found")
    return task_out(db, guest, t)


class Award(BaseModel):
    # awarded: points added now · already: done before, nothing added · unavailable: not on at this moment ·
    # limit: all its places are taken («Лимит исчерпан»), nothing added
    result: str
    task: TaskOut


def available(db: DbSession, t: Task) -> bool:
    """A task can be done now: its stage is the current one and its window is open."""
    d = stages.day(db)
    return t.active and d.current is not None and t.stage_id == d.current.id and _open(t, stages.now())


def _award(db: DbSession, guest: Guest, t: Task) -> Award:
    """Award a QR or link task once per guest, only while it is on: its stage is the current one and its window is
    open."""
    reason = task_reason(t.id)
    if reason in _done(db, guest):
        return Award(result="already", task=task_out(db, guest, t))
    if not available(db, t):
        return Award(result="unavailable", task=task_out(db, guest, t))
    # Two phones of the same guest scanning at once still award once: the ledger checks under the guest's lock.
    # The place is checked and taken under the task's lock, so two guests can't both take the last one
    ledger.lock(db, guest.id)
    if not places.take(db, guest.id, t):
        db.rollback()
        return Award(result="limit", task=task_out(db, guest, t))
    # Points × the running stage's multiplier (available() made it this task's stage); coins as they are
    added = ledger.write(db, guest.id, reason, "task", t.points, t.coins,
                         multiplier=stages.multiplier(db)) is not None
    badges.sync(db, [guest.id], actor=guest.id)
    db.commit()
    return Award(result="awarded" if added else "already", task=task_out(db, guest, t))


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
