"""Task limits: a task with «Лимит» N can be done by N guests in all. A guest holds a place in it with
- a photo or text task: an open claim (piece 14) still in time, or a submission not rejected with a penalty nor
  withdrawn by the guest («Отклонить — переснять» keeps the place, so that guest may send again even when the task
  is full);
- a quiz: an attempt, taken at «Начать» so nobody is cut off mid-timer;
- a QR, link or market task: having done it.
A place is checked and taken in one locked step (take), so two guests can't both take the last one."""
from collections.abc import Iterable

from sqlalchemy import and_, exists, select
from sqlalchemy.orm import Session as DbSession, aliased

from app import ledger, stages
from app.models import Claim, QuizAttempt, ScoreEvent, Submission, Task

SUBMIT_METHODS = {"photo", "text", "photo_text"}
# A submission rejected with a penalty, or withdrawn by the guest: its award stands (the task stays closed) but it
# counts for nothing: no place in the limit, no badge, no completion
CLOSED = ("penalty", "withdrawn")


def holders(db: DbSession, tasks: Iterable[Task]) -> dict[int, set[int]]:
    """The guests holding a place in each task that has a limit; tasks without one are left out."""
    limited = [t for t in tasks if t.limit is not None]
    out: dict[int, set[int]] = {t.id: set() for t in limited}
    submit = [t.id for t in limited if t.method in SUBMIT_METHODS]
    quiz = [t.id for t in limited if t.method == "quiz"]
    awards = {f"task:{t.id}": t.id for t in limited if t.method not in SUBMIT_METHODS and t.method != "quiz"}
    pairs: list[tuple[int, int]] = []
    if submit:
        pairs += db.execute(select(Claim.task_id, Claim.guest_id).where(
            Claim.task_id.in_(submit), Claim.state == "open", Claim.expires_at > stages.now())).all()
        # A penalty or a withdrawal is final (the task stays closed): it frees the place even if a retake came before
        penalty = aliased(Submission)
        pairs += db.execute(select(Submission.task_id, Submission.guest_id).where(
            Submission.task_id.in_(submit), Submission.status.not_in(CLOSED),
            ~exists().where(and_(penalty.task_id == Submission.task_id, penalty.guest_id == Submission.guest_id,
                                 penalty.status.in_(CLOSED))))).all()
    if quiz:
        pairs += db.execute(select(QuizAttempt.task_id, QuizAttempt.guest_id)
                            .where(QuizAttempt.task_id.in_(quiz))).all()
    if awards:
        rows = db.execute(select(ScoreEvent.reason, ScoreEvent.guest_id).where(
            ScoreEvent.reason.in_(list(awards)), ScoreEvent.action == "task", ledger.standing())).all()
        pairs += [(awards[reason], guest_id) for reason, guest_id in rows]
    for task_id, guest_id in pairs:
        out[task_id].add(guest_id)
    return out


def full(db: DbSession, guest_id: int, tasks: Iterable[Task]) -> set[int]:
    """The tasks whose places are all taken by other guests: «Временно недоступно» for this guest."""
    by_id = {t.id: t for t in tasks}
    return {task_id for task_id, guests in holders(db, by_id.values()).items()
            if guest_id not in guests and len(guests) >= by_id[task_id].limit}


def take(db: DbSession, guest_id: int, t: Task) -> bool:
    """Whether the guest may have a place in the task now. With a limit, the task's row stays locked until the
    caller commits what takes the place (the claim, the award, the attempt), so the next guest counts it. The
    caller locks the guest first (ledger.lock), the same order everywhere."""
    if t.limit is None:
        return True
    # FOR NO KEY UPDATE: guests taking places go one at a time, while rows that only point at the task don't wait
    # Read again under the lock: an admin may have just raised it
    limit = db.scalar(select(Task.limit).where(Task.id == t.id).with_for_update(key_share=True))
    if limit is None:
        return True
    guests = holders(db, [t])[t.id]
    return guest_id in guests or len(guests) < limit
