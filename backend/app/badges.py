"""Badges the admin sets in the «Бейджи» sheet or tab (TAG's rules, 3.3): each one is a rule with its numbers and
filters. A badge follows what is true now and is worked out when something changes (a task done, a moderator's
decision, a quiz finished, a freeze, an upload, a form save), so its coins and the hall announcement happen at that
moment. badge_awards records what each guest holds, whether they saw the full-screen moment, and what the hall screen
may announce."""
from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy import String, cast, delete, exists, func, select, update
from sqlalchemy.orm import Session as DbSession

from app import ledger, stages
from app.models import Badge, BadgeAward, Guest, Partner, QuizAttempt, ScoreEvent, Submission, Task
from app.task_file import kind_keys


def reason(code: str) -> str:
    """The badge's coins in score_events: badge:{code} fits reason's 32 characters, as codes are at most 26."""
    return f"badge:{code}"


def active(db: DbSession) -> list[Badge]:
    """The badges switched on, in the order guests see them."""
    return list(db.scalars(select(Badge).where(Badge.active).order_by(Badge.position, Badge.id)))


def _matches(b: Badge, keys: set[str], type_: str, method: str, partner: int | None) -> bool:
    """A task counts towards the badge: its type or way of doing it is one of the filter's (any when empty), and it is
    the filter's partner's (when one is set)."""
    return (not keys or type_ in keys or method in keys) and (b.partner_id is None or partner == b.partner_id)


def _rejected():
    """The award's submission was rejected by a moderator: it never counts towards a badge."""
    return exists().where(Submission.guest_id == ScoreEvent.guest_id, Submission.status == "penalty",
                          cast(Submission.task_id, String) == func.split_part(ScoreEvent.reason, ":", 2))


def _first(db: DbSession, b: Badge) -> set[int]:
    """«Первые N»: the first N guests to do the task, by the awards that still stand, in the order they were earned.
    A rejected guest drops out and the next one moves in."""
    if b.task_id is None or not b.count:
        return set()
    return set(db.scalars(select(ScoreEvent.guest_id)
                          .where(ScoreEvent.reason == f"task:{b.task_id}", ledger.standing(), ~_rejected())
                          .order_by(ScoreEvent.created_at, ScoreEvent.id).limit(b.count)))


def compute(db: DbSession, guest_ids: list[int]) -> dict[int, set[str]]:
    """The codes of the active badges each guest meets now. A task counts as done while its award stands and no
    moderator rejected its submission (a retake reverses the award; a penalty keeps it but rejects the submission)."""
    out: dict[int, set[str]] = {gid: set() for gid in guest_ids}
    badges = active(db)
    if not badges or not guest_ids:
        return out
    award = ScoreEvent.reason == "task:" + cast(Task.id, String)
    done = db.execute(select(ScoreEvent.guest_id, Task.id, Task.type, Task.method, Task.partner_id)
                      .join(Task, award).where(ScoreEvent.guest_id.in_(guest_ids), ledger.standing(),
                                               ~_rejected())).all()
    bonuses = db.execute(select(Submission.guest_id, Task.type, Task.method, Task.partner_id)
                         .join(Task, Task.id == Submission.task_id)
                         .where(Submission.guest_id.in_(guest_ids), Submission.status == "bonus")).all()
    # Quizzes in the order they finished: a perfect one adds to the run, any other (a wrong or unanswered question,
    # the timer ending it) resets it. One whose timer ran out counts at its deadline even before anything settles it:
    # it always has an unanswered question, so it is a mistake
    perfect: dict[int, list[bool]] = defaultdict(list)
    deadline = QuizAttempt.started_at + func.make_interval(0, 0, 0, 0, 0, 0, Task.timer_seconds)
    ended = func.coalesce(QuizAttempt.finished_at, deadline)
    for gid, correct, total, finished in db.execute(
            select(QuizAttempt.guest_id, QuizAttempt.correct, QuizAttempt.total, QuizAttempt.finished_at)
            .join(Task, Task.id == QuizAttempt.task_id)
            .where(QuizAttempt.guest_id.in_(guest_ids),
                   QuizAttempt.finished_at.is_not(None) | ((Task.timer_seconds > 0) & (deadline <= stages.now())))
            .order_by(ended, QuizAttempt.id)):
        perfect[gid].append(finished is not None and bool(total) and correct == total)
    by_guest: dict[int, list] = defaultdict(list)
    for row in done:
        by_guest[row.guest_id].append(row)

    for b in badges:
        keys = kind_keys(b.kinds)
        if b.rule == "tasks":
            for gid in guest_ids:
                rows = [r for r in by_guest[gid] if _matches(b, keys, r.type, r.method, r.partner_id)]
                if b.any_partner:
                    met = max(Counter(r.partner_id for r in rows if r.partner_id).values(), default=0) >= b.count
                else:
                    met = len(rows) >= b.count
                if met:
                    out[gid].add(b.code)
        elif b.rule == "all_of_type":
            # Every such task in the file; with none in it, nobody gets the badge
            needed = {t.id for t in db.scalars(select(Task).where(Task.active))
                      if _matches(b, keys, t.type, t.method, t.partner_id)}
            for gid in guest_ids:
                if needed and needed <= {r.id for r in by_guest[gid]}:
                    out[gid].add(b.code)
        elif b.rule == "quiz_streak":
            for gid in guest_ids:
                run = best = 0
                for ok in perfect[gid]:
                    run = run + 1 if ok else 0
                    best = max(best, run)
                # Once reached the badge stays: finished quizzes can't be rejected
                if best >= b.count:
                    out[gid].add(b.code)
        elif b.rule == "bonuses":
            got = Counter(gid for gid, type_, method, partner in bonuses if _matches(b, keys, type_, method, partner))
            for gid in guest_ids:
                if got[gid] >= b.count:
                    out[gid].add(b.code)
        elif b.rule == "first_n":
            for gid in _first(db, b) & set(guest_ids):
                out[gid].add(b.code)
        elif b.rule == "place":
            # In the top N while the ranking is frozen; unfrozen, nobody
            top = set(db.scalars(select(Guest.id).where(Guest.id.in_(guest_ids), Guest.in_rating,
                                                        Guest.frozen_place.is_not(None),
                                                        Guest.frozen_place <= b.count)))
            for gid in top:
                out[gid].add(b.code)
    return out


def lock_all(db: DbSession) -> None:
    """Every guest's row, locked in id order. A transaction that will recheck takes this first, before any task, badge
    or other row: guests are always locked first, in the same order everywhere, so it can't deadlock with a guest's
    own action (guest, then task) or another recheck."""
    db.execute(select(Guest.id).order_by(Guest.id).with_for_update())


def sync(db: DbSession, guest_ids: list[int], actor: int | None = None) -> None:
    """Bring the guests' badges up to what they meet now: a badge gained is recorded unseen and pays its coins, one
    lost is removed and its coins taken back (they may go below zero, as a moderator's penalty can), and one kept
    whose «Монеты» the admin changed is settled to the new amount. Only the actor's gains, by their own action, may be
    announced on the hall screen. The guests are locked in order (the caller holds no task row lock then), so a
    second change for one of them waits. The caller commits."""
    if not guest_ids:
        return
    ids = sorted(set(guest_ids))
    db.execute(select(Guest.id).where(Guest.id.in_(ids)).order_by(Guest.id).with_for_update())
    want = compute(db, ids)
    badges = {b.code: b for b in active(db)}
    have: dict[int, set[str]] = defaultdict(set)
    for gid, code in db.execute(select(BadgeAward.guest_id, BadgeAward.badge).where(BadgeAward.guest_id.in_(ids))):
        have[gid].add(code)
    # The badge coins each guest holds now: their standing badge:{code} awards
    paid = {(e.guest_id, e.reason): e for e in db.scalars(
        select(ScoreEvent).where(ScoreEvent.guest_id.in_(ids), ScoreEvent.action == "badge", ledger.standing()))}
    in_rating = dict(db.execute(select(Guest.id, Guest.in_rating).where(Guest.id.in_(ids))).all())
    for gid in ids:
        lost = have[gid] - want[gid]
        if lost:
            db.execute(delete(BadgeAward).where(BadgeAward.guest_id == gid, BadgeAward.badge.in_(lost)))
            for code in sorted(lost):
                if (gid, reason(code)) in paid:
                    ledger.take_back(db, paid[gid, reason(code)], reason(code), "badge", reverse=True)
        for code in [c for c in badges if c in want[gid] & have[gid]]:
            # The admin changed the badge's coins: the old amount is taken back and the new one paid
            event = paid.get((gid, reason(code)))
            if (event.coins if event else 0) != badges[code].coins:
                if event is not None:
                    ledger.take_back(db, event, reason(code), "badge", reverse=True)
                if badges[code].coins:
                    ledger.write(db, gid, reason(code), "badge", 0, badges[code].coins)
        for code in [c for c in badges if c in want[gid] - have[gid]]:
            b = badges[code]
            # «Место» badges come from the admin's freeze, not the guest's action: never announced
            db.add(BadgeAward(guest_id=gid, badge=code, created_at=stages.now(),
                              announce=gid == actor and b.on_screen and in_rating[gid] and b.rule != "place"))
            # Coins only, at multiplier 1: badges never move the ranking or levels. A re-earned badge pays again,
            # as its last award was reversed when it was lost
            if b.coins:
                ledger.write(db, gid, reason(code), "badge", 0, b.coins)
    db.flush()


def recheck(db: DbSession) -> None:
    """Every guest's badges checked against all past activity, quietly: an admin's change never floods the hall
    screen. The caller took lock_all first. The caller commits."""
    sync(db, list(db.scalars(select(Guest.id))))


def first_n_guests(db: DbSession, task_id: int) -> list[int]:
    """Who a rejection on this task may move in or out of a «Первые N» badge: its holders and every guest who did the
    task (whoever moves in is one of them). Known before the rejection is written, so they are locked first."""
    out: set[int] = set()
    for b in active(db):
        if b.rule == "first_n" and b.task_id == task_id:
            out |= set(db.scalars(select(BadgeAward.guest_id).where(BadgeAward.badge == b.code)))
            out |= set(db.scalars(select(ScoreEvent.guest_id).where(ScoreEvent.reason == f"task:{task_id}")))
    return list(out)


@dataclass
class Held:
    code: str
    name: str
    rule: str


def _held(b: Badge) -> Held:
    return Held(b.code, b.name, b.rule)


def earned(db: DbSession, guest_ids: list[int]) -> dict[int, list[Held]]:
    """Each guest's badges, in the order guests see them, as badge_awards records them."""
    out: dict[int, list[Held]] = {gid: [] for gid in guest_ids}
    if not guest_ids:
        return out
    rows = db.execute(select(BadgeAward.guest_id, Badge).join(Badge, Badge.code == BadgeAward.badge)
                      .where(BadgeAward.guest_id.in_(guest_ids), Badge.active)
                      .order_by(Badge.position, Badge.id))
    for gid, b in rows:
        out[gid].append(_held(b))
    return out


def of(db: DbSession, guest_id: int) -> list[Held]:
    return earned(db, [guest_id])[guest_id]


def fresh(db: DbSession, guest_id: int) -> list[Held]:
    """The badges held and not seen before: the full-screen moment, once each. A conditional update, so two loads at
    once can't both show one. Commits."""
    codes = set(db.scalars(update(BadgeAward).where(BadgeAward.guest_id == guest_id, BadgeAward.seen.is_(False))
                           .values(seen=True).returning(BadgeAward.badge)))
    db.commit()
    return [_held(b) for b in active(db) if b.code in codes]


@dataclass
class Shown:
    """A badge on the profile: held in colour, or greyed with the condition its rule gives."""
    code: str
    name: str
    rule: str
    count: int | None
    kinds: str
    partner: str
    any_partner: bool
    task: str
    held: bool


def shelf(db: DbSession, guest_id: int) -> list[Shown]:
    held = {h.code for h in of(db, guest_id)}
    badges = active(db)
    partners = dict(db.execute(select(Partner.id, Partner.name)).all())
    tasks = dict(db.execute(select(Task.id, Task.text).where(Task.id.in_({b.task_id for b in badges}))).all())
    return [Shown(b.code, b.name, b.rule, b.count, b.kinds, partners.get(b.partner_id, ""), b.any_partner,
                  tasks.get(b.task_id, ""), b.code in held) for b in badges]
