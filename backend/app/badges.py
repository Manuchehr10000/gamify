"""Badges for categories of tasks (TAG's rules, 3.3). Conditions are fixed here; names and their texts are in the
language file. A badge follows what is done now: it is worked out from the guest's tasks on every read, and
badge_awards only remembers which ones the guest has seen, the way guests.level_shown does for levels."""
from collections import Counter, defaultdict

from sqlalchemy import String, cast, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DbSession

from app.models import BadgeAward, Guest, QuizAttempt, ScoreEvent, Submission, Task

# In the order guests see them
BADGES = ["photo_hunter", "networker", "erudite", "brand_friend", "forum_spirit"]

PHOTO_METHODS = {"photo", "photo_text"}
PHOTO_TASKS = 5
FULL_QUIZZES = 5
PARTNER_TASKS = 3


def earned(db: DbSession, guest_ids: list[int]) -> dict[int, list[str]]:
    """Each guest's badges, in BADGES order. A task counts as done while its award stands and no moderator rejected
    its submission (a retake takes the award back; a penalty keeps it but rejects the submission)."""
    if not guest_ids:
        return {}
    award = ScoreEvent.reason == "task:" + cast(Task.id, String)
    done = db.execute(select(ScoreEvent.guest_id, Task.id, Task.type, Task.method, Task.partner_name)
                      .join(Task, award).where(ScoreEvent.guest_id.in_(guest_ids))).all()
    rejected = set(db.execute(select(Submission.guest_id, Submission.task_id)
                              .where(Submission.guest_id.in_(guest_ids), Submission.status == "penalty")).all())
    spirit = set(db.scalars(select(Submission.guest_id).join(Task, Task.id == Submission.task_id)
                            .where(Submission.guest_id.in_(guest_ids), Submission.status == "bonus",
                                   Task.type == "crazy")))
    full = Counter(db.scalars(select(QuizAttempt.guest_id).where(
        QuizAttempt.guest_id.in_(guest_ids), QuizAttempt.finished_at.is_not(None), QuizAttempt.total > 0,
        QuizAttempt.correct == QuizAttempt.total)))
    # Every Нетворкинг task in the file; with none in it, nobody gets the badge
    networking = set(db.scalars(select(Task.id).where(Task.active, Task.type == "networking")))

    photos: Counter = Counter()
    partners: dict[int, Counter] = defaultdict(Counter)
    tasks: dict[int, set[int]] = defaultdict(set)
    for gid, task_id, _type, method, partner in done:
        if (gid, task_id) in rejected:
            continue
        tasks[gid].add(task_id)
        if method in PHOTO_METHODS:
            photos[gid] += 1
        if partner:
            partners[gid][partner] += 1

    out: dict[int, list[str]] = {}
    for gid in guest_ids:
        has = {
            "photo_hunter": photos[gid] >= PHOTO_TASKS,
            "networker": bool(networking) and networking <= tasks[gid],
            "erudite": full[gid] >= FULL_QUIZZES,
            "brand_friend": any(n >= PARTNER_TASKS for n in partners[gid].values()),
            "forum_spirit": gid in spirit,
        }
        out[gid] = [b for b in BADGES if has[b]]
    return out


def of(db: DbSession, guest_id: int) -> list[str]:
    return earned(db, [guest_id])[guest_id]


def _lock(db: DbSession, guest_id: int) -> None:
    """The guest's row, locked until commit: a feed load and a moderator's rejection work out and record badges one
    after the other, so a rejection never lands between reading the badges and remembering them."""
    db.execute(select(Guest.id).where(Guest.id == guest_id).with_for_update())


def fresh(db: DbSession, guest_id: int) -> list[str]:
    """Remember the badges the guest holds and return the ones not seen before: the full-screen moment, once each.
    Ones no longer held are forgotten quietly. Conflict-free inserts, so two loads at once can't both show one."""
    _lock(db, guest_id)
    badges = of(db, guest_id)
    new = [b for b in badges
           if db.execute(insert(BadgeAward).values(guest_id=guest_id, badge=b)
                         .on_conflict_do_nothing(index_elements=["guest_id", "badge"])
                         .returning(BadgeAward.id)).scalar() is not None]
    db.execute(delete(BadgeAward).where(BadgeAward.guest_id == guest_id, BadgeAward.badge.not_in(badges)))
    db.commit()
    return new


def lost(db: DbSession, guest_id: int) -> None:
    """Forget the badges a moderator's rejection just broke, so earning one back shows the moment again even when
    the guest never opened the feed in between. The caller flushes the decision first and commits."""
    _lock(db, guest_id)
    db.execute(delete(BadgeAward).where(BadgeAward.guest_id == guest_id, BadgeAward.badge.not_in(of(db, guest_id))))
