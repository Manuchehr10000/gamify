import os

os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://localhost/gamify_test")
os.environ["PUBLIC_BASE_URL"] = "http://api.test"
os.environ["FRONTEND_URL"] = "http://app.test"
os.environ["DESK_PIN"] = "1234"
os.environ["ADMIN_PASSWORD"] = "admin-pass"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def schema():
    command.upgrade(Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini")), "head")


@pytest.fixture(autouse=True)
def clean():
    with engine.begin() as c:
        c.execute(text("TRUNCATE guests, sessions, score_events, tasks, stages RESTART IDENTITY CASCADE"))


@pytest.fixture
def client():
    return TestClient(app)


def staff_headers(client: TestClient, role: str) -> dict:
    secret = "1234" if role == "desk" else "admin-pass"
    token = client.post("/api/staff/login", json={"role": role, "secret": secret}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def open_link(client: TestClient, link: str) -> dict:
    """Open a badge link like a phone would; returns the guest's auth header."""
    r = client.get(link.replace("http://api.test", ""), follow_redirects=False)
    assert r.status_code == 302
    location = r.headers["location"]
    assert location.startswith("http://app.test/app/welcome#token=")
    return {"Authorization": f"Bearer {location.split('#token=')[1]}"}
