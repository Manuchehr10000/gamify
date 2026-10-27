from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
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
