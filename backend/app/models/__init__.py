from datetime import datetime

from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, LargeBinary, Numeric, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
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
    # Switched off by an admin: can't log in, and its sessions were ended
    active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    # Raised by every save; a form sends the version it read, and a stale one is refused
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    __mapper_args__ = {"version_id_col": version}


class ScoreEvent(Base):
    """The points and coins record. Append-only: written by app.ledger only, never edited or deleted."""
    __tablename__ = "score_events"
    __table_args__ = (Index("score_events_guest_reason", "guest_id", "reason"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id", ondelete="CASCADE"))
    # What it is for: task:{id}, bonus:{submission}, retake:{submission}, penalty:{submission},
    # withdraw:{submission}, buy:{prize}, forum_arrival. One open award per reason per guest: opening the link again or on a second phone adds nothing
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
    # Switched off in the admin's form: left out of the day's schedule. A stage with tasks is never deleted
    active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    # «Карточек в ленте»: how many cards a guest's feed shows at once in this stage (open time windows included)
    batch_size: Mapped[int] = mapped_column(default=15, server_default=text("15"))
    # «Множитель»: 1 to 5 in steps of 0.5. Task awards pay base points × it; coins stay as they are
    multiplier: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal(1), server_default=text("1"))
    # Raised by every save; a form sends the version it read, and a stale one is refused
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    __mapper_args__ = {"version_id_col": version}


class Partner(Base):
    __tablename__ = "partners"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Uploads of «Задания» and «Призы» match partners by it; a new name adds a partner
    name: Mapped[str] = mapped_column(String(100), unique=True)
    # general, headliner, mf_partner, supporters, or "" (none given): set by the «Задания» sheet
    package: Mapped[str] = mapped_column(String(16), default="")
    # PNG or JPEG bytes, up to 1 MB; deferred so listing partners never loads them
    logo: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    # Raised by every save; a form sends the version it read, and a stale one is refused
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    __mapper_args__ = {"version_id_col": version}


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
    # «Лимит»: how many guests may do it in all (app.places counts them); empty = no limit
    limit: Mapped[int | None]
    # A quiz's «Блиц»: each right answer earns a speed bonus in points on top of the quiz's own
    blitz: Mapped[bool] = mapped_column(default=False, server_default="false")
    # «Бонус за скорость» per question: paid whole within «Без потерь, сек», then falling to 0 at «Время бонуса, сек»
    speed_bonus: Mapped[int] = mapped_column(default=20, server_default="20")
    grace_seconds: Mapped[int] = mapped_column(default=3, server_default="3")
    bonus_seconds: Mapped[int] = mapped_column(default=12, server_default="12")
    # Rows removed from the file are hidden, not deleted: later pieces keep what guests did
    active: Mapped[bool] = mapped_column(default=True)
    # Raised by every save; a form sends the version it read, and a stale one is refused
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    __mapper_args__ = {"version_id_col": version}


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
    # Raised by every save; a form sends the version it read, and a stale one is refused
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    __mapper_args__ = {"version_id_col": version}


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
        Index("submissions_photo_token", "photo_token", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id", ondelete="CASCADE"))
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    # The JPEG as the phone sent it, metadata stripped; deferred so listing submissions never loads the bytes
    photo: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    # The phone's 400 px copy for the moderation list; empty for photos sent before thumbnails
    thumb: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # "" waiting for a moderator · accepted · bonus · retake (task reopened) · penalty (task closed, no points) ·
    # withdrawn (the guest deleted the photo before a decision: task closed, no points)
    status: Mapped[str] = mapped_column(String(16), default="")
    moderator: Mapped[str] = mapped_column(String(100), default="")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The phone's key for this send (its claim's ID), repeated on its retries: a late retry of one sent back is not
    # a new send
    upload: Mapped[str] = mapped_column(String(64), default="")
    # The photo's link in the partner report (/api/photos/{token}): random, never the ID; None for a text
    photo_token: Mapped[str | None] = mapped_column(String(64))


class Claim(Base):
    """The first step of sending a photo or text: the phone's submission ID, checked and timed by the server. The
    files follow in a second step; points are paid when they arrive (a text-only claim pays at once)."""
    __tablename__ = "claims"
    __table_args__ = (
        Index("claims_open_guest_task", "guest_id", "task_id", unique=True, postgresql_where=text("state = 'open'")),
        Index("claims_open_expires", "expires_at", postgresql_where=text("state = 'open'")),
    )

    # Made on the phone, repeated on every retry: the same ID never pays twice
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id", ondelete="CASCADE"))
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    # A text or photo+text task's text rides in the claim
    text: Mapped[str] = mapped_column(Text, default="")
    # The server's time of the claim: it sets the stage, and later the stock (piece 15) and multiplier (piece 16)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    stage_id: Mapped[int | None] = mapped_column(ForeignKey("stages.id", ondelete="SET NULL"))
    # The stage's multiplier at the claim: the award pays at it even if the admin changes it before the files arrive
    multiplier: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal(1), server_default="1")
    # Past this the claim lapses and frees its place; files that come later are refused
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # open (waiting for files) · done · lapsed
    state: Mapped[str] = mapped_column(String(8), default="open")


class FeedRotation(Base):
    """Where a guest's feed is in a stage's rotation. Moved on by POST /api/feed/next, on a page load of /app:
    the next batch starts after the last card shown (a poll that filled the batch from a later card moves that mark). Tasks are found again by their place in the order, even if
    done, switched off or moved since; empty = from the top."""
    __tablename__ = "feed_rotations"

    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id", ondelete="CASCADE"), primary_key=True)
    stage_id: Mapped[int] = mapped_column(ForeignKey("stages.id", ondelete="CASCADE"), primary_key=True)
    # The batch on screen starts after this card, so polls and coming back show the same batch
    after_task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))
    # The last rotating card shown since that page load: the next one starts after it
    last_task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))


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
    # Raised by every save; a form sends the version it read, and a stale one is refused
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    __mapper_args__ = {"version_id_col": version}


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    # One attempt per quiz per guest
    __table_args__ = (UniqueConstraint("guest_id", "task_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id", ondelete="CASCADE"))
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    # Set from the server clock at «Начать»: a reload doesn't restart the countdown
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # The stage's multiplier at «Начать»: the finish pays the share at it
    multiplier: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal(1), server_default=text("1"))
    # The stage running at «Начать»: the speed bonus row is stored on it, with the multiplier above
    stage_id: Mapped[int | None] = mapped_column(ForeignKey("stages.id", ondelete="SET NULL"))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # {"question number": option number chosen}; keyed by number so a re-upload of the questions keeps them
    answers: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {"question number": {"sent": when the server first sent it, "got": when it received the answer}}: the speed
    # bonus's answer times, from the server clock only
    times: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    # Filled when the quiz ends: what the guest sees as «3 из 5»
    correct: Mapped[int | None]
    total: Mapped[int | None]


class Level(Base):
    __tablename__ = "levels"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The file's «Уровни» sheet: «Название» and «Баллов от»; the first level starts at 0
    name: Mapped[str] = mapped_column(String(100))
    min_points: Mapped[int] = mapped_column(unique=True)
    # Raised by every save; a form sends the version it read, and a stale one is refused
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    __mapper_args__ = {"version_id_col": version}


class Badge(Base):
    """A badge the admin set in the «Бейджи» sheet or tab: a rule with its numbers and filters. TAG's five come from
    the migration with 011's codes."""
    __tablename__ = "badges"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The admin's ID: re-uploads match rows by it, and badge:{code} is its coins' reason in score_events (so at most 26)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    # tasks · all_of_type · quiz_streak · bonuses · first_n · place (app.badges.RULES)
    rule: Mapped[str] = mapped_column(String(16))
    # The N the rule needs; empty for «Все задания типа»
    count: Mapped[int | None]
    # «Тип задания»: task types or ways of doing it, as the file names them, comma-separated; empty = any
    kinds: Mapped[str] = mapped_column(String(200), default="", server_default="")
    # Only this partner's tasks; or any_partner: N tasks of one and the same partner
    partner_id: Mapped[int | None] = mapped_column(ForeignKey("partners.id"))
    any_partner: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    # «Первые N»: the task whose first N guests get it
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"))
    # Paid once on earning, taken back on losing; never points, never a stage multiplier
    coins: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    # «На экран»: the hall screen announces a guest earning it
    on_screen: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    # Switched off: nobody holds it, and its coins are taken back
    active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    # Row order in the last upload: the order guests see them in
    position: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    # Raised by every save; a form sends the version it read, and a stale one is refused
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    __mapper_args__ = {"version_id_col": version}


class BadgeAward(Base):
    __tablename__ = "badge_awards"
    # A badge the guest holds now, worked out when something changes; losing it removes the row, so earning it again
    # shows the moment again
    __table_args__ = (UniqueConstraint("guest_id", "badge"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id", ondelete="CASCADE"))
    # The badge's code (badges.code)
    badge: Mapped[str] = mapped_column(ForeignKey("badges.code"))
    # When it was earned, from the server clock
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # The guest saw the full-screen moment
    seen: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    # Earned by the guest's own action, of a badge marked «на экран»: the hall screen may show it within 60 seconds
    announce: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    # When the hall screen started showing it
    shown_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
    # What an ok run did, in the job's words, e.g. how many claims lapsed
    detail: Mapped[str] = mapped_column(Text, default="")


class Setting(Base):
    """A game setting the admin edits in the form. The keys and their defaults are in app.settings."""
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    min_value: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    max_value: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    # now (from now on) · recheck (past activity is checked again) · locked (refused while running)
    effect: Mapped[str] = mapped_column(String(16))
    # A text setting's value (the push texts); min_value and max_value are then its length. Empty for numbers
    text_value: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    __mapper_args__ = {"version_id_col": version}


class ChangeEvent(Base):
    """The admins' change log. Append-only: a database trigger refuses updates and deletes."""
    __tablename__ = "change_events"
    __table_args__ = (Index("change_events_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # The admin who saved it; no foreign key, so the log outlives the account
    staff_id: Mapped[int | None]
    staff_name: Mapped[str] = mapped_column(String(100))
    # A list kind (stages, tasks, …), settings, rating or guests
    kind: Mapped[str] = mapped_column(String(32))
    item_id: Mapped[int | None]
    # What the item was called when it changed: a task's ID, a stage's name, a setting's key
    item: Mapped[str] = mapped_column(String(200))
    # The field's key; _created and _deleted for whole rows
    field: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    # form or excel
    source: Mapped[str] = mapped_column(String(8))


class HallState(Base):
    """The hall screen's mode, switched by a moderator or admin. One row (id 1); none means «Авто»."""
    __tablename__ = "hall_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    # auto · live («Эфир сейчас») · logos («Только логотипы») · pause
    mode: Mapped[str] = mapped_column(String(8))
    # Who switched last, by the name they logged in with
    staff_name: Mapped[str] = mapped_column(String(100))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LogoShow(Base):
    """One logo on the hall screen: when it came up and how long it stayed. Read by piece 21's partner report."""
    __tablename__ = "logo_shows"
    __table_args__ = (UniqueConstraint("partner_id", "started_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    partner_id: Mapped[int] = mapped_column(ForeignKey("partners.id", ondelete="CASCADE"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    seconds: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PushSubscription(Base):
    """A phone that allowed pushes. The push service's «gone» answer switches it off; there is no unsubscribe."""
    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Random, carried in each push so the phone's arrival report names its subscription without a login
    key: Mapped[str] = mapped_column(String(32), unique=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id", ondelete="CASCADE"))
    # The browser's push address and keys, as PushSubscription.toJSON() gives them
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PushMessage(Base):
    """One push in the schedule. Rows with a source are kept in step with it by app.push.regenerate; one-off messages
    are the admin's. The counts are per push, not per phone."""
    __tablename__ = "push_messages"
    __table_args__ = (Index("push_messages_state_at", "state", "at"), Index("push_messages_shown_at", "shown_at"))

    id: Mapped[int] = mapped_column(primary_key=True)
    # stage · quiz_before · quiz_open · market · one_off
    kind: Mapped[str] = mapped_column(String(16))
    # What it follows: stage:{id}, quiz_before:{task}, quiz_open:{task}, market; empty for a one-off message
    source: Mapped[str | None] = mapped_column(String(32), unique=True)
    # A quiz push opens this task's page
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))
    # The source's time; at = source_at + shift_seconds, so an admin's move survives the source moving
    source_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shift_seconds: Mapped[int] = mapped_column(default=0, server_default="0")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    title: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Tajik: the columns are ready and stay empty; guests get Russian
    text_tg: Mapped[str] = mapped_column(Text, default="", server_default="")
    title_tg: Mapped[str] = mapped_column(String(200), default="", server_default="")
    # An admin edited the title or text: the source's text no longer replaces it
    text_edited: Mapped[bool] = mapped_column(default=False, server_default="false")
    # planned · sent · cancelled · expired (past due and never sent)
    state: Mapped[str] = mapped_column(String(16), default="planned", server_default="planned")
    # When it went out to open apps and the hall screen (sent, or due while pushes were off)
    shown_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Accepted by the push service · reported arrived by the phone · refused or gone
    sends: Mapped[int] = mapped_column(default=0, server_default="0")
    deliveries: Mapped[int] = mapped_column(default=0, server_default="0")
    failures: Mapped[int] = mapped_column(default=0, server_default="0")
    # The ids of the subscriptions whose arrival report was already counted for this push, so each counts once; only
    # for that check, never shown or reported (the counts stay per push)
    counted_subscriptions: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list, server_default="{}")
    # Raised by every save; a form sends the version it read, and a stale one is refused
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __mapper_args__ = {"version_id_col": version}
