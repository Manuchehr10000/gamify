import csv
import io
from collections import defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from openpyxl import Workbook
from pydantic import BaseModel
from sqlalchemy import String, cast, exists, func, or_, select, union
from sqlalchemy.orm import Session as DbSession

from app import config, ledger, photos, push, rating, settings, stages
from app.auth import require_role
from app.db import get_db
from app.models import (Guest, LogoShow, Partner, Prize, Redemption, ScoreEvent, Session, Stage, Submission,
                        Task)
from app.routers.admin_tasks import XLSX
from app.stages import EVENT_TZ
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
    return (select(ScoreEvent.guest_id.label("guest_id"), task_id.label("task_id"), ScoreEvent.created_at.label("at"))
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


# A moderator's «Переснять» or «Штраф»: the result does not count; each sent-back retake is counted once
REJECTED = ("retake", "penalty")
# The only photos a partner sees, in «Фото» and behind its link
SHOWN = ("accepted", "bonus")


def _append(ws, values: list) -> None:
    """A row with every text cell written as text: openpyxl reads only a leading = as a formula, so such a cell is
    stored as a string (+ - @ are already text in .xlsx; an apostrophe as in the CSV would show in the cell)."""
    ws.append(values)
    for c in ws[ws.max_row]:
        if c.data_type == "f":
            c.data_type = "s"


def _local(at):
    return at.astimezone(EVENT_TZ).replace(tzinfo=None)


@router.get("/partners/{partner_id}/report")
def partner_report(partner_id: int, db: DbSession = Depends(get_db)) -> Response:
    """One partner's file after the forum: «Сводка», «Детали» by hour and «Фото» links. Tasks and prizes follow
    their partner now; counts are /admin/live's. No guest names anywhere."""
    p = db.get(Partner, partner_id)
    if p is None:
        raise HTTPException(404, "partner_not_found")
    tasks = db.execute(select(Task, Stage).join(Stage, Stage.id == Task.stage_id).where(Task.partner_id == p.id)
                       .order_by(Task.position, Task.id)).all()
    ids = [t.id for t, _ in tasks]
    done = completions()
    # Completions as /admin/live counts them, and the rejected sends, each with its time
    finished = db.execute(select(done.c.guest_id, done.c.task_id, done.c.at)
                          .where(done.c.task_id.in_([str(i) for i in ids]))).all()
    rejected = db.execute(select(Submission.task_id, Submission.created_at)
                          .where(Submission.task_id.in_(ids), Submission.status.in_(REJECTED))).all()
    per_task: dict[int, list[int]] = defaultdict(list)
    # (task, local hour) → the guests who finished then, and the rejected count
    per_hour: dict[tuple[int, object], list] = defaultdict(lambda: [[], 0])
    for guest_id, task_id, at in finished:
        per_task[int(task_id)].append(guest_id)
        per_hour[int(task_id), _local(at).replace(minute=0, second=0, microsecond=0)][0].append(guest_id)
    rejected_per_task: dict[int, int] = defaultdict(int)
    for task_id, at in rejected:
        rejected_per_task[task_id] += 1
        per_hour[task_id, _local(at).replace(minute=0, second=0, microsecond=0)][1] += 1
    # As the CSV: switched-off tasks only when something happened on them
    listed = [(t, st) for t, st in tasks if t.active or per_task[t.id] or rejected_per_task[t.id]]

    wb = Workbook()
    ws = wb.active
    ws.title = "Сводка"
    package = PACKAGES[p.package][0] if p.package else "—"
    _append(ws, [f"Отчёт партнёра: {p.name}"])
    _append(ws, ["Пакет", package])
    _append(ws, ["Сформирован", _local(stages.now())])
    ws["B3"].number_format = "DD.MM.YYYY HH:MM"
    if not rating.frozen(db):
        _append(ws, ["Предварительные данные: итоги форума ещё не зафиксированы"])
    until = photos.delete_date(db)
    _append(ws, [f"Ссылки на фото работают до {until:%d.%m.%Y}" if until else "Ссылки на фото работают до —"])
    ws.append([])
    _append(ws, ["Задание", "Этап", "Выполнений", "Уникальных участников", "Отклонено"])
    for t, st in listed:
        _append(ws, [t.text, f"{st.number}. {st.name}", len(per_task[t.id]), len(set(per_task[t.id])),
                     rejected_per_task[t.id]])
    # Unique guests across all the partner's tasks, as /admin/live
    _append(ws, ["Итого", "", len(finished), len({g for g, _, _ in finished}), len(rejected)])
    ws.append([])

    sold = dict(db.execute(select(Redemption.prize_id, func.count()).join(Prize, Prize.id == Redemption.prize_id)
                           .where(Prize.partner_id == p.id).group_by(Redemption.prize_id)).all())
    issued = dict(db.execute(select(Redemption.prize_id, func.count()).join(Prize, Prize.id == Redemption.prize_id)
                             .where(Prize.partner_id == p.id, Redemption.issued_at.is_not(None))
                             .group_by(Redemption.prize_id)).all())
    _append(ws, ["Приз", "Куплено", "Выдано на стендах"])
    for prize in db.scalars(select(Prize).where(Prize.partner_id == p.id).order_by(Prize.position, Prize.id)):
        if prize.active or sold.get(prize.id):
            _append(ws, [prize.name, sold.get(prize.id, 0), issued.get(prize.id, 0)])
    _append(ws, ["Итого", sum(sold.values()), sum(issued.values())])
    ws.append([])

    shows, seconds = db.execute(select(func.count(), func.coalesce(func.sum(LogoShow.seconds), 0))
                                .where(LogoShow.partner_id == p.id)).one()
    _append(ws, ["Логотип на экране в зале", "Пакет", "Показов", "Секунд"])
    _append(ws, ["", package, shows, int(seconds)])
    ws.append([])
    pushes = push.counts(db)
    _append(ws, ["Push-уведомления (весь форум)", "Подписаны", "Доставлено"])
    _append(ws, ["", pushes.opt_ins, pushes.deliveries])
    ws.column_dimensions["A"].width = 50

    wd = wb.create_sheet("Детали")
    _append(wd, ["Задание", "Этап", "Час", "Выполнений", "Уникальных участников", "Отклонено"])
    for t, st in listed:
        for hour in sorted(h for task_id, h in per_hour if task_id == t.id):
            guests, n_rejected = per_hour[t.id, hour]
            _append(wd, [t.text, f"{st.number}. {st.name}", hour, len(guests), len(set(guests)), n_rejected])
    for c in wd["C"][1:]:
        c.number_format = "DD.MM.YYYY HH:MM"
    wd.column_dimensions["A"].width = 50

    wf = wb.create_sheet("Фото")
    _append(wf, ["Задание", "Отправлено", "Ссылка"])
    sent = db.execute(select(Task.text, Submission.created_at, Submission.photo_token)
                      .join(Task, Task.id == Submission.task_id)
                      .where(Task.partner_id == p.id, Submission.status.in_(SHOWN), Submission.photo.is_not(None),
                             Submission.photo_token.is_not(None))
                      .order_by(Submission.created_at, Submission.id)).all()
    for text, at, token in sent:
        url = f"{config.PUBLIC_BASE_URL}/api/photos/{token}"
        _append(wf, [text, _local(at), url])
        wf.cell(wf.max_row, 3).hyperlink = url
    for c in wf["B"][1:]:
        c.number_format = "DD.MM.YYYY HH:MM"
    wf.column_dimensions["A"].width = 50
    wf.column_dimensions["C"].width = 60

    out = io.BytesIO()
    wb.save(out)
    # The name is set by the page; a Cyrillic header would not pass
    return Response(out.getvalue(), media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="partner-{p.id}.xlsx"'})


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
