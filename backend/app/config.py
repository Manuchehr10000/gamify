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
