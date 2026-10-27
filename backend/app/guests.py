import re
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app import config
from app.models import Guest

# No 0/o, 1/l/i: a code read aloud at the desk can't be mistaken
CODE_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def new_code(db: DbSession) -> str:
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(10))
        if not db.scalar(select(Guest.id).where(Guest.code == code)):
            return code


def link(guest: Guest) -> str:
    return f"{config.PUBLIC_BASE_URL}/b/{guest.code}"


def clean_phone(raw: str) -> str:
    return re.sub(r"\D", "", raw or "")
