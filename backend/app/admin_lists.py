"""The lists the admin edits in /admin/settings, one registry behind /api/admin/lists/{kind}. Each kind names its
table, its fields with their limits and effect rules, what keeps a row from being deleted, and what a save changes
in the live game. A later piece registers its own kind in KINDS."""
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import ColumnElement, delete, exists, func, select, text
from sqlalchemy.orm import Session as DbSession

from app import accounts, changes, settings, stages
from app.models import (ChangeEvent, Level, Partner, Prize, Question, QuizAttempt, ScoreEvent, Session,
                        Stage, Staff, Submission, Task)
from app.stages import EVENT_TZ
from app.task_file import LIMITS, METHODS, PACKAGES, TYPES, rule_coins, sold

ROLES = ("admin", "moderator", "desk", "stand")
# The desk and the stands share one account each: its PIN is reset, never a second one added
SHARED = ("desk", "stand")
# Held while counting the active admins, so two admins switching each other off can't both pass
ADMINS_LOCK = 7013


@dataclass(frozen=True)
class Field:
    name: str
    # int · text · bool · datetime · choice · ref · secret
    type: str
    required: bool = False
    # int: the range; text and secret: the length
    min: int | None = None
    max: int | None = None
    choices: tuple[str, ...] = ()
    # ref: the kind it points at, and which of its rows it may point at
    ref: str | None = None
    where: Callable[[], ColumnElement[bool]] | None = None
    # now (from now on) · recheck (past activity checked again) · locked (refused while running)
    effect: str = "now"
    # No other row may have the same value
    unique: bool = False
    # Set when the row is added, never changed after (a staff account's role)
    fixed: bool = False
    # A blank text is stored as NULL, not ""
    null: bool = False


def refuse(code: str, status: int = 400, **detail) -> HTTPException:
    return HTTPException(status, {"code": code, **detail})


@dataclass
class Kind:
    model: type
    fields: list[Field]
    order: Callable[[], list]
    # Cross-field checks on the row once the new values are on it; raises
    check: Callable[[DbSession, object, bool], None] = lambda db, row, creating: None
    # Why the row can't be deleted (it is in use, or the list can't do without it); None when it can
    keep: Callable[[DbSession, object], str | None] = lambda db, row: None
    # Refused while the live game uses it (a quiz's questions during its blitz); raises
    lock: Callable[[DbSession, object], None] = lambda db, row: None
    # What the live game looks like, taken before and after a save to tell what the save changes in it
    state: Callable[[DbSession, object | None], object] = lambda db, row: None
    impact: Callable[[DbSession, object, object, bool], list[dict]] = lambda db, row, before, gone: []
    # Run after the values are on the row (filled fields, ended sessions)
    after: Callable[[DbSession, object, dict], None] = lambda db, row, changed: None
    # Read-only facts shown beside each row, keyed by row id
    extra: Callable[[DbSession, list], dict[int, dict]] = lambda db, rows: {}
    secret_fields: tuple[str, ...] = field(default=())


# Values ----------------------------------------------------------------------------------------------------------

def _value(db: DbSession, f: Field, raw: object) -> object:
    """One field's value from the form, checked against its limits; the refusal names the field and the range."""
    blank = raw is None or (isinstance(raw, str) and not raw.strip())
    if f.type == "bool":
        if not isinstance(raw, bool):
            raise refuse("bad_value", field=f.name)
        return raw
    if blank:
        if f.required:
            raise refuse("required", field=f.name)
        return None if f.null or f.type not in ("text", "choice") else ""
    if f.type == "int":
        if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
            raise refuse("bad_value", field=f.name)
        try:
            n = float(str(raw).replace(",", "."))
        except ValueError:
            raise refuse("bad_value", field=f.name) from None
        if not n.is_integer() or not f.min <= n <= f.max:
            raise refuse("out_of_range", field=f.name, min=f.min, max=f.max)
        return int(n)
    if not isinstance(raw, (str, int)):
        raise refuse("bad_value", field=f.name)
    if f.type == "ref":
        model = KINDS[f.ref].model
        q = select(model.id).where(model.id == raw)
        if f.where is not None:
            q = q.where(f.where())
        if not isinstance(raw, int) or db.scalar(q) is None:
            raise refuse("bad_value", field=f.name)
        return raw
    text = str(raw).strip() if f.type != "secret" else str(raw)
    if f.type == "datetime":
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            raise refuse("bad_value", field=f.name) from None
        # The form sends Dushanbe wall-clock time, as the Excel file does
        return dt.replace(tzinfo=EVENT_TZ) if dt.tzinfo is None else dt
    if f.type == "choice":
        if text not in f.choices:
            raise refuse("bad_value", field=f.name)
        return text
    if not (f.min or 0) <= len(text) <= f.max:
        raise refuse("length", field=f.name, min=f.min or 0, max=f.max)
    return text


def parse(db: DbSession, kind: Kind, raw: dict, row: object | None) -> dict:
    """The fields the form sent, checked; adding a row needs every required one."""
    names = {f.name for f in kind.fields}
    for k in raw:
        if k not in names:
            raise refuse("unknown_field", field=k)
    out = {}
    for f in kind.fields:
        if f.name not in raw:
            if row is None and f.required:
                raise refuse("required", field=f.name)
            continue
        value = _value(db, f, raw[f.name])
        if f.fixed and row is not None:
            if value != getattr(row, f.name):
                raise refuse("fixed", field=f.name)
            continue
        if f.unique and value is not None:
            col = getattr(kind.model, f.name)
            if db.scalar(select(kind.model.id).where(col == value, kind.model.id != (row.id if row else 0))):
                raise refuse("duplicate", field=f.name)
        out[f.name] = value
    return out


def shown_value(f: Field, value: object) -> object:
    if isinstance(value, datetime):
        return value.astimezone(EVENT_TZ).strftime("%Y-%m-%dT%H:%M")
    return value


def row_out(kind: Kind, row: object, extra: dict) -> dict:
    values = {f.name: shown_value(f, getattr(row, f.name)) for f in kind.fields if f.type != "secret"}
    if isinstance(row, Task) and row.coins_from_rule:
        # A blank coins cell follows the rule, as in the Excel file
        values["coins"] = None
    return {"id": row.id, "version": row.version, "values": values, "extra": extra}


def schema(db: DbSession, kind: Kind) -> list[dict]:
    out = []
    for f in kind.fields:
        options = None
        if f.ref:
            ref = KINDS[f.ref]
            q = select(ref.model).order_by(*ref.order())
            if f.where is not None:
                q = q.where(f.where())
            options = [{"id": r.id, "label": changes.label(db, r) + (f" · {r.text[:60]}" if isinstance(r, Task) else ""),
                        "active": getattr(r, "active", True)} for r in db.scalars(q)]
        out.append({"name": f.name, "type": f.type, "required": f.required, "min": f.min, "max": f.max,
                    "choices": list(f.choices), "options": options, "effect": f.effect, "fixed": f.fixed})
    return out


# Stages ----------------------------------------------------------------------------------------------------------

def _stage_check(db: DbSession, s: Stage, creating: bool) -> None:
    if s.ends_at <= s.starts_at:
        raise refuse("end_before_start", field="ends_at")


def _day(db: DbSession, row: object | None) -> tuple:
    d = stages.day(db)
    return d.state, d.current.number if d.current else None


def _stage_impact(db: DbSession, row: object, before: tuple, gone: bool) -> list[dict]:
    """A save that ends the running stage or starts another changes what every guest sees."""
    after = _day(db, None)
    if after == before:
        return []
    return [{"code": "stage_change", "from": before[1], "to": after[1]}]


def _stage_keep(db: DbSession, s: Stage) -> str | None:
    """A stage with tasks, or one past points were earned in (deleting it would blank their stage), stays."""
    used = (exists().where(Task.stage_id == s.id), exists().where(ScoreEvent.stage_id == s.id))
    return "in_use" if any(db.scalar(select(u)) for u in used) else None


# Tasks -----------------------------------------------------------------------------------------------------------

def _task_check(db: DbSession, t: Task, creating: bool) -> None:
    if t.window_start and t.window_end and t.window_end <= t.window_start:
        raise refuse("bad_window", field="window_end")
    if t.method == "link":
        if not t.link:
            raise refuse("required", field="link")
        if not re.match(r"https?://\S+$", t.link):
            raise refuse("bad_link", field="link")
    if t.method != "quiz" and (t.timer_seconds is not None or t.requires_task_id is not None):
        raise refuse("quiz_only", field="timer_seconds" if t.timer_seconds is not None else "requires_task_id")
    if t.requires_task_id is not None and t.requires_task_id == t.id:
        raise refuse("bad_value", field="requires_task_id")
    # A quiz gated on a switched-off QR task could never open, and the file couldn't write its «Требует» back
    if not t.active and t.id and db.scalar(select(exists().where(Task.requires_task_id == t.id, Task.active))):
        raise refuse("required_by", field="active")


def _task_after(db: DbSession, t: Task, changed: dict) -> None:
    if t.method != "link":
        t.link = ""
    # A blank coins field follows the rule, like a blank coins cell in the file
    if "coins" in changed or t.coins is None:
        t.coins_from_rule = changed.get("coins") is None
    if t.coins_from_rule:
        t.coins = rule_coins(t.points, t.partner_id is not None, settings.get(db, "partner_coin_multiplier"))
    if t.method == "qr" and not t.qr_code:
        from app.task_file import _new_qr
        t.qr_code = _new_qr(db)


def _task_keep(db: DbSession, t: Task) -> str | None:
    used = (exists().where(ScoreEvent.reason == f"task:{t.id}"), exists().where(Submission.task_id == t.id),
            exists().where(QuizAttempt.task_id == t.id), exists().where(Task.requires_task_id == t.id))
    return "in_use" if any(db.scalar(select(u)) for u in used) else None


def _task_state(db: DbSession, t: Task | None) -> bool:
    from app.routers.feed import available
    return t is not None and available(db, t)


def _task_impact(db: DbSession, t: Task, before: bool, gone: bool) -> list[dict]:
    """Switching off (or moving, or deleting) a task guests can do right now takes it off their phones."""
    if before and (gone or not _task_state(db, t)):
        done = db.scalar(select(func.count()).where(ScoreEvent.reason == f"task:{t.id}"))
        return [{"code": "task_off", "item": t.code, "done": done}]
    return []


# Prizes ----------------------------------------------------------------------------------------------------------

def _prize_check(db: DbSession, p: Prize, creating: bool) -> None:
    bought = 0 if creating else sold(db, p.id)
    if p.quantity < bought:
        raise refuse("below_sold", field="quantity", min=bought)


def _market_open(db: DbSession) -> bool:
    opens_at = stages.market_opens_at(db)
    return opens_at is not None and stages.now() >= opens_at


def _prize_impact(db: DbSession, p: Prize, before: bool, gone: bool) -> list[dict]:
    if before and (gone or not p.active):
        return [{"code": "prize_off", "item": p.name}]
    return []


# Questions -------------------------------------------------------------------------------------------------------

def _question_check(db: DbSession, q: Question, creating: bool) -> None:
    if db.scalar(select(Task.method).where(Task.id == q.task_id)) != "quiz":
        raise refuse("not_a_quiz", field="task_id")
    options = [q.option1, q.option2, q.option3, q.option4]
    if q.option4 and not q.option3:
        raise refuse("required", field="option3")
    count = sum(1 for o in options if o)
    if q.correct > count:
        raise refuse("out_of_range", field="correct", min=1, max=count)
    if db.scalar(select(Question.id).where(Question.task_id == q.task_id, Question.number == q.number,
                                           Question.id != (q.id or 0))):
        raise refuse("duplicate", field="number")


def _question_lock(db: DbSession, q: Question) -> None:
    from app.routers.quiz import running
    task = db.get(Task, q.task_id)
    if task is not None and running(db, task):
        raise refuse("quiz_running", status=409)


# Levels ----------------------------------------------------------------------------------------------------------

def _level_check(db: DbSession, lv: Level, creating: bool) -> None:
    # Every guest has a level: the one from 0 points stays
    if not db.scalar(select(Level.id).where(Level.min_points == 0, Level.id != (lv.id or 0))) and lv.min_points != 0:
        raise refuse("zero_level", field="min_points")


def _level_keep(db: DbSession, lv: Level) -> str | None:
    return "zero_level" if lv.min_points == 0 else None


# Partners --------------------------------------------------------------------------------------------------------

def _partner_keep(db: DbSession, p: Partner) -> str | None:
    used = db.scalar(select(exists().where(Task.partner_id == p.id))) or db.scalar(
        select(exists().where(Prize.partner_id == p.id)))
    return "in_use" if used else None


def _partner_extra(db: DbSession, rows: list) -> dict[int, dict]:
    with_logo = set(db.scalars(select(Partner.id).where(Partner.logo.is_not(None))))
    return {p.id: {"logo": p.id in with_logo} for p in rows}


# Staff -----------------------------------------------------------------------------------------------------------

def _other_admin(db: DbSession, s: Staff) -> bool:
    """Whether an active admin other than this one is left. The lock makes a second save wait for the first to commit,
    then count again."""
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": ADMINS_LOCK})
    return db.scalar(select(exists().where(Staff.role == "admin", Staff.active, Staff.id != (s.id or 0))))


def _staff_check(db: DbSession, s: Staff, creating: bool) -> None:
    if creating and s.role in SHARED and db.scalar(select(Staff.id).where(Staff.role == s.role, Staff.id != (s.id or 0))):
        raise refuse("shared_exists", field="role")
    if not s.active and s.role == "admin" and not _other_admin(db, s):
        raise refuse("last_admin", field="active")


def _staff_after(db: DbSession, s: Staff, changed: dict) -> None:
    # Switching an account off ends its sessions: its next action is refused
    if not s.active:
        db.flush()
        db.execute(delete(Session).where(Session.staff_id == s.id))


def _staff_keep(db: DbSession, s: Staff) -> str | None:
    if s.role in SHARED:
        return "shared_account"
    if s.role == "admin" and s.active and not _other_admin(db, s):
        return "last_admin"
    return "in_use" if db.scalar(select(exists().where(ChangeEvent.staff_id == s.id))) else None


def set_secret(db: DbSession, s: Staff, secret: str) -> None:
    if accounts.taken(db, s.role, secret, s.id):
        raise refuse("secret_taken", field="secret")
    s.secret_hash = accounts.hash_secret(secret)


KINDS: dict[str, Kind] = {
    "stages": Kind(
        Stage,
        [Field("number", "int", True, *LIMITS["stages", "number"], unique=True),
         Field("name", "text", True, *LIMITS["stages", "name"]),
         Field("starts_at", "datetime", True), Field("ends_at", "datetime", True),
         Field("message", "text", max=LIMITS["stages", "message"][1]), Field("market", "bool"), Field("active", "bool")],
        lambda: [Stage.number],
        check=_stage_check,
        keep=_stage_keep,
        state=_day, impact=_stage_impact),
    "tasks": Kind(
        Task,
        [Field("code", "text", True, *LIMITS["tasks", "code"], unique=True), Field("stage_id", "ref", True, ref="stages"),
         Field("type", "choice", True, choices=tuple(TYPES)), Field("text", "text", True, *LIMITS["tasks", "text"]),
         Field("points", "int", True, *LIMITS["tasks", "points"]), Field("coins", "int", False, *LIMITS["tasks", "coins"]),
         Field("partner_id", "ref", ref="partners"), Field("method", "choice", choices=("", *METHODS)),
         Field("link", "text", max=LIMITS["tasks", "link"][1]), Field("window_start", "datetime"), Field("window_end", "datetime"),
         Field("timer_seconds", "int", False, *LIMITS["tasks", "timer_seconds"]),
         Field("requires_task_id", "ref", ref="tasks", where=lambda: (Task.method == "qr") & Task.active),
         Field("active", "bool")],
        lambda: [Task.position, Task.id],
        check=_task_check, keep=_task_keep, state=_task_state, impact=_task_impact, after=_task_after,
        extra=lambda db, rows: {t.id: {"qr_code": t.qr_code} for t in rows}),
    "prizes": Kind(
        Prize,
        [Field("code", "text", True, *LIMITS["prizes", "code"], unique=True),
         Field("name", "text", True, *LIMITS["prizes", "name"]), Field("partner_id", "ref", True, ref="partners"),
         Field("price", "int", True, *LIMITS["prizes", "price"]), Field("quantity", "int", True, *LIMITS["prizes", "quantity"]),
         Field("active", "bool")],
        lambda: [Prize.position, Prize.id],
        check=_prize_check,
        keep=lambda db, p: "in_use" if sold(db, p.id) else None,
        state=lambda db, p: p is not None and p.active and _market_open(db), impact=_prize_impact,
        extra=lambda db, rows: {p.id: {"sold": sold(db, p.id)} for p in rows}),
    "questions": Kind(
        Question,
        [Field("task_id", "ref", True, ref="tasks", where=lambda: Task.method == "quiz", effect="locked"),
         Field("number", "int", True, *LIMITS["questions", "number"], effect="locked"),
         Field("text", "text", True, *LIMITS["questions", "text"], effect="locked"),
         Field("option1", "text", True, *LIMITS["questions", "option"], effect="locked"),
         Field("option2", "text", True, *LIMITS["questions", "option"], effect="locked"),
         Field("option3", "text", max=LIMITS["questions", "option"][1], effect="locked", null=True),
         Field("option4", "text", max=LIMITS["questions", "option"][1], effect="locked", null=True),
         Field("correct", "int", True, 1, 4, effect="locked")],
        lambda: [Question.task_id, Question.number],
        check=_question_check, lock=_question_lock),
    "levels": Kind(
        Level,
        [Field("name", "text", True, *LIMITS["levels", "name"], effect="recheck"),
         Field("min_points", "int", True, *LIMITS["levels", "min_points"], effect="recheck", unique=True)],
        lambda: [Level.min_points],
        check=_level_check, keep=_level_keep),
    "partners": Kind(
        Partner,
        [Field("name", "text", True, *LIMITS["partners", "name"], unique=True), Field("package", "choice", choices=("", *PACKAGES)),
         Field("active", "bool")],
        lambda: [Partner.name],
        keep=_partner_keep, extra=_partner_extra),
    "staff": Kind(
        Staff,
        [Field("name", "text", True, 1, 100), Field("role", "choice", True, choices=ROLES, fixed=True),
         Field("secret", "secret", min=4, max=72), Field("active", "bool")],
        lambda: [Staff.role, Staff.name],
        check=_staff_check, keep=_staff_keep, after=_staff_after, secret_fields=("secret",)),
}
