"""Quizzes: one question at a time, options shuffled, an optional countdown kept by the server.

/start opens the quiz or returns where the guest is in it (a reload continues, a finished quiz shows its result);
the quiz pays once, in proportion to the right answers, when it ends.
"""
import random
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DbSession

from app import ledger, stages
from app.auth import current_guest
from app.db import get_db
from app.models import Guest, Question, QuizAttempt, Task
from app.routers.feed import _done, available, task_reason

router = APIRouter(prefix="/api/quiz")


class Option(BaseModel):
    # The option's number in the file; the guest sends it back. It says nothing about which one is right
    n: int
    text: str


class QuestionOut(BaseModel):
    number: int
    text: str
    options: list[Option]


class Result(BaseModel):
    correct: int
    total: int
    points: int
    coins: int


class QuizState(BaseModel):
    text: str
    total: int
    answered: int
    # The next unanswered question; None once the quiz is over
    question: QuestionOut | None
    # Seconds until the countdown ends; None for a quiz without a timer or one that is over
    seconds_left: int | None
    result: Result | None


def _quiz(db: DbSession, task_id: int) -> Task:
    t = db.get(Task, task_id)
    if t is None or not t.active or t.method != "quiz":
        raise HTTPException(404, "quiz_not_found")
    return t


def _questions(db: DbSession, t: Task) -> list[Question]:
    return list(db.scalars(select(Question).where(Question.task_id == t.id).order_by(Question.number)))


def _attempt(db: DbSession, guest_id: int, task_id: int, lock: bool = False) -> QuizAttempt | None:
    q = select(QuizAttempt).where(QuizAttempt.guest_id == guest_id, QuizAttempt.task_id == task_id)
    # Locked, answer, finish and settle on one attempt run one after another and see each other's writes
    return db.scalar(q.with_for_update().execution_options(populate_existing=True) if lock else q)


def _deadline(t: Task, a: QuizAttempt) -> datetime | None:
    return a.started_at + timedelta(seconds=t.timer_seconds) if t.timer_seconds else None


def _expired(db: DbSession, t: Task, a: QuizAttempt) -> bool:
    """Time is up: the countdown ran out, or (without a timer) the quiz is no longer on."""
    deadline = _deadline(t, a)
    return stages.now() >= deadline if deadline else not available(db, t)


def _share(amount: int, correct: int, total: int) -> int:
    """Paid in proportion to the right answers, rounded up."""
    return (amount * correct + total - 1) // total if total else 0


def _finish(db: DbSession, t: Task, a: QuizAttempt, questions: list[Question]) -> None:
    """End the attempt (locked by the caller) and pay it once; unanswered questions count as wrong."""
    if a.finished_at is not None:
        return
    a.correct = sum(1 for q in questions if a.answers.get(str(q.number)) == q.correct)
    a.total = len(questions)
    a.finished_at = stages.now()
    # A zero score still marks the task done in the feed
    ledger.write(db, a.guest_id, task_reason(t.id), "task", _share(t.points, a.correct, a.total),
                 _share(t.coins, a.correct, a.total))
    db.commit()


def settle(db: DbSession, guest_id: int | None = None) -> None:
    """Pay quizzes whose time ran out while the quiz screen was closed: one guest's, or everyone's."""
    q = select(QuizAttempt.guest_id, Task).join(Task, QuizAttempt.task_id == Task.id).where(
        QuizAttempt.finished_at.is_(None))
    if guest_id is not None:
        q = q.where(QuizAttempt.guest_id == guest_id)
    for gid, t in db.execute(q).all():
        a = _attempt(db, gid, t.id, lock=True)
        if a is not None and a.finished_at is None and _expired(db, t, a):
            _finish(db, t, a, _questions(db, t))
        else:
            db.rollback()


def _options(a: QuizAttempt, q: Question) -> list[Option]:
    options = [Option(n=i, text=o) for i, o in enumerate((q.option1, q.option2, q.option3, q.option4), start=1) if o]
    # Seeded by the attempt: a reload shows the same order, another guest gets another one
    random.Random(f"{a.id}:{q.number}").shuffle(options)
    return options


def _state(db: DbSession, t: Task, a: QuizAttempt, questions: list[Question]) -> QuizState:
    answered = sum(1 for q in questions if str(q.number) in a.answers)
    if a.finished_at is not None:
        event = ledger.award(db, a.guest_id, task_reason(t.id))
        result = Result(correct=a.correct or 0, total=a.total or 0,
                        points=event.points if event else 0, coins=event.coins if event else 0)
        return QuizState(text=t.text, total=a.total or 0, answered=answered, question=None, seconds_left=None,
                         result=result)
    nxt = next((q for q in questions if str(q.number) not in a.answers), None)
    deadline = _deadline(t, a)
    left = max(0, int((deadline - stages.now()).total_seconds())) if deadline else None
    return QuizState(text=t.text, total=len(questions), answered=answered,
                     question=QuestionOut(number=nxt.number, text=nxt.text, options=_options(a, nxt)) if nxt else None,
                     seconds_left=left, result=None)


def _open_attempt(db: DbSession, guest: Guest, t: Task) -> tuple[QuizAttempt, list[Question]]:
    """The guest's attempt, ended first if its time is up."""
    a = _attempt(db, guest.id, t.id, lock=True)
    if a is None:
        raise HTTPException(409, "not_started")
    questions = _questions(db, t)
    if a.finished_at is None and _expired(db, t, a):
        _finish(db, t, a, questions)
    return a, questions


@router.post("/{task_id}/start")
def start(task_id: int, guest: Guest = Depends(current_guest), db: DbSession = Depends(get_db)) -> QuizState:
    t = _quiz(db, task_id)
    if _attempt(db, guest.id, t.id) is None:
        # Only a new attempt needs the quiz on now; a started one may be finished within its timer
        if t.requires_task_id is not None and task_reason(t.requires_task_id) not in _done(db, guest):
            raise HTTPException(403, "check_in_first")
        if not available(db, t):
            raise HTTPException(409, "unavailable")
        # Two phones of the same guest pressing «Начать» at once still make one attempt
        db.execute(insert(QuizAttempt).values(guest_id=guest.id, task_id=t.id, started_at=stages.now(), answers={})
                   .on_conflict_do_nothing(index_elements=["guest_id", "task_id"]))
        db.commit()
    a, questions = _open_attempt(db, guest, t)
    return _state(db, t, a, questions)


class AnswerIn(BaseModel):
    question: int
    option: int


@router.post("/{task_id}/answer")
def answer(task_id: int, body: AnswerIn, guest: Guest = Depends(current_guest),
           db: DbSession = Depends(get_db)) -> QuizState:
    t = _quiz(db, task_id)
    a, questions = _open_attempt(db, guest, t)
    # After the end (time up or finished) an answer is ignored; a retry of one already taken changes nothing
    if a.finished_at is not None or str(body.question) in a.answers:
        return _state(db, t, a, questions)
    nxt = next((q for q in questions if str(q.number) not in a.answers), None)
    if nxt is None or nxt.number != body.question:
        raise HTTPException(400, "wrong_question")
    if body.option not in {o.n for o in _options(a, nxt)}:
        raise HTTPException(400, "bad_option")
    a.answers = {**a.answers, str(body.question): body.option}
    # Saved and finished under the same lock, so a /finish sent at the same moment sees this answer
    if all(str(q.number) in a.answers for q in questions):
        _finish(db, t, a, questions)
    else:
        db.commit()
    return _state(db, t, a, questions)


@router.post("/{task_id}/finish")
def finish(task_id: int, guest: Guest = Depends(current_guest), db: DbSession = Depends(get_db)) -> QuizState:
    """The countdown reached zero on the phone, or the guest stops early: unanswered questions count as wrong."""
    t = _quiz(db, task_id)
    a, questions = _open_attempt(db, guest, t)
    _finish(db, t, a, questions)
    return _state(db, t, a, questions)
