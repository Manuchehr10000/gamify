"""What phones and screens read without a login: the config version they poll, and partner logos."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app import settings
from app.db import get_db
from app.models import Partner
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
