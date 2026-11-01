from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from app import levels, rating
from app.auth import current_guest, require_role
from app.db import get_db
from app.models import Guest
from app.routers.quiz import settle

router = APIRouter()

TOP = 20
HALL_TOP = 10


class Place(BaseModel):
    place: int
    # First name and last initial
    name: str
    points: int
    # The level the points reach, shown beside the name
    level: str


class GuestPlace(Place):
    me: bool


class Mine(BaseModel):
    place: int
    points: int


class Rating(BaseModel):
    frozen: bool
    top: list[GuestPlace]
    # The guest's own place; None when they aren't ranked (no points yet, or «В рейтинге: нет»)
    me: Mine | None


@router.get("/api/rating")
def guest_rating(guest: Guest = Depends(current_guest), db: DbSession = Depends(get_db)) -> Rating:
    # A quiz pays when its time is up, not when its guest next opens the feed
    settle(db)
    frozen, rows = rating.rows(db)
    lv = levels.load(db)
    mine = next((r for r in rows if r.guest.id == guest.id), None)
    return Rating(
        frozen=frozen,
        top=[GuestPlace(place=r.place, name=rating.guest_name(r.guest.first_name, r.guest.last_name),
                        points=r.points, level=levels.name(lv, r.points), me=r.guest.id == guest.id)
             for r in rows[:TOP]],
        me=Mine(place=mine.place, points=mine.points) if mine else None,
    )


class Hall(BaseModel):
    frozen: bool
    top: list[Place]


@router.get("/api/hall")
def hall(db: DbSession = Depends(get_db)) -> Hall:
    """The hall screen: no login, read-only."""
    settle(db)
    frozen, rows = rating.rows(db)
    lv = levels.load(db)
    return Hall(frozen=frozen, top=[Place(place=r.place, name=rating.guest_name(r.guest.first_name, r.guest.last_name),
                                          points=r.points, level=levels.name(lv, r.points)) for r in rows[:HALL_TOP]])


class FreezeIn(BaseModel):
    # True freezes, False unfreezes, None only reads the current state (the admin page on load)
    frozen: bool | None


class HostPlace(BaseModel):
    place: int
    first_name: str
    last_name: str
    company: str
    points: int


class Frozen(BaseModel):
    frozen: bool
    # The top 10 with full names and companies, for the host to read out; empty when not frozen
    top: list[HostPlace]


@router.post("/api/admin/rating/freeze", dependencies=[Depends(require_role("admin"))])
def freeze(body: FreezeIn, db: DbSession = Depends(get_db)) -> Frozen:
    # Freezing again keeps the first freeze and gives its list back, so the admin page can reprint it
    if body.frozen:
        settle(db)
        try:
            rating.freeze(db)
        except rating.NothingToFreeze:
            raise HTTPException(409, "nobody_ranked") from None
    elif body.frozen is False:
        rating.unfreeze(db)
    frozen, rows = rating.rows(db)
    return Frozen(frozen=frozen, top=[
        HostPlace(place=r.place, first_name=r.guest.first_name, last_name=r.guest.last_name,
                  company=r.guest.company, points=r.points) for r in rows[:HALL_TOP]] if frozen else [])
