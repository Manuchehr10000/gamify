from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app import ledger, stages
from app.auth import current_guest
from app.db import get_db
from app.guests import random_code
from app.models import Guest, Prize, Redemption, Task
from app.routers.feed import partners, task_reason, totals
from app.stages import EVENT_TZ

router = APIRouter(prefix="/api/market")


class PrizeOut(BaseModel):
    id: int
    name: str
    partner: str
    price: int
    left: int
    # The guest's purchase: the code in their stand QR, and when the stand handed the prize over
    code: str | None
    issued_at: datetime | None


class Market(BaseModel):
    coins: int
    open: bool
    # None: no stage is marked «Маркет» yet
    opens_at: datetime | None
    prizes: list[PrizeOut]


def local(dt: datetime | None) -> datetime | None:
    return dt.astimezone(EVENT_TZ) if dt else None


def _sold(db: DbSession) -> dict[int, int]:
    return dict(db.execute(select(Redemption.prize_id, func.count()).group_by(Redemption.prize_id)).all())


def _market(db: DbSession, guest: Guest) -> Market:
    opens_at = stages.market_opens_at(db)
    mine = {r.prize_id: r for r in db.scalars(select(Redemption).where(Redemption.guest_id == guest.id))}
    sold = _sold(db)
    by_id = partners(db)
    # A prize removed from the file stays on the screen of a guest who already bought it
    prizes = [p for p in db.scalars(select(Prize).order_by(Prize.position, Prize.id)) if p.active or p.id in mine]
    return Market(
        coins=totals(db, guest)[1],
        open=opens_at is not None and stages.now() >= opens_at,
        opens_at=local(opens_at),
        prizes=[PrizeOut(id=p.id, name=p.name, partner=by_id[p.partner_id].name, price=p.price,
                         left=max(0, p.quantity - sold.get(p.id, 0)),
                         code=mine[p.id].code if p.id in mine else None,
                         issued_at=local(mine[p.id].issued_at) if p.id in mine else None) for p in prizes],
    )


@router.get("")
def market(guest: Guest = Depends(current_guest), db: DbSession = Depends(get_db)) -> Market:
    return _market(db, guest)


def _new_code(db: DbSession) -> str:
    while True:
        code = random_code(6)
        if not db.scalar(select(Redemption.id).where(Redemption.code == code)):
            return code


@router.post("/{prize_id}/buy")
def buy(prize_id: int, guest: Guest = Depends(current_guest), db: DbSession = Depends(get_db)) -> Market:
    # Lock the guest, then the prize: one guest's two taps can't spend the same coins twice,
    # and two guests after the last item take turns, so only one of them gets it
    db.execute(select(Guest.id).where(Guest.id == guest.id).with_for_update())
    prize = db.scalar(select(Prize).where(Prize.id == prize_id).with_for_update())
    if prize is None or not prize.active:
        raise HTTPException(404, "prize_not_found")
    opens_at = stages.market_opens_at(db)
    if opens_at is None or stages.now() < opens_at:
        raise HTTPException(409, "market_closed")
    if db.scalar(select(Redemption.id).where(Redemption.guest_id == guest.id, Redemption.prize_id == prize.id)):
        raise HTTPException(409, "already_bought")
    if _sold(db).get(prize.id, 0) >= prize.quantity:
        raise HTTPException(409, "sold_out")
    # The stored total, read under the guest's lock
    if totals(db, guest)[1] < prize.price:
        raise HTTPException(409, "not_enough_coins")
    db.add(Redemption(guest_id=guest.id, prize_id=prize.id, code=_new_code(db)))
    ledger.write(db, guest.id, f"buy:{prize.id}", "buy", 0, -prize.price)
    # «Выполнение» = Маркет: the first purchase completes the task, once
    for t in db.scalars(select(Task).where(Task.active, Task.method == "market")):
        ledger.write(db, guest.id, task_reason(t.id), "task", t.points, t.coins)
    db.commit()
    return _market(db, guest)
