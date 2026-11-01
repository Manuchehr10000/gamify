import csv
import io
from datetime import timedelta

from sqlalchemy import select, update

from app import stages
from app.db import SessionLocal
from app.models import Prize, Redemption, ScoreEvent, Submission
from tests.conftest import moderator_headers, staff_headers
from tests.test_market import load, make_guest
from tests.test_moderation import decide
from tests.test_qr_tasks import row
from tests.test_submissions import ids, send_photo, send_text
from tests.test_tasks import admin, clock  # noqa: F401 (fixtures)


def typed(type_, *args, **kw):
    r = row(*args, **kw)
    r[2] = type_
    return r


TASKS = [
    typed("Селфи", "selfie", 1, "Селфи у входа", method="Фото"),
    typed("Действие", "text", 1, "Напишите отзыв", method="Текст"),
    typed("Селфи", "cola", 1, "Фото с бутылкой", method="Фото", partner="Кока-Кола", package="MF Партнёр"),
    typed("Действие", "cola2", 1, "Отзыв о напитке", method="Текст", partner="Кока-Кола", package="MF Партнёр"),
    typed("Действие", "alif", 2, "Отзыв об Алифе", method="Текст", partner="Алиф", package="Генеральный партнёр"),
]


def live(client, admin):
    r = client.get("/api/admin/live", headers=admin)
    assert r.status_code == 200, r.text
    return r.json()


def report(client, admin) -> list[list[str]]:
    r = client.get("/api/admin/partners/export", headers=admin)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert r.content.startswith("﻿".encode())
    return list(csv.reader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))


def partner(page: dict, name: str) -> dict:
    return next(p for p in page["partners"] if p["partner"] == name)


def setup(client, admin, clock) -> dict[str, int]:
    load(client, admin, tasks=TASKS)
    clock("09:30")
    return ids(client, admin)


def recent(minutes: int = 1) -> None:
    """Date everything guests did to the server clock: rows are stamped by the database, the tests' clock is moved."""
    at = stages.now() - timedelta(minutes=minutes)
    with SessionLocal() as db:
        for model in (ScoreEvent, Submission, Redemption):
            db.execute(update(model).values(created_at=at))
        db.commit()


def test_live_and_report_need_the_admin_password(client, admin):
    guest = make_guest(client, "R-1", "Иван")
    for h in ({}, guest, staff_headers(client, "desk"), moderator_headers(client)):
        assert client.get("/api/admin/live", headers=h).status_code == 401
        assert client.get("/api/admin/partners/export", headers=h).status_code == 401


def test_three_logged_in_two_active(client, admin, clock):
    t = setup(client, admin, clock)
    guests = [make_guest(client, f"R-{n}", name) for n, name in enumerate(["Иван", "Анна", "Олег"], start=1)]
    # Arriving gives +10, which is part of logging in, not activity
    for g in guests:
        client.post("/api/consent", headers=g)
    page = live(client, admin)
    assert (page["logged_in"], page["active"]) == (3, 0)
    send_text(client, guests[0], t["text"], "Отлично")
    send_photo(client, guests[1], t["selfie"])
    recent()
    page = live(client, admin)
    assert (page["logged_in"], page["active"]) == (3, 2)
    # A second phone on the same badge is still one guest
    make_guest(client, "R-1", "Иван")
    assert live(client, admin)["logged_in"] == 3


def test_activity_older_than_15_minutes_drops_off(client, admin, clock):
    t = setup(client, admin, clock)
    g = make_guest(client, "R-1", "Иван")
    send_text(client, g, t["text"], "Отлично")
    recent(minutes=16)
    assert live(client, admin)["active"] == 0
    recent(minutes=14)
    assert live(client, admin)["active"] == 1


def test_a_purchase_counts_as_activity(client, admin, clock):
    load(client, admin, tasks=TASKS)
    g = make_guest(client, "R-1", "Иван", coins=100)
    clock("14:30")
    with SessionLocal() as db:
        prize_id = db.scalar(select(Prize.id).where(Prize.code == "P3"))
    assert client.post(f"/api/market/{prize_id}/buy", headers=g).status_code == 200
    with SessionLocal() as db:
        db.execute(update(ScoreEvent).values(created_at=stages.now() - timedelta(hours=1)))
        db.execute(update(Redemption).values(created_at=stages.now() - timedelta(minutes=2)))
        db.commit()
    assert live(client, admin)["active"] == 1


def test_partner_completion_goes_up_by_one(client, admin, clock):
    t = setup(client, admin, clock)
    ivan, anna = make_guest(client, "R-1", "Иван"), make_guest(client, "R-2", "Анна")
    assert live(client, admin)["partners"] == []
    send_photo(client, ivan, t["cola"])
    assert partner(live(client, admin), "Кока-Кола") == {"partner": "Кока-Кола", "completions": 1, "guests": 1}
    send_text(client, ivan, t["cola2"], "Вкусно")
    send_text(client, anna, t["cola2"], "Освежает")
    clock("11:00")
    send_text(client, anna, t["alif"], "Удобно")
    page = live(client, admin)
    # Sorted by completions
    assert page["partners"] == [{"partner": "Кока-Кола", "completions": 3, "guests": 2},
                                {"partner": "Алиф", "completions": 1, "guests": 1}]


def test_completions_by_type_and_stage(client, admin, clock):
    t = setup(client, admin, clock)
    ivan, anna = make_guest(client, "R-1", "Иван"), make_guest(client, "R-2", "Анна")
    send_photo(client, ivan, t["selfie"])
    send_photo(client, anna, t["selfie"])
    send_photo(client, ivan, t["cola"])
    send_text(client, ivan, t["text"], "Отлично")
    clock("11:00")
    send_text(client, anna, t["alif"], "Удобно")
    page = live(client, admin)
    assert page["by_type"] == [{"name": "selfie", "completions": 3}, {"name": "action", "completions": 2}]
    assert [(s["number"], s["name"], s["completions"]) for s in page["by_stage"]] == [
        (1, "Начало", 4), (2, "Первые победы", 1), (3, "Спад и разочарование", 0), (4, "Последняя гонка", 0)]


def test_four_waiting_oldest_six_minutes(client, admin, clock):
    t = setup(client, admin, clock)
    assert (live(client, admin)["waiting"], live(client, admin)["oldest_seconds"]) == (0, None)
    ivan, anna = make_guest(client, "R-1", "Иван"), make_guest(client, "R-2", "Анна")
    for g in (ivan, anna):
        send_photo(client, g, t["selfie"])
        send_photo(client, g, t["cola"])
    with SessionLocal() as db:
        for n, s in enumerate(db.scalars(select(Submission).order_by(Submission.id))):
            s.created_at = stages.now() - timedelta(minutes=6 - n)
        db.commit()
    page = live(client, admin)
    assert (page["waiting"], page["oldest_seconds"]) == (4, 360)
    # A decided one leaves the count
    mod = moderator_headers(client)
    with SessionLocal() as db:
        oldest = db.scalar(select(Submission.id).order_by(Submission.id).limit(1))
    decide(client, mod, oldest, "accept")
    page = live(client, admin)
    assert (page["waiting"], page["oldest_seconds"]) == (3, 300)


def test_market_bought_issued_and_left(client, admin, clock):
    load(client, admin, tasks=TASKS)
    clock("14:30")
    page = live(client, admin)
    # The file's prizes: 5 + 1 + 100
    assert (page["bought"], page["issued"], page["left"]) == (0, 0, 106)
    with SessionLocal() as db:
        prizes = {p.code: p.id for p in db.scalars(select(Prize))}
    ivan, anna = make_guest(client, "R-1", "Иван", coins=100), make_guest(client, "R-2", "Анна", coins=100)
    client.post(f"/api/market/{prizes['P1']}/buy", headers=ivan)
    client.post(f"/api/market/{prizes['P2']}/buy", headers=ivan)
    client.post(f"/api/market/{prizes['P1']}/buy", headers=anna)
    with SessionLocal() as db:
        code = db.scalar(select(Redemption.code).order_by(Redemption.id).limit(1))
    assert client.post(f"/api/stand/{code}/issue", headers=staff_headers(client, "stand")).status_code == 200
    page = live(client, admin)
    assert (page["bought"], page["issued"], page["left"]) == (3, 1, 103)


def test_partner_report_has_each_partner_task_in_cyrillic(client, admin, clock):
    t = setup(client, admin, clock)
    ivan, anna = make_guest(client, "R-1", "Иван"), make_guest(client, "R-2", "Анна")
    send_photo(client, ivan, t["cola"])
    send_photo(client, anna, t["cola"])
    send_text(client, ivan, t["cola2"], "Вкусно")
    # Tasks without a partner aren't in it
    send_photo(client, ivan, t["selfie"])
    assert report(client, admin) == [
        ["Партнёр", "Пакет", "Задание", "Выполнений", "Уникальных участников"],
        ["Алиф", "Генеральный партнёр", "Отзыв об Алифе", "0", "0"],
        ["Кока-Кола", "MF Партнёр", "Фото с бутылкой", "2", "2"],
        ["Кока-Кола", "MF Партнёр", "Отзыв о напитке", "1", "1"],
    ]


def test_partner_report_keeps_task_text_that_looks_like_a_formula(client, admin, clock):
    load(client, admin, tasks=[typed("Действие", "promo", 1, "-20% на кофе у стенда", method="Текст",
                                     partner="@Кофе", package="MF Партнёр")])
    assert report(client, admin)[1][:3] == ["'@Кофе", "MF Партнёр", "'-20% на кофе у стенда"]


def test_rejected_partner_photos_are_not_counted(client, admin, clock):
    t = setup(client, admin, clock)
    ivan, anna, oleg = (make_guest(client, f"R-{n}", name) for n, name in enumerate(["Иван", "Анна", "Олег"], 1))
    for g in (ivan, anna, oleg):
        send_photo(client, g, t["cola"])
    assert partner(live(client, admin), "Кока-Кола")["completions"] == 3
    mod = moderator_headers(client)
    with SessionLocal() as db:
        first, second, third = db.scalars(select(Submission.id).order_by(Submission.id)).all()
    decide(client, mod, first, "penalty")
    decide(client, mod, second, "retake")
    decide(client, mod, third, "accept")
    assert partner(live(client, admin), "Кока-Кола") == {"partner": "Кока-Кола", "completions": 1, "guests": 1}
    assert live(client, admin)["by_type"] == [{"name": "selfie", "completions": 1}]
    cola = next(r for r in report(client, admin) if r[2] == "Фото с бутылкой")
    assert cola[3:] == ["1", "1"]
    # A retaken photo that is sent again counts again
    send_photo(client, anna, t["cola"])
    assert partner(live(client, admin), "Кока-Кола")["completions"] == 2
