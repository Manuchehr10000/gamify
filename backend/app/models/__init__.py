from datetime import datetime

from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, LargeBinary, Numeric, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Guest(Base):
    __tablename__ = "guests"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The random code in the badge link; never the registration ID
    code: Mapped[str] = mapped_column(String(16), unique=True)
    # TAG's registration ID; empty for walk-ins added at the desk
    reg_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100), default="")
    phone: Mapped[str] = mapped_column(String(32), default="", index=True)
    company: Mapped[str] = mapped_column(String(200), default="")
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # «В рейтинге: нет» in the guest list (staff, volunteers): plays and earns, never ranked
    in_rating: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    # The place and points when the admin froze the ranking; empty when it isn't frozen
    frozen_place: Mapped[int | None]
    frozen_points: Mapped[int | None]
    # The threshold («Баллов от») of the level the guest last saw: climbing past it shows the full-screen moment.
    # A threshold, not a place in the list, so a new level added below doesn't show an old level again
    level_shown: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    # The sum of the guest's score_events, kept by app.ledger in the same transaction as each row
    points: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    coins: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # guest, desk, admin, stand or moderator
    role: Mapped[str] = mapped_column(String(16))
    guest_id: Mapped[int | None] = mapped_column(ForeignKey("guests.id", ondelete="CASCADE"))
    # The staff account acting in this session; empty for guests
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"))
    # The account's name when it logged in, so a moderator's decisions are logged under it
    staff_name: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Staff(Base):
    __tablename__ = "staff"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    # admin, moderator, desk or stand
    role: Mapped[str] = mapped_column(String(16))
    # bcrypt of the PIN or password; the secret alone identifies the account, so each one is unique
    secret_hash: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScoreEvent(Base):
    """The points and coins record. Append-only: written by app.ledger only, never edited or deleted."""
    __tablename__ = "score_events"
    __table_args__ = (Index("score_events_guest_reason", "guest_id", "reason"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id", ondelete="CASCADE"))
    # What it is for: task:{id}, bonus:{submission}, retake:{submission}, penalty:{submission}, buy:{prize},
    # forum_arrival. One open award per reason per guest: opening the link again or on a second phone adds nothing
    reason: Mapped[str] = mapped_column(String(32))
    # arrival, task, bonus, retake, penalty, buy, speed, badge or withdraw
    action: Mapped[str] = mapped_column(String(16))
    # points = base_points × multiplier, rounded to whole points, halves up
    base_points: Mapped[int]
    multiplier: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal(1), server_default=text("1"))
    points: Mapped[int]
    coins: Mapped[int] = mapped_column(default=0)
    # The stage running when it was written; empty outside the day's schedule
    stage_id: Mapped[int | None] = mapped_column(ForeignKey("stages.id", ondelete="SET NULL"))
    # A retake's reversal: the award it takes back. An award with a reversal no longer counts as done
    reverses_id: Mapped[int | None] = mapped_column(ForeignKey("score_events.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Stage(Base):
    __tablename__ = "stages"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 1–4, the order of the day; the file's «Этапы» sheet is keyed by it
    number: Mapped[int] = mapped_column(unique=True)
    name: Mapped[str] = mapped_column(String(100))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # The banner line guests see when this stage begins
    message: Mapped[str] = mapped_column(Text, default="")
    # The market opens when the first stage marked «Маркет» starts
    market: Mapped[bool] = mapped_column(default=False)


class Partner(Base):
    __tablename__ = "partners"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Uploads of «Задания» and «Призы» match partners by it; a new name adds a partner
    name: Mapped[str] = mapped_column(String(100), unique=True)
    # general, headliner, mf_partner, supporters, or "" (none given): set by the «Задания» sheet
    package: Mapped[str] = mapped_column(String(16), default="")
    logo: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The admin's ID from the file: re-uploads match rows by it
    code: Mapped[str] = mapped_column(String(32), unique=True)
    stage_id: Mapped[int] = mapped_column(ForeignKey("stages.id"))
    type: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    points: Mapped[int]
    coins: Mapped[int]
    # Blank coins cell: filled by the rule, so the export gives it back blank
    coins_from_rule: Mapped[bool] = mapped_column(default=False)
    partner_id: Mapped[int | None] = mapped_column(ForeignKey("partners.id"))
    # How a guest does it: "qr" (scan the code at the venue), "link" (open a link, then confirm),
    # "market" (the guest's first purchase in the market), "photo", "text", "photo_text" (send a submission),
    # "quiz" (answer the questions on the quiz screen), "" (not yet)
    method: Mapped[str] = mapped_column(String(16), default="")
    link: Mapped[str] = mapped_column(Text, default="")
    # The random code printed in the task's QR; kept across re-uploads so printed codes keep working
    qr_code: Mapped[str | None] = mapped_column(String(16), unique=True)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # A quiz's «Таймер, сек»: the guest has this long from «Начать»; empty = no countdown
    timer_seconds: Mapped[int | None]
    # A quiz's «Требует»: the QR task (check-in to the hall) the guest must have done first
    requires_task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"))
    # Row order in the last upload: the tie-break inside each group of the feed
    position: Mapped[int] = mapped_column(default=0)
    # Rows removed from the file are hidden, not deleted: later pieces keep what guests did
    active: Mapped[bool] = mapped_column(default=True)


class Prize(Base):
    __tablename__ = "prizes"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The admin's ID from the file's «Призы» sheet: re-uploads match rows by it
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    partner_id: Mapped[int] = mapped_column(ForeignKey("partners.id"))
    price: Mapped[int]
    quantity: Mapped[int]
    position: Mapped[int] = mapped_column(default=0)
    # Rows removed from the file are hidden, not deleted: guests who bought them still get them
    active: Mapped[bool] = mapped_column(default=True)


class Redemption(Base):
    __tablename__ = "redemptions"
    # A guest can buy each prize once
    __table_args__ = (UniqueConstraint("guest_id", "prize_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id", ondelete="CASCADE"))
    prize_id: Mapped[int] = mapped_column(ForeignKey("prizes.id"))
    # The code in the guest's QR and read out at the stand
    code: Mapped[str] = mapped_column(String(16), unique=True)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Submission(Base):
    __tablename__ = "submissions"
    # One submission per task per guest; after sending it is final. One sent back for a retake stays as the log
    __table_args__ = (
        Index("submissions_guest_task", "guest_id", "task_id", unique=True, postgresql_where=text("status <> 'retake'")),
        Index("submissions_unchecked", "created_at", postgresql_where=text("status = ''")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id", ondelete="CASCADE"))
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    # The JPEG as the phone sent it; deferred so listing submissions never loads the bytes
    photo: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # "" waiting for a moderator · accepted · bonus · retake (task reopened) · penalty (task closed, no points)
    status: Mapped[str] = mapped_column(String(16), default="")
    moderator: Mapped[str] = mapped_column(String(100), default="")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The phone's key for this send, repeated on its retries: a late retry of one sent back is not a new send
    upload: Mapped[str] = mapped_column(String(64), default="")


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (UniqueConstraint("task_id", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    # «№ вопроса» in the «Вопросы» sheet: the order guests get them in, and the key of their answers
    number: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    option1: Mapped[str] = mapped_column(Text)
    option2: Mapped[str] = mapped_column(Text)
    option3: Mapped[str | None] = mapped_column(Text)
    option4: Mapped[str | None] = mapped_column(Text)
    # 1–4: which option is right; never sent to the guest
    correct: Mapped[int]


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    # One attempt per quiz per guest
    __table_args__ = (UniqueConstraint("guest_id", "task_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id", ondelete="CASCADE"))
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    # Set from the server clock at «Начать»: a reload doesn't restart the countdown
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # {"question number": option number chosen}; keyed by number so a re-upload of the questions keeps them
    answers: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Filled when the quiz ends: what the guest sees as «3 из 5»
    correct: Mapped[int | None]
    total: Mapped[int | None]


class Level(Base):
    __tablename__ = "levels"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The file's «Уровни» sheet: «Название» and «Баллов от»; the first level starts at 0
    name: Mapped[str] = mapped_column(String(100))
    min_points: Mapped[int] = mapped_column(unique=True)


class BadgeAward(Base):
    __tablename__ = "badge_awards"
    # A badge the guest holds and has seen; the full-screen moment shows when one is added. A rejection that breaks
    # its condition removes the row, so earning it again shows the moment again
    __table_args__ = (UniqueConstraint("guest_id", "badge"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id", ondelete="CASCADE"))
    # One of badges.BADGES: photo_hunter, networker, erudite, brand_friend, forum_spirit
    badge: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The registered job's name in app.jobs.JOBS
    job: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # ok · failed (error says why) · skipped (the previous run still held the lock)
    result: Mapped[str] = mapped_column(String(16), default="")
    error: Mapped[str] = mapped_column(Text, default="")
