"""The job runner. A Cloudflare cron calls POST /api/jobs/run every minute; each registered job runs in turn, in
its own transaction, and every run of every job is logged in job_runs with its start, end and result."""
from collections.abc import Callable

from sqlalchemy import text, update
from sqlalchemy.orm import Session as DbSession

from app import claims, push, stages
from app.db import SessionLocal
from app.models import JobRun

# (name, job) in the order they run. A later piece appends its job here: photo deletion
# Each job returns a short note of what it did, kept in the run log
JOBS: list[tuple[str, Callable[[DbSession], str]]] = [
    ("lapsed_claims", claims.lapse),
    ("push", push.run),
]

# One run at a time: a run that finds the previous one still going is logged as skipped
RUN_LOCK = 7012


def run_all() -> list[JobRun]:
    with SessionLocal() as log:
        # Held by this transaction until the run ends; the log rows are committed on their own connection below
        if not log.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": RUN_LOCK}):
            with SessionLocal() as db:
                skipped = JobRun(job="*", started_at=stages.now(), finished_at=stages.now(), result="skipped")
                db.add(skipped)
                db.commit()
            return [skipped]
        # This run holds the lock, so a job still open is from a run whose process died: close it as failed
        with SessionLocal() as db:
            db.execute(update(JobRun).where(JobRun.finished_at.is_(None))
                       .values(result="failed", error="прерван", finished_at=stages.now()))
            db.commit()
        return [_run(name, job) for name, job in JOBS]


def _run(name: str, job: Callable[[DbSession], str]) -> JobRun:
    """One job, in its own session: a failure is logged and rolled back, and the next job still runs."""
    with SessionLocal() as db:
        run = JobRun(job=name, started_at=stages.now())
        db.add(run)
        db.commit()
        with SessionLocal() as work:
            try:
                detail = job(work)
                work.commit()
                run.result, run.detail = "ok", detail
            except Exception as e:  # noqa: BLE001 — any error is the job's result, not the runner's
                work.rollback()
                run.result, run.error = "failed", f"{type(e).__name__}: {e}"
        run.finished_at = stages.now()
        db.commit()
        return run
