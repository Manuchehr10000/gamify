import csv
import io
from datetime import timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import String, cast, exists, func, or_, select, union
from sqlalchemy.orm import Session as DbSession

from app import ledger, push, settings, stages
from app.auth import require_role
from app.db import get_db
from app.models import Guest, Partner, Prize, Redemption, ScoreEvent, Session, Stage, Submission, Task
from app.task_file import PACKAGES

# The organizer's live numbers during the forum, and the partners' report after it
router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_role("admin"))])

def completions():
    """(guest_id, task_id) for every task a guest has done. A task sent back for a retake has its award reversed;
    a submission rejected with a penalty keeps its award, so it is left out here."""
    # Kept as text: the task's ID after «task:», compared with the ID written out, never cast
    task_id = func.substr(ScoreEvent.reason, 6)
    penalized = exists().where(Submission.guest_id == ScoreEvent.guest_id, Submission.status == "penalty",
                               cast(Submission.task_id, String) == task_id)
    return (select(ScoreEvent.guest_id.label("guest_id"), task_id.label("task_id"))
            .where(ScoreEvent.reason.like("task:%"), ledger.standing(), ~penalized).subquery())


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
    # Pushes: active subscriptions, accepted by the push service, reported arrived by phones, refused or gone
    push_opt_ins: int
    push_sends: int
    push_deliveries: int
    push_failures: int


@router.get("/live")
def live(db: DbSession = Depends(get_db)) -> Live:
    logged_in = db.scalar(select(func.count(func.distinct(Session.guest_id))).where(Session.role == "guest"))
    # Active: did a task, sent a submission or bought something lately. Arriving (+10) is part of logging in
    since = stages.now() - timedelta(minutes=settings.number(db, "active_window_minutes"))
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
        select(Partner.name, func.count(), func.count(func.distinct(done.c.guest_id)))
        .select_from(Task).join(done, on).join(Partner, Partner.id == Task.partner_id)
        .group_by(Partner.id).order_by(func.count().desc(), Partner.name)).all()

    waiting, oldest = db.execute(select(func.count(), func.min(Submission.created_at))
                                 .where(Submission.status == "")).one()
    sold = dict(db.execute(select(Redemption.prize_id, func.count()).group_by(Redemption.prize_id)).all())
    issued = db.scalar(select(func.count()).where(Redemption.issued_at.is_not(None)))
    left = sum(max(0, p.quantity - sold.get(p.id, 0)) for p in db.scalars(select(Prize).where(Prize.active)))
    pushes = push.counts(db)
    return Live(
        logged_in=logged_in,
        active=active,
        by_type=[Count(name=t, completions=n) for t, n in by_type],
        by_stage=[StageCount(number=s.number, name=s.name, completions=stage_counts.get(s.id, 0))
                  for s in db.scalars(select(Stage).where(Stage.active).order_by(Stage.number))],
        partners=[PartnerCount(partner=p, completions=n, guests=g) for p, n, g in partners],
        waiting=waiting,
        oldest_seconds=max(0, int((stages.now() - oldest).total_seconds())) if oldest else None,
        bought=sum(sold.values()),
        issued=issued,
        left=left,
        push_opt_ins=pushes.opt_ins,
        push_sends=pushes.sends,
        push_deliveries=pushes.deliveries,
        push_failures=pushes.failures,
    )


REPORT_HEAD = ["Партнёр", "Пакет", "Задание", "Выполнений", "Уникальных участников"]


def cell(text: str) -> str:
    """Excel reads a cell starting with = + - @ as a formula, so such text gets a leading apostrophe."""
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


@router.get("/partners/export")
def partners_export(db: DbSession = Depends(get_db)) -> Response:
    done = completions()
    rows = db.execute(
        select(Partner.name, Partner.package, Task.text, func.count(done.c.guest_id),
               func.count(func.distinct(done.c.guest_id)))
        .select_from(Task).join(Partner, Partner.id == Task.partner_id)
        .outerjoin(done, done.c.task_id == cast(Task.id, String))
        .group_by(Task.id, Partner.id).having(Task.active | (func.count(done.c.guest_id) > 0))
        .order_by(Partner.name, Task.position, Task.id)).all()
    out = io.StringIO()
    # Semicolons and a BOM so Excel opens Cyrillic correctly
    w = csv.writer(out, delimiter=";")
    w.writerow(REPORT_HEAD)
    for partner, package, text, n, guests in rows:
        w.writerow([cell(partner), cell(PACKAGES[package][0] if package else ""), cell(text), n, guests])
    return Response("﻿" + out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="partners.csv"'})


class Mismatch(BaseModel):
    name: str
    # Stored on the guest, and the sum of their score_events
    points: int
    points_sum: int
    coins: int
    coins_sum: int


@router.get("/balance-check")
def balance_check(db: DbSession = Depends(get_db)) -> list[Mismatch]:
    """Guests whose stored totals differ from the sum of their events. Only reports; changes nothing."""
    sums = (select(ScoreEvent.guest_id, func.sum(ScoreEvent.points).label("points_sum"),
                   func.sum(ScoreEvent.coins).label("coins_sum")).group_by(ScoreEvent.guest_id).subquery())
    points, coins = func.coalesce(sums.c.points_sum, 0), func.coalesce(sums.c.coins_sum, 0)
    rows = db.execute(select(Guest, points, coins).outerjoin(sums, sums.c.guest_id == Guest.id)
                      .where(or_(Guest.points != points, Guest.coins != coins))
                      .order_by(Guest.last_name, Guest.first_name, Guest.id)).all()
    return [Mismatch(name=f"{g.first_name} {g.last_name}".strip(), points=g.points, points_sum=int(p),
                     coins=g.coins, coins_sum=int(c)) for g, p, c in rows]
