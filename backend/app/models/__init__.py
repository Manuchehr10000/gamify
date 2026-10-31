from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # guest, desk or admin
    role: Mapped[str] = mapped_column(String(16))
    guest_id: Mapped[int | None] = mapped_column(ForeignKey("guests.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScoreEvent(Base):
    __tablename__ = "score_events"
    # One award per reason per guest: opening the link again or on a second phone adds nothing
    __table_args__ = (UniqueConstraint("guest_id", "reason"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id", ondelete="CASCADE"))
    reason: Mapped[str] = mapped_column(String(32))
    points: Mapped[int]
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
    partner_name: Mapped[str] = mapped_column(String(100), default="")
    partner_package: Mapped[str] = mapped_column(String(16), default="")
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Row order in the last upload: the tie-break inside each group of the feed
    position: Mapped[int] = mapped_column(default=0)
    # Rows removed from the file are hidden, not deleted: later pieces keep what guests did
    active: Mapped[bool] = mapped_column(default=True)
