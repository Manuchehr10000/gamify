"""Push notifications. The schedule (push_messages) follows its sources: each stage's start, each quiz window («Доступно
с»: 5 minutes before and at the opening) and the first stage marked «Маркет»; the admin adds one-off messages. The job
runner sends what is due each minute; a push lives 10 minutes, then it is expired, unsent."""
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from pywebpush import WebPushException, webpush
from sqlalchemy import any_, exists, func, select, text, update
from sqlalchemy.orm import Session as DbSession

from app import config, settings, stages
from app.models import PushMessage, PushSubscription, ScoreEvent, Stage, Task

# In this order: at the same minute the stage push goes before the market push
KINDS = ("stage", "market", "quiz_before", "quiz_open", "one_off")
STATES = ("planned", "sent", "cancelled", "expired")
# A push's life: the push service is told it (TTL), and the job expires anything this far past due
LIFE = timedelta(minutes=10)
QUIZ_LEAD = timedelta(minutes=5)
# Held while the schedule is rebuilt, so the job and an admin's page can't both add a source's row
REGEN_LOCK = 7019
# Pushes sent at once: one minute's push to every guest finishes inside that minute
WORKERS = 32
# The per-kind titles in the settings; the stage push takes the stage's banner instead
TEXT_KEYS = {"quiz_before": "push_text_quiz_before", "quiz_open": "push_text_quiz_open", "market": "push_text_market",
             "one_off": "push_text_one_off"}


def ready() -> bool:
    """All three VAPID values are set. Unset: phones are never asked and nothing is sent."""
    return bool(config.VAPID_PUBLIC_KEY and config.VAPID_PRIVATE_KEY and config.VAPID_SUBJECT)


def enabled(db: DbSession) -> bool:
    return settings.number(db, "push_enabled") == 1


def stage_title(stage: Stage) -> str:
    """The stage banner's title (feed.newStage / feed.newStageMultiplier in the app's ru.json), «×1,5» with a comma."""
    m = Decimal(str(stage.multiplier)).normalize()
    if m == 1:
        return f"Новый этап: {stage.name}"
    return f"Новый этап: {stage.name} — очки ×{format(m, 'f').replace('.', ',')}"


@dataclass
class Source:
    key: str
    kind: str
    at: datetime
    title: str
    text: str
    task_id: int | None = None


def sources(db: DbSession) -> list[Source]:
    out = []
    day = list(db.scalars(select(Stage).where(Stage.active).order_by(Stage.number)))
    for s in day:
        out.append(Source(f"stage:{s.id}", "stage", s.starts_at, stage_title(s), s.message))
    market = next((s for s in day if s.market), None)
    if market:
        out.append(Source("market", "market", market.starts_at, settings.text(db, TEXT_KEYS["market"]), ""))
    quizzes = db.scalars(select(Task).join(Stage, Stage.id == Task.stage_id).where(
        Task.active, Task.method == "quiz", Task.window_start.is_not(None), Stage.active).order_by(Task.window_start))
    for t in quizzes:
        out.append(Source(f"quiz_before:{t.id}", "quiz_before", t.window_start - QUIZ_LEAD,
                          settings.text(db, TEXT_KEYS["quiz_before"]), t.text, t.id))
        out.append(Source(f"quiz_open:{t.id}", "quiz_open", t.window_start,
                          settings.text(db, TEXT_KEYS["quiz_open"]), t.text, t.id))
    return out


def _put(row: PushMessage, name: str, value: object) -> None:
    # Only a real change is written, so the row's version moves only then
    if getattr(row, name) != value:
        setattr(row, name, value)


def regenerate(db: DbSession) -> None:
    """Bring the planned pushes in step with their sources: new sources get a row, moved ones move it (keeping the
    admin's shift), and their texts follow unless the admin edited them. A source that is gone (a switched-off quiz,
    the «Маркет» mark taken off) drops its planned push. Sent, expired and cancelled pushes are left alone.
    The caller commits."""
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": REGEN_LOCK})
    rows = {r.source: r for r in db.scalars(select(PushMessage).where(PushMessage.source.is_not(None)))}
    for s in sources(db):
        row = rows.pop(s.key, None)
        if row is None:
            db.add(PushMessage(kind=s.kind, source=s.key, task_id=s.task_id, source_at=s.at, at=s.at, title=s.title,
                               text=s.text))
            continue
        if row.state not in ("planned", "cancelled"):
            continue
        _put(row, "source_at", s.at)
        _put(row, "at", s.at + timedelta(seconds=row.shift_seconds))
        if not row.text_edited:
            _put(row, "title", s.title)
            _put(row, "text", s.text)
    for row in rows.values():
        if row.state == "planned":
            db.delete(row)
    db.flush()


def url(m: PushMessage) -> str:
    """Tapping a quiz push opens that quiz's task page; any other push opens the feed."""
    return f"/app/tasks/{m.task_id}" if m.kind in ("quiz_before", "quiz_open") and m.task_id else "/app"


def deliver(subscription: dict, data: str) -> str:
    """One push to one phone: ok (accepted by the push service) · gone (the phone dropped it) · failed."""
    try:
        webpush(subscription, data, vapid_private_key=config.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": config.VAPID_SUBJECT}, ttl=int(LIFE.total_seconds()), timeout=10)
        return "ok"
    except WebPushException as e:
        status = getattr(e.response, "status_code", None)
        return "gone" if status in (404, 410) else "failed"
    except Exception:  # noqa: BLE001 — a network error is this phone's failure, not the whole send's
        return "failed"


def send(db: DbSession, m: PushMessage, shown_at: datetime | None = None) -> None:
    """Send one push to every active subscription, several at a time, and count the answers. Subscriptions the push
    service reports gone are switched off. The push is marked sent and committed before any phone is reached, so the
    row lock and the transaction never span the requests, and a crash mid-send can't send it a second time."""
    subs = [(s.id, s.key, {"endpoint": s.endpoint, "keys": {"p256dh": s.p256dh, "auth": s.auth}})
            for s in db.scalars(select(PushSubscription).where(PushSubscription.active).order_by(PushSubscription.id))]
    m.state, m.shown_at = "sent", shown_at or stages.now()
    payload = {"id": m.id, "title": m.title, "body": m.text, "url": url(m)}
    push_id = m.id
    db.commit()

    def one(sub: tuple[int, str, dict]) -> str:
        return deliver(sub[2], json.dumps({**payload, "sub": sub[1]}, ensure_ascii=False))

    with ThreadPoolExecutor(WORKERS) as pool:
        results = list(pool.map(one, subs))
    ok = results.count("ok")
    gone = [sub[0] for sub, result in zip(subs, results) if result == "gone"]
    db.execute(update(PushMessage).where(PushMessage.id == push_id).values(
        sends=PushMessage.sends + ok, failures=PushMessage.failures + len(results) - ok)
        .execution_options(synchronize_session=False))
    if gone:
        db.execute(update(PushSubscription).where(PushSubscription.id.in_(gone)).values(active=False))
    db.commit()


def run(db: DbSession) -> str:
    """The job: rebuild the schedule, expire what is more than 10 minutes past due, then send what is due. With
    pushes off (or no VAPID keys) a due push is not sent: it is expired and still shows in open apps and on /hall."""
    regenerate(db)
    db.commit()
    t = stages.now()
    expired = db.execute(update(PushMessage).where(PushMessage.state == "planned", PushMessage.at < t - LIFE)
                         .values(state="expired")).rowcount
    db.commit()
    due = db.execute(select(PushMessage.id, PushMessage.at, PushMessage.kind)
                     .where(PushMessage.state == "planned", PushMessage.at <= t)).all()
    due.sort(key=lambda r: (r.at, KINDS.index(r.kind), r.id))
    on = enabled(db) and ready()
    sent = handled = 0
    for i, r in enumerate(due):
        # Locked and read again: an admin's «send now» or cancel since then wins
        m = db.get(PushMessage, r.id, with_for_update=True, populate_existing=True)
        if m is None or m.state != "planned":
            db.rollback()
            continue
        handled += 1
        # A microsecond apart in sending order, so the newest one out is the last sent (the market after the stage)
        shown_at = t + timedelta(microseconds=i)
        if on:
            # Kept as sent before it goes, so a failure later in the run doesn't send it again
            send(db, m, shown_at)
            sent += 1
        else:
            m.state, m.shown_at = "expired", shown_at
            db.commit()
    note = f"отправлено: {sent}, истекло: {expired + handled - sent}"
    return note if ready() else note + " (нет ключей VAPID)"


def receive(db: DbSession, push_id: int, key: str) -> bool:
    """A phone's report that the push arrived: counted once per subscription per push. The caller commits."""
    sub_id = db.scalar(select(PushSubscription.id).where(PushSubscription.key == key))
    if sub_id is None:
        return False
    counted = db.execute(update(PushMessage).where(
        PushMessage.id == push_id, PushMessage.state == "sent", ~(sub_id == any_(PushMessage.counted_subscriptions)),
    ).values(deliveries=PushMessage.deliveries + 1,
             counted_subscriptions=func.array_append(PushMessage.counted_subscriptions, sub_id)))
    return counted.rowcount > 0


def latest(db: DbSession, within: timedelta) -> PushMessage | None:
    """The newest push that went out within this long: the banner in open apps and the hall screen's interrupt."""
    return db.scalar(select(PushMessage).where(PushMessage.shown_at >= stages.now() - within)
                     .order_by(PushMessage.shown_at.desc(), PushMessage.id.desc()).limit(1))


def should_ask(db: DbSession, guest_id: int) -> bool:
    """The app may ask once the guest has task points (not the +10 for arriving). Once per phone is the phone's own
    memory (it said yes, «Не сейчас» or Block), so a second phone of the same guest is asked too."""
    if not ready():
        return False
    return bool(db.scalar(select(exists().where(ScoreEvent.guest_id == guest_id, ScoreEvent.action == "task"))))


@dataclass
class Counts:
    opt_ins: int
    sends: int
    deliveries: int
    failures: int


def counts(db: DbSession) -> Counts:
    """For /admin/live and piece 21: active subscriptions, and the sums over every push."""
    opt_ins = db.scalar(select(func.count()).where(PushSubscription.active))
    sends, deliveries, failures = db.execute(select(
        func.coalesce(func.sum(PushMessage.sends), 0), func.coalesce(func.sum(PushMessage.deliveries), 0),
        func.coalesce(func.sum(PushMessage.failures), 0))).one()
    return Counts(opt_ins, int(sends), int(deliveries), int(failures))
