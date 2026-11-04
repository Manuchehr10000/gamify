import os

from dotenv import load_dotenv

load_dotenv()


def _database_url() -> str:
    url = os.environ["DATABASE_URL"]
    # Railway gives postgres:// or postgresql://; SQLAlchemy needs the psycopg driver named
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = _database_url()
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173").rstrip("/")
# The Cloudflare Worker's shared secret for POST /api/jobs/run; unset: the job endpoint refuses every call
JOBS_SECRET = os.environ.get("JOBS_SECRET", "")
# How many days Neon's restore history (point-in-time restore) keeps old data: the photo deletion job logs the day
# the photos leave it too. Infrastructure, not a game setting
NEON_RESTORE_DAYS = int(os.environ.get("NEON_RESTORE_DAYS") or "7")
# Web push (VAPID): the public key goes to phones in /api/me, the private key signs each push, the subject is a
# mailto: or https: address the push services can reach. Any one unset: phones are never asked and nothing is sent
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "")
# The staff secrets below fill an empty staff table once, at app start (app.accounts); after that they are ignored
DESK_PIN = os.environ.get("DESK_PIN", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
# One PIN shared by the partner stands in the market
STAND_PIN = os.environ.get("STAND_PIN", "")


def _moderators(raw: str) -> list[tuple[str, str]]:
    """«Модератор 1:PIN;Модератор 2:PIN» → [(name, pin)]. Entries without a PIN are left out."""
    pairs = []
    for entry in raw.split(";"):
        name, _, pin = entry.rpartition(":")
        if name.strip() and pin.strip():
            pairs.append((name.strip(), pin.strip()))
    # A shared PIN would log one moderator's decisions under another's name
    for i, what in ((0, "name"), (1, "PIN")):
        values = [p[i] for p in pairs]
        if len(set(values)) != len(values):
            raise ValueError(f"MODERATORS: each moderator needs their own {what}")
    return pairs


# Each moderator has their own PIN, so decisions are logged under their name
MODERATORS = _moderators(os.environ.get("MODERATORS", ""))
