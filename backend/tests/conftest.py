import os

os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://localhost/gamify_test")
os.environ["PUBLIC_BASE_URL"] = "http://api.test"
os.environ["FRONTEND_URL"] = "http://app.test"
os.environ["DESK_PIN"] = "1234"
os.environ["ADMIN_PASSWORD"] = "admin-pass"
os.environ["STAND_PIN"] = "5678"
os.environ["MODERATORS"] = "Модератор 1:1111;Модератор 2:2222;Модератор 3:3333"
os.environ["JOBS_SECRET"] = "jobs-secret"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import accounts  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def schema():
    command.upgrade(Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini")), "head")
    # What the app's start does (TestClient without `with` skips it)
    with SessionLocal() as db:
        accounts.seed_if_empty(db)


@pytest.fixture(autouse=True)
def clean():
    with engine.begin() as c:
        # staff stays: the app's start seeded it once from the values above
        c.execute(text("TRUNCATE guests, sessions, score_events, tasks, stages, prizes, partners, redemptions, submissions, questions, quiz_attempts, levels, badge_awards, job_runs RESTART IDENTITY CASCADE"))
        # The levels the migration starts with: TAG's five
        c.execute(text("INSERT INTO levels (name, min_points) VALUES ('Новичок форума', 0), ('Участник', 50), "
                       "('Актив', 150), ('Эксперт форума', 300), ('Легенда MF', 500)"))


@pytest.fixture
def client():
    return TestClient(app)


def staff_headers(client: TestClient, role: str) -> dict:
    secret = {"desk": "1234", "admin": "admin-pass", "stand": "5678"}[role]
    token = client.post("/api/staff/login", json={"role": role, "secret": secret}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def open_link(client: TestClient, link: str) -> dict:
    """Open a badge link like a phone would; returns the guest's auth header."""
    r = client.get(link.replace("http://api.test", ""), follow_redirects=False)
    assert r.status_code == 302
    location = r.headers["location"]
    assert location.startswith("http://app.test/app/welcome#token=")
    return {"Authorization": f"Bearer {location.split('#token=')[1]}"}


def moderator_headers(client: TestClient, pin: str = "1111") -> dict:
    token = client.post("/api/moderator/login", json={"secret": pin}).json()["token"]
    return {"Authorization": f"Bearer {token}"}
