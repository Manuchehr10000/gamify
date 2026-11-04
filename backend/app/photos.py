"""Photos guests send. The phone redraws them; the server only checks what arrived and drops the metadata segments
(no image library in the stack). Kept until the photo deletion date."""
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session as DbSession

from app import config, settings, stages
from app.db import engine
from app.models import JobRun, Setting, Stage, Submission

MAX_SIDE = 1600
# A 1600 px JPEG from the phone is well under this; anything bigger was not redrawn
MAX_BYTES = 1024 * 1024
# The phone's copy for the moderation list
THUMB_SIDE = 400
THUMB_MAX_BYTES = 100 * 1024
# The whole files request: the photo, its thumbnail and the multipart framing
MAX_BODY = MAX_BYTES + THUMB_MAX_BYTES + 64 * 1024

# The default deletion date: this many days after the local date of the last stage's end
KEEP_DAYS = 30


def delete_date(db: DbSession) -> date | None:
    """The day photo links stop working (and piece 22 deletes the photos): the admin's date, else the default.
    None with neither: nothing is open."""
    saved = settings.text(db, "photo_delete_date")
    return date.fromisoformat(saved) if saved else default_date(db)


def default_date(db: DbSession) -> date | None:
    """The local date (UTC+5) of the last stage's end + 30 days; None without stages."""
    end = db.scalar(select(func.max(Stage.ends_at)).where(Stage.active))
    return end.astimezone(stages.EVENT_TZ).date() + timedelta(days=KEEP_DAYS) if end else None


def links_open(db: DbSession) -> bool:
    """Checked on every open: links work up to the day before the deletion date, in forum local time."""
    until = delete_date(db)
    return until is not None and stages.now().astimezone(stages.EVENT_TZ).date() < until


# Admins see the banner, and the date is locked, this many days before it
WARN_DAYS = 7
# Photos emptied per committed step of the deletion job: a stopped run keeps what it did
BATCH = 200
# The job's name in the run log, and how its final entry starts
JOB = "photo_deletion"
DONE = "удалено фото:"
# How a run that deleted a batch, not yet compacted, starts its entry
DELETED = "удалено фото в этом запуске:"


def _today() -> date:
    return stages.now().astimezone(stages.EVENT_TZ).date()


def locked(db: DbSession) -> bool:
    """From 7 days before the deletion date the banner shows and the date can't be changed."""
    until = delete_date(db)
    return until is not None and _today() >= until - timedelta(days=WARN_DAYS)


def too_soon(day: date | None) -> bool:
    """A date an admin may not set: one that would leave admins less than the 7 days' warning."""
    return day is not None and day < _today() + timedelta(days=WARN_DAYS)


def remaining(db: DbSession) -> int:
    """Photos still kept, guests' own deletions left out."""
    return db.scalar(select(func.count()).where(Submission.photo.is_not(None)))


def _pin(db: DbSession) -> str:
    """Once the banner shows, the default date is saved as the admin's date, so a later change to the stages can't
    move the announced day."""
    until = delete_date(db)
    if settings.text(db, "photo_delete_date") or not locked(db):
        return ""
    db.execute(update(Setting).where(Setting.key == "photo_delete_date").values(text_value=until.isoformat()))
    settings.bump(db)
    return f"дата удаления фото закреплена: {until:%d.%m.%Y}"


def delete_job(db: DbSession) -> str:
    """The job: from the banner on, it keeps the date as announced. On the deletion date, every photo and thumbnail
    goes in batches, each committed, so a stopped run is continued by the next one. The first run that finds none
    left compacts the table and writes the final entry, once: the count, start, end and the day Neon's restore
    history stops holding the photos."""
    pinned = _pin(db)
    until = delete_date(db)
    if until is None or _today() < until:
        return pinned
    kept = (Submission.photo.is_not(None)) | (Submission.thumb.is_not(None))
    day_start = datetime.combine(until, time(), stages.EVENT_TZ)
    deleted = 0
    while True:
        batch = select(Submission.id).where(kept).order_by(Submission.id).limit(BATCH).scalar_subquery()
        n = db.execute(update(Submission).where(Submission.id.in_(batch)).values(photo=None, thumb=None)).rowcount
        if not n:
            break
        deleted += n
        db.commit()
    if deleted:
        # This run's own snapshot predates its batches, and VACUUM keeps every row version a transaction that began
        # before them might still see: the compaction is left to the next run, which starts after them
        return f"{DELETED} {deleted}; сжатие — в следующем"
    if db.scalar(select(func.count()).where(JobRun.job == JOB, JobRun.detail.startswith(DONE))):
        return ""
    db.commit()
    # VACUUM FULL can't run inside a transaction: its own connection, with nothing of this session's still open.
    # It rewrites the table without the emptied photos, so the database shrinks
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        c.execute(text("VACUUM FULL submissions"))
    # Every photo sent has a token; a guest's own deletion takes its token too, so this counts what the job deleted
    count = db.scalar(select(func.count()).where(Submission.photo_token.is_not(None)))
    # From the first run on the date, which a stopped run may have been
    start = db.scalar(select(func.min(JobRun.started_at)).where(JobRun.job == JOB, JobRun.started_at >= day_start))
    # The end is when the last run that deleted photos finished, not this compaction run; now when guests had
    # deleted every one themselves
    end = db.scalar(select(func.max(JobRun.finished_at)).where(
        JobRun.job == JOB, JobRun.started_at >= day_start, JobRun.detail.startswith(DELETED))) or stages.now()
    kept_until = end + timedelta(days=config.NEON_RESTORE_DAYS)

    def at(t: datetime) -> str:
        return f"{t.astimezone(stages.EVENT_TZ):%d.%m.%Y %H:%M}"
    return (f"{DONE} {count}; начало {at(start or end)}, конец {at(end)}; "
            f"в истории восстановления Neon до {kept_until.astimezone(stages.EVENT_TZ):%d.%m.%Y}")


# Start-of-frame markers carry the size: baseline, progressive and the rarer coding modes, not DHT/JPG/DAC
_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def jpeg_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) read from the JPEG's frame header, or None when it is not a JPEG."""
    if not data.startswith(b"\xff\xd8"):
        return None
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        if marker in (0x01, *range(0xD0, 0xD8)):  # markers without a length
            i += 2
            continue
        length = int.from_bytes(data[i + 2:i + 4], "big")
        if marker in _SOF:
            if i + 9 > len(data):
                return None
            height = int.from_bytes(data[i + 5:i + 7], "big")
            width = int.from_bytes(data[i + 7:i + 9], "big")
            return width, height
        if marker == 0xDA:  # image data started without a frame header
            return None
        i += 2 + length
    return None


def strip_metadata(data: bytes) -> bytes:
    """The JPEG without its APP1–APP15 segments (Exif with GPS and camera data, XMP, ICC …). APP0 (JFIF) and
    everything from the image data on are kept as they are. Called on a JPEG jpeg_size has read."""
    out = bytearray(data[:2])
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            break
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        if marker in (0x01, *range(0xD0, 0xD8)):  # markers without a length
            out += data[i:i + 2]
            i += 2
            continue
        if marker == 0xDA:  # image data: kept as it is to the end
            break
        end = i + 2 + int.from_bytes(data[i + 2:i + 4], "big")
        if not 0xE1 <= marker <= 0xEF:
            out += data[i:end]
        i = end
    return bytes(out + data[i:])
