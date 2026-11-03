import hmac
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app import config, jobs


def worker_only(x_jobs_secret: str = Header(default="")) -> None:
    """Only the Cloudflare Worker's scheduled trigger knows JOBS_SECRET. Unset: every call is refused."""
    if not config.JOBS_SECRET or not hmac.compare_digest(x_jobs_secret.encode(), config.JOBS_SECRET.encode()):
        raise HTTPException(401, "not_allowed")


router = APIRouter(prefix="/api/jobs", dependencies=[Depends(worker_only)])


class Run(BaseModel):
    job: str
    started_at: datetime
    finished_at: datetime | None
    # ok · failed · skipped
    result: str
    error: str
    # What an ok run did, e.g. how many claims lapsed
    detail: str


@router.post("/run")
def run() -> list[Run]:
    return [Run(job=r.job, started_at=r.started_at, finished_at=r.finished_at, result=r.result, error=r.error,
                detail=r.detail)
            for r in jobs.run_all()]
