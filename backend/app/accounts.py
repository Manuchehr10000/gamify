"""Staff accounts: admin, moderator, desk and stand. Secrets are stored as bcrypt hashes; the PIN or password alone
says which account it is, within the role of the login screen it was typed into."""
import hashlib
import logging

import bcrypt
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session as DbSession

from app import config
from app.models import Staff

log = logging.getLogger(__name__)


def _key(secret: str) -> bytes:
    # bcrypt reads at most 72 bytes; the digest keeps a long password whole
    return hashlib.sha256(secret.encode()).hexdigest().encode()


def hash_secret(secret: str) -> str:
    return bcrypt.hashpw(_key(secret), bcrypt.gensalt()).decode()


def taken(db: DbSession, role: str, secret: str, account_id: int | None = None) -> bool:
    """Another account of the role, switched off or not, already has this secret: it would no longer say who is
    logging in."""
    return any(bcrypt.checkpw(_key(secret), a.secret_hash.encode())
               for a in db.scalars(select(Staff).where(Staff.role == role, Staff.id != (account_id or 0))))


def find(db: DbSession, role: str, secret: str) -> Staff | None:
    """The account of this role whose secret this is; None for a wrong or empty one."""
    if not secret:
        return None
    for account in db.scalars(select(Staff).where(Staff.role == role, Staff.active).order_by(Staff.id)):
        if bcrypt.checkpw(_key(secret), account.secret_hash.encode()):
            return account
    return None


def seed_if_empty(db: DbSession) -> None:
    """Run at every start: an empty staff table is filled once from DESK_PIN, STAND_PIN, MODERATORS and
    ADMIN_PASSWORD. Once it holds an account, the environment values are ignored."""
    # Two starts at once seed only once
    db.execute(text("LOCK TABLE staff IN EXCLUSIVE MODE"))
    if db.scalar(select(func.count()).select_from(Staff)):
        db.rollback()
        return
    accounts = [("Администратор", "admin", config.ADMIN_PASSWORD), ("Стойка регистрации", "desk", config.DESK_PIN),
                ("Стенды партнёров", "stand", config.STAND_PIN)]
    accounts += [(name, "moderator", pin) for name, pin in config.MODERATORS]
    rows = [Staff(name=name, role=role, secret_hash=hash_secret(secret))
            for name, role, secret in accounts if secret]
    if not rows:
        log.warning("Нет ни одного сотрудника, а DESK_PIN, STAND_PIN, MODERATORS и ADMIN_PASSWORD не заданы: "
                    "войти в админку, на стойку, стенд и модерацию нельзя")
    db.add_all(rows)
    db.commit()
