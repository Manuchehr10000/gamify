from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from app import badges, changes, hall as screen, levels, rating, settings, stages
from app.auth import current_guest, require_role
from app.db import get_db
from app.models import Guest, Staff
from app.routers.quiz import settle

router = APIRouter()


class HeldBadge(BaseModel):
    code: str
    # The admin's name for it
    name: str
    # Its rule type: the icon for a badge without one of its own
    rule: str


class Place(BaseModel):
    place: int
    # First name and last initial
    name: str
    points: int
    # The level the points reach, shown beside the name
    level: str
    # The badges held now, as small icons beside the name
    badges: list[HeldBadge]


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


def _held(held: list[badges.Held]) -> list[HeldBadge]:
    return [HeldBadge(code=h.code, name=h.name, rule=h.rule) for h in held]


@router.get("/api/rating")
def guest_rating(guest: Guest = Depends(current_guest), db: DbSession = Depends(get_db)) -> Rating:
    # A quiz pays when its time is up, not when its guest next opens the feed
    settle(db)
    frozen, rows = rating.rows(db)
    lv = levels.load(db)
    top = settings.number(db, "rating_top")
    held = badges.earned(db, [r.guest.id for r in rows[:top]])
    mine = next((r for r in rows if r.guest.id == guest.id), None)
    return Rating(
        frozen=frozen,
        top=[GuestPlace(place=r.place, name=rating.guest_name(r.guest.first_name, r.guest.last_name),
                        points=r.points, level=levels.name(lv, r.points), badges=_held(held[r.guest.id]),
                        me=r.guest.id == guest.id)
             for r in rows[:top]],
        me=Mine(place=mine.place, points=mine.points) if mine else None,
    )


class Countdown(BaseModel):
    # quiz · market · stage
    kind: str
    # The quiz's text or the stage's name; empty for the market
    name: str
    at: datetime


class HallLogo(BaseModel):
    id: int
    name: str
    # 1 small · 2 medium · 3 large
    size: int
    # Shown on every Nth logo slide
    every: int
    # Piece 13's GET /api/partners/{id}/logo, with the partner's version
    url: str


class HallPush(BaseModel):
    id: int
    text: str


class HallBadge(BaseModel):
    # The award's id: each screen shows it once
    id: int
    # First name and last initial
    name: str
    badge: str


class Hall(BaseModel):
    frozen: bool
    top: list[Place]
    # auto · live («Эфир сейчас») · logos · pause, as a moderator or admin last switched it
    mode: str
    # «Авто» shows «Эфир» from this time on; None without a schedule
    live_from: datetime | None
    # The server's clock, so a screen with a wrong clock still switches and counts down on time
    now: datetime
    slide_seconds: int
    min_font_px: int
    logos: list[HallLogo]
    # The countdown slide; None skips it
    next: Countdown | None
    # The latest push sent in the last 15 seconds (piece 19), shown once per id
    push: HallPush | None
    # A guest's badge marked «на экран», shown full screen like a push, one at a time; none while a push shows, in
    # «Эфир» or «Пауза»
    badge: HallBadge | None


@router.get("/api/hall")
def hall(db: DbSession = Depends(get_db)) -> Hall:
    """The hall screen: no login, read-only."""
    settle(db)
    frozen, rows = rating.rows(db)
    lv = levels.load(db)
    top = settings.number(db, "hall_top")
    held = badges.earned(db, [r.guest.id for r in rows[:top]])
    places = [Place(place=r.place, name=rating.guest_name(r.guest.first_name, r.guest.last_name), points=r.points,
                    level=levels.name(lv, r.points), badges=_held(held[r.guest.id])) for r in rows[:top]]
    target = screen.next_target(db)
    push = screen.latest_push(db)
    # Commits when it starts a badge: read after the places, so the commit doesn't reload them
    badge = screen.badge_announcement(db, push is not None)
    look = screen.look(db)
    return Hall(frozen=frozen, top=places,
                mode=screen.mode(db), live_from=screen.live_from(db), now=stages.now(),
                slide_seconds=look.slide_seconds, min_font_px=look.min_font_px,
                logos=[HallLogo(id=lg.id, name=lg.name, size=lg.size, every=lg.every, url=lg.url)
                       for lg in screen.logos(db)],
                next=Countdown(kind=target.kind, name=target.name, at=target.at) if target else None,
                push=HallPush(id=push.id, text=push.text) if push else None,
                badge=HallBadge(id=badge.id, name=badge.name, badge=badge.badge) if badge else None)


class ModeIn(BaseModel):
    mode: Literal["auto", "live", "logos", "pause"]


class ModeOut(BaseModel):
    mode: str
    changed_at: datetime


@router.post("/api/hall/mode")
def switch_mode(body: ModeIn, staff: Staff = Depends(require_role("admin", "moderator")),
                db: DbSession = Depends(get_db)) -> ModeOut:
    """«Экран в зале» in /moderate and /admin/live: every screen takes it at its next poll."""
    state = screen.set_mode(db, staff, body.mode)
    return ModeOut(mode=state.mode, changed_at=state.changed_at)


class ShowIn(BaseModel):
    partner_id: int
    started_at: datetime
    seconds: int


class ShowsIn(BaseModel):
    # A screen sends what it logged while offline in one go
    shows: list[ShowIn]


class ShowsOut(BaseModel):
    kept: int


@router.post("/api/hall/logo-shows")
def logo_shows(body: ShowsIn, db: DbSession = Depends(get_db)) -> ShowsOut:
    """No login, like /hall: the server keeps only shows that pass its checks."""
    return ShowsOut(kept=screen.log_shows(db, [screen.Show(s.partner_id, s.started_at, s.seconds)
                                               for s in body.shows[:500]]))


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
def freeze(body: FreezeIn, admin: Staff = Depends(require_role("admin")), db: DbSession = Depends(get_db)) -> Frozen:
    def logged() -> None:
        changes.record(db, admin, "rating", None, "Рейтинг", "frozen", not body.frozen, body.frozen)
        settings.bump(db)
        # «Место» badges follow the freeze: the top N get them, quietly; unfreezing takes them back
        db.flush()
        badges.recheck(db)

    # Freezing again keeps the first freeze and gives its list back, so the admin page can reprint it
    if body.frozen:
        settle(db)
    # The freeze writes every ranked guest's row and rechecks badges: all guests are locked first, in id order, as
    # every other recheck does
    if body.frozen is not None:
        badges.lock_all(db)
    if body.frozen:
        try:
            rating.freeze(db, logged)
        except rating.NothingToFreeze:
            raise HTTPException(409, "nobody_ranked") from None
    elif body.frozen is False:
        rating.unfreeze(db, logged)
    frozen, rows = rating.rows(db)
    return Frozen(frozen=frozen, top=[
        HostPlace(place=r.place, first_name=r.guest.first_name, last_name=r.guest.last_name,
                  company=r.guest.company, points=r.points) for r in rows[:settings.number(db, "hall_top")]] if frozen else [])
