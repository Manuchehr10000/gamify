from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app import stages
from app.auth import require_role
from app.db import get_db
from app.models import Guest, Partner, Prize, Redemption
from app.routers.market import local

# Partner stands scan a guest's market QR and hand the prize over
router = APIRouter(prefix="/api/stand", dependencies=[Depends(require_role("stand"))])


class Handover(BaseModel):
    prize: str
    partner: str
    first_name: str
    issued_at: datetime | None


class Issue(BaseModel):
    # issued: handed over now · already: handed over before
    result: str
    handover: Handover


def _redemption(db: DbSession, code: str, lock: bool = False) -> Redemption:
    q = select(Redemption).where(Redemption.code == code.strip().lower())
    r = db.scalar(q.with_for_update() if lock else q)
    if r is None:
        raise HTTPException(404, "code_not_found")
    return r


def _handover(db: DbSession, r: Redemption) -> Handover:
    prize = db.get(Prize, r.prize_id)
    return Handover(prize=prize.name, partner=db.get(Partner, prize.partner_id).name, first_name=db.get(Guest, r.guest_id).first_name,
                    issued_at=local(r.issued_at))


@router.get("/{code}")
def handover(code: str, db: DbSession = Depends(get_db)) -> Handover:
    return _handover(db, _redemption(db, code))


@router.post("/{code}/issue")
def issue(code: str, db: DbSession = Depends(get_db)) -> Issue:
    # Locked so two stand phones tapping «Выдано» at once give the prize out once
    r = _redemption(db, code, lock=True)
    if r.issued_at is not None:
        return Issue(result="already", handover=_handover(db, r))
    r.issued_at = stages.now()
    db.commit()
    return Issue(result="issued", handover=_handover(db, r))
