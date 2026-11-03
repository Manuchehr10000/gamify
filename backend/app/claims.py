"""Claims, the first step of sending a photo or text. A claim the files never followed lapses at its expires_at and
frees its place: the job runner marks it, and every read of a claim treats one past its time as lapsed already."""
from sqlalchemy import update
from sqlalchemy.orm import Session as DbSession

from app import stages
from app.models import Claim


def expired(c: Claim) -> bool:
    """Lapsed, or open past its time though the job hasn't run since."""
    return c.state == "lapsed" or (c.state == "open" and c.expires_at <= stages.now())


def lapse(db: DbSession) -> str:
    """The job: open claims past their time become lapsed; how many, for the run log. The runner commits."""
    n = db.execute(update(Claim).where(Claim.state == "open", Claim.expires_at <= stages.now())
                   .values(state="lapsed")).rowcount
    return f"истекло заявок: {n}"
