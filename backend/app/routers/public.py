"""What phones, screens and partners read without a login: the config version they poll, partner logos and the
photo links in the partner report."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app import photos, settings
from app.db import get_db
from app.models import Partner, Submission, Task
from app.routers.admin_settings import image_type

router = APIRouter(prefix="/api")


@router.get("/partners/{partner_id}/logo")
def logo(partner_id: int, db: DbSession = Depends(get_db)) -> Response:
    data = db.scalar(select(Partner.logo).where(Partner.id == partner_id))
    if data is None:
        raise HTTPException(404, "logo_not_found")
    # The page adds the partner's version to the URL, so a new logo is a new address
    return Response(data, media_type=image_type(data), headers={
        "X-Content-Type-Options": "nosniff", "Cache-Control": "public, max-age=3600"})


class Version(BaseModel):
    version: int


@router.get("/version")
def config_version(db: DbSession = Depends(get_db)) -> Version:
    """Moves on every admin save: phones and screens poll it every 10 seconds and reload when it moves."""
    return Version(version=settings.version(db))


@router.get("/photos/{token}")
def photo(token: str, db: DbSession = Depends(get_db)) -> Response:
    """A partner task's accepted photo by its random token, until the deletion date. Anything else is not found."""
    data = db.scalar(select(Submission.photo).join(Task, Task.id == Submission.task_id).where(
        Submission.photo_token == token, Submission.status.in_(("accepted", "bonus")), Task.partner_id.is_not(None)))
    if data is None or not photos.links_open(db):
        raise HTTPException(404, "photo_not_found")
    # Never kept by a browser or proxy, so the deletion date holds
    return Response(data, media_type="image/jpeg", headers={
        "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})
