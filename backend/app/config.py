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
