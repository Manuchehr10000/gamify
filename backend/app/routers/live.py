import csv
import io
from datetime import timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import String, cast, exists, func, select, union
from sqlalchemy.orm import Session as DbSession

from app import stages
from app.auth import require_role
from app.db import get_db
from app.models import Prize, Redemption, ScoreEvent, Session, Stage, Submission, Task
from app.task_file import PACKAGES

# The organizer's live numbers during the forum, and the partners' report after it
router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_role("admin"))])

ACTIVE_WINDOW = timedelta(minutes=15)


def completions():
    """(guest_id, task_id) for every task a guest has done. A task sent back for a retake has no award;
    a submission rejected with a penalty keeps its award, so it is left out here."""
    # Kept as text: the task's ID after «task:», compared with the ID written out, never cast
    task_id = func.substr(ScoreEvent.reason, 6)
    penalized = exists().where(Submission.guest_id == ScoreEvent.guest_id, Submission.status == "penalty",
                               cast(Submission.task_id, String) == task_id)
    return (select(ScoreEvent.guest_id.label("guest_id"), task_id.label("task_id"))
            .where(ScoreEvent.reason.like("task:%"), ~penalized).subquery())


class Count(BaseModel):
    name: str
    completions: int


class StageCount(BaseModel):
    number: int
    name: str
    completions: int


class PartnerCount(BaseModel):
    partner: str
    completions: int
    guests: int


class Live(BaseModel):
    logged_in: int
    active: int
    # Keyed by the task type (quiz, selfie, …); types nobody has done are left out
    by_type: list[Count]
    by_stage: list[StageCount]
    partners: list[PartnerCount]
    waiting: int
    # How long the oldest waiting submission has waited; None when nothing waits
    oldest_seconds: int | None
    bought: int
    issued: int
    left: int


@router.get("/live")
def live(db: DbSession = Depends(get_db)) -> Live:
    logged_in = db.scalar(select(func.count(func.distinct(Session.guest_id))).where(Session.role == "guest"))
    # Active: did a task, sent a submission or bought something lately. Arriving (+10) is part of logging in
    since = stages.now() - ACTIVE_WINDOW
    recent = union(
        select(ScoreEvent.guest_id).where(ScoreEvent.reason.like("task:%"), ScoreEvent.created_at >= since),
        select(Submission.guest_id).where(Submission.created_at >= since),
        select(Redemption.guest_id).where(Redemption.created_at >= since),
    ).subquery()
    active = db.scalar(select(func.count()).select_from(recent))

    done = completions()
    on = done.c.task_id == cast(Task.id, String)
    by_type = db.execute(select(Task.type, func.count()).join(done, on)
                         .group_by(Task.type).order_by(func.count().desc(), Task.type)).all()
    stage_counts = dict(db.execute(select(Task.stage_id, func.count()).join(done, on).group_by(Task.stage_id)).all())
    partners = db.execute(
        select(Task.partner_name, func.count(), func.count(func.distinct(done.c.guest_id)))
        .join(done, on).where(Task.partner_name != "")
        .group_by(Task.partner_name).order_by(func.count().desc(), Task.partner_name)).all()

    waiting, oldest = db.execute(select(func.count(), func.min(Submission.created_at))
                                 .where(Submission.status == "")).one()
    sold = dict(db.execute(select(Redemption.prize_id, func.count()).group_by(Redemption.prize_id)).all())
    issued = db.scalar(select(func.count()).where(Redemption.issued_at.is_not(None)))
    left = sum(max(0, p.quantity - sold.get(p.id, 0)) for p in db.scalars(select(Prize).where(Prize.active)))
    return Live(
        logged_in=logged_in,
        active=active,
        by_type=[Count(name=t, completions=n) for t, n in by_type],
        by_stage=[StageCount(number=s.number, name=s.name, completions=stage_counts.get(s.id, 0))
                  for s in db.scalars(select(Stage).order_by(Stage.number))],
        partners=[PartnerCount(partner=p, completions=n, guests=g) for p, n, g in partners],
        waiting=waiting,
        oldest_seconds=max(0, int((stages.now() - oldest).total_seconds())) if oldest else None,
        bought=sum(sold.values()),
        issued=issued,
        left=left,
    )


REPORT_HEAD = ["Партнёр", "Пакет", "Задание", "Выполнений", "Уникальных участников"]


def cell(text: str) -> str:
    """Excel reads a cell starting with = + - @ as a formula, so such text gets a leading apostrophe."""
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


@router.get("/partners/export")
def partners_export(db: DbSession = Depends(get_db)) -> Response:
    done = completions()
    rows = db.execute(
        select(Task.partner_name, Task.partner_package, Task.text, func.count(done.c.guest_id),
               func.count(func.distinct(done.c.guest_id)))
        .outerjoin(done, done.c.task_id == cast(Task.id, String)).where(Task.partner_name != "")
        .group_by(Task.id).having(Task.active | (func.count(done.c.guest_id) > 0))
        .order_by(Task.partner_name, Task.position, Task.id)).all()
    out = io.StringIO()
    # Semicolons and a BOM so Excel opens Cyrillic correctly
    w = csv.writer(out, delimiter=";")
    w.writerow(REPORT_HEAD)
    for partner, package, text, n, guests in rows:
        w.writerow([cell(partner), cell(PACKAGES[package][0] if package else ""), cell(text), n, guests])
    return Response("﻿" + out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="partners.csv"'})
