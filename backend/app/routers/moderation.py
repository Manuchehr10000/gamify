import math
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session as DbSession

from app import accounts, badges, ledger, levels, rating, settings, stages
from app.auth import current_moderator, start_session
from app.db import get_db
from app.models import Guest, ScoreEvent, Submission, Task
from app.routers.feed import task_reason
from app.routers.market import local

# Moderators check photo and text submissions on a tablet. Points were counted on sending (post-moderation):
# a decision keeps them, adds a bonus or takes them back
router = APIRouter()


class Login(BaseModel):
    secret: str


class ModeratorToken(BaseModel):
    token: str
    name: str


@router.post("/api/moderator/login")
def login(body: Login, db: DbSession = Depends(get_db)) -> ModeratorToken:
    # The PIN alone says which moderator it is; no moderator accounts: nobody can log in
    account = accounts.find(db, "moderator", body.secret)
    if account is None:
        raise HTTPException(401, "wrong_secret")
    return ModeratorToken(token=start_session(db, account), name=account.name)


class Item(BaseModel):
    id: int
    task: str
    points: int
    # First name and last initial
    guest: str
    text: str
    photo: bool
    created_at: datetime


class Queue(BaseModel):
    moderator: str
    waiting: int
    # How long the oldest waiting submission has waited; None when nothing waits
    oldest_seconds: int | None
    items: list[Item]


@router.get("/api/moderation/queue")
def queue(top20: bool = False, name: str = Depends(current_moderator), db: DbSession = Depends(get_db)) -> Queue:
    where = [Submission.status == ""]
    if top20:
        # The current top of the ranking (20 unless the admin set another number), for the check before the ceremony
        top = rating.ranking().limit(settings.number(db, "moderation_top")).subquery()
        where.append(Submission.guest_id.in_(select(top.c.guest_id)))
    waiting, oldest = db.execute(select(func.count(), func.min(Submission.created_at)).where(*where)).one()
    # The points sending it earned, the base of the moderator's bonus, even if the task file was uploaded again since
    award = ((ScoreEvent.guest_id == Submission.guest_id)
             & (ScoreEvent.reason == "task:" + cast(Submission.task_id, String)) & ledger.standing())
    rows = db.execute(
        select(Submission.id, Task.text, func.coalesce(ScoreEvent.points, Task.points), Guest.first_name,
               Guest.last_name, Submission.text, Submission.photo.isnot(None), Submission.created_at)
        .join(Task, Task.id == Submission.task_id).join(Guest, Guest.id == Submission.guest_id)
        .outerjoin(ScoreEvent, award)
        .where(*where).order_by(Submission.created_at.desc(), Submission.id.desc())
    )
    # The server's clock, so a tablet set to the wrong time still shows the right age
    oldest_seconds = max(0, int((stages.now() - oldest).total_seconds())) if oldest else None
    return Queue(
        moderator=name,
        waiting=waiting,
        oldest_seconds=oldest_seconds,
        items=[Item(id=sid, task=task, points=points, guest=rating.guest_name(first, last), text=text, photo=photo,
                    created_at=local(created)) for sid, task, points, first, last, text, photo, created in rows],
    )


@router.get("/api/submissions/{submission_id}/photo", dependencies=[Depends(current_moderator)])
def photo(submission_id: int, db: DbSession = Depends(get_db)) -> Response:
    data = db.scalar(select(Submission.photo).where(Submission.id == submission_id))
    if data is None:
        raise HTTPException(404, "photo_not_found")
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


class DecisionIn(BaseModel):
    action: Literal["accept", "bonus", "retake", "penalty"]


STATUS = {"accept": "accepted", "bonus": "bonus", "retake": "retake", "penalty": "penalty"}


class Decision(BaseModel):
    # decided: this decision counts · already: another moderator decided it first
    result: str
    status: str
    moderator: str
    decided_at: datetime | None


@router.post("/api/submissions/{submission_id}/decision")
def decide(submission_id: int, body: DecisionIn, name: str = Depends(current_moderator),
           db: DbSession = Depends(get_db)) -> Decision:
    # Locked: of two moderators deciding at once, the second waits, then finds it decided
    s = db.scalar(select(Submission).where(Submission.id == submission_id).with_for_update())
    if s is None:
        raise HTTPException(404, "submission_not_found")
    if s.status:
        return Decision(result="already", status=s.status, moderator=s.moderator, decided_at=local(s.decided_at))
    # What sending it earned, which may differ from the task now if the file was uploaded again since
    award = ledger.award(db, s.guest_id, task_reason(s.task_id))
    points = award.points if award else 0
    if body.action == "bonus":
        # A share of the points, rounded up: +50% unless the admin set another one
        share = settings.get(db, "moderator_bonus_percent")
        ledger.write(db, s.guest_id, f"bonus:{s.id}", "bonus", math.ceil(points * share / 100), 0)
    elif body.action == "retake" and award:
        # A reversal row takes the award back and reopens the task: the guest's next submission is awarded afresh
        ledger.take_back(db, award, f"retake:{s.id}", "retake", reverse=True)
    elif body.action == "penalty" and award:
        # The award stays, so the task stays closed; this takes its points and coins back. Coins may go below zero
        ledger.take_back(db, award, f"penalty:{s.id}", "penalty", reverse=False)
    if body.action in ("retake", "penalty"):
        db.flush()
        levels.dropped(db, s.guest_id)
    s.status, s.moderator, s.decided_at = STATUS[body.action], name, stages.now()
    if body.action in ("retake", "penalty"):
        # A rejected submission no longer counts towards a badge
        db.flush()
        badges.lost(db, s.guest_id)
    db.commit()
    return Decision(result="decided", status=s.status, moderator=s.moderator, decided_at=local(s.decided_at))
