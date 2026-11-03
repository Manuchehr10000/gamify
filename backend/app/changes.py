"""The admins' change log: every saved change records who, when, which item and field, the old and new value,
and whether it came from a form or an Excel upload. Rows are only ever added."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session as DbSession

from app.models import ChangeEvent, Partner, Prize, Question, Staff, Stage, Task
from app.stages import EVENT_TZ

CREATED = "_created"
DELETED = "_deleted"


def text(value: object) -> str | None:
    """A value as the log shows it: Dushanbe times, «да»/«нет», numbers without trailing zeros."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, datetime):
        return value.astimezone(EVENT_TZ).strftime("%d.%m.%Y %H:%M")
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    return str(value)


def record(db: DbSession, admin: Staff, kind: str, item_id: int | None, item: str, field: str,
           old: object = None, new: object = None, source: str = "form") -> None:
    """Add one log row in the caller's transaction, so a change and its log row commit or roll back together."""
    db.add(ChangeEvent(staff_id=admin.id, staff_name=admin.name, kind=kind, item_id=item_id, item=item[:200],
                       field=field, old_value=text(old), new_value=text(new), source=source))


def label(db: DbSession, row: object) -> str:
    """What the log calls an item: a task's or prize's ID, a stage's number and name, a name otherwise."""
    if isinstance(row, Stage):
        return f"{row.number}. {row.name}"
    if isinstance(row, (Task, Prize)):
        return row.code
    if isinstance(row, Question):
        task = db.get(Task, row.task_id)
        return f"{task.code if task else row.task_id} · {row.number}"
    return getattr(row, "name", "")


# Fields that point at another row: the log shows that row's label, not its number in the database
REFS = {"stage_id": Stage, "partner_id": Partner, "requires_task_id": Task, "task_id": Task}


def shown(db: DbSession, field: str, value: object) -> object:
    if field in REFS and value is not None:
        row = db.get(REFS[field], value)
        return label(db, row) if row is not None else value
    return value
