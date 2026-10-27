from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DbSession

from app.auth import require_role
from app.db import get_db
from app.guests import clean_phone, link, new_code
from app.models import Guest

router = APIRouter(prefix="/api/desk/guests", dependencies=[Depends(require_role("desk"))])


class DeskGuest(BaseModel):
    id: int
    first_name: str
    last_name: str
    phone: str
    company: str
    link: str


class WalkIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(default="", max_length=100)
    phone: str = Field(min_length=1, max_length=32)
    company: str = Field(default="", max_length=200)


def _out(g: Guest) -> DeskGuest:
    return DeskGuest(id=g.id, first_name=g.first_name, last_name=g.last_name, phone=g.phone,
                     company=g.company, link=link(g))


@router.get("")
def search(q: str, db: DbSession = Depends(get_db)) -> list[DeskGuest]:
    q = q.strip()
    if len(q) < 2:
        return []
    # "Иванов Иван" and "Иван Иванов" both match. ICU lowercases Cyrillic whatever the database's locale
    name = func.lower((Guest.last_name + " " + Guest.first_name + " " + Guest.last_name).collate("und-x-icu"))
    conditions = [name.contains(q.lower())]
    digits = clean_phone(q)
    if len(digits) >= 3:
        conditions.append(Guest.phone.contains(digits))
    guests = db.scalars(select(Guest).where(or_(*conditions)).order_by(Guest.last_name).limit(20))
    return [_out(g) for g in guests]


@router.post("")
def add_walk_in(body: WalkIn, db: DbSession = Depends(get_db)) -> DeskGuest:
    guest = Guest(code=new_code(db), first_name=body.first_name.strip(), last_name=body.last_name.strip(),
                  phone=clean_phone(body.phone), company=body.company.strip())
    db.add(guest)
    db.commit()
    return _out(guest)
