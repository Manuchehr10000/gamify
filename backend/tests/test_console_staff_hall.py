"""Piece 016 (console look: staff and hall screen) changes only the look of /desk, /stand/:code, /moderate, /hall and
the staff login card. These pin what those screens draw from the API, one test per «How to check it» line that code
can check, and the language-file words the new look shows."""
import json
import re
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from app import stages
from app.db import SessionLocal
from app.models import Guest, Submission
from tests.conftest import moderator_headers, staff_headers
from tests.test_market import buy, make_guest, market, prize, stand  # noqa: F401 (fixtures)
from tests.test_market import load as load_market
from tests.test_moderation import queue, setup
from tests.test_rating import freeze, guests, hall, score
from tests.test_submissions import send_photo
from tests.test_tasks import admin, clock, guest  # noqa: F401 (fixtures)

FRONTEND = Path(__file__).parents[2] / "frontend" / "src"
RU = json.loads((FRONTEND / "locales" / "ru.json").read_text("utf-8"))


# The login card, the same on every staff and admin page

def test_the_desk_pin_opens_the_desk_and_a_wrong_one_says_so(client):
    assert client.post("/api/staff/login", json={"role": "desk", "secret": "1234"}).status_code == 200
    assert client.post("/api/staff/login", json={"role": "desk", "secret": "0000"}).status_code == 401
    assert (RU["staff"]["deskTitle"], RU["staff"]["pin"], RU["staff"]["enter"]) == ("Стойка регистрации", "PIN-код", "Войти")
    # Under the field after a wrong try
    assert RU["staff"]["wrong"] == "Неверный PIN-код или пароль"


def test_admin_guests_opens_with_the_password_on_the_same_card(client):
    assert client.post("/api/staff/login", json={"role": "admin", "secret": "admin-pass"}).status_code == 200
    assert client.post("/api/staff/login", json={"role": "admin", "secret": "1234"}).status_code == 401
    assert RU["staff"]["password"] == "Пароль"
    assert RU["staff"]["adminTitle"] == "Список гостей"


# Desk

def test_searching_kari_gives_the_matching_guests_as_rows_with_their_qr(client):
    desk = staff_headers(client, "desk")
    for first, last in (("Зарина", "Каримова"), ("Карим", "Каримов"), ("Анна", "Петрова")):
        r = client.post("/api/desk/guests", headers=desk, json={"first_name": first, "last_name": last, "phone": "900", "company": ""})
        assert r.status_code == 200, r.text
    found = client.get("/api/desk/guests", params={"q": "Кари"}, headers=desk).json()
    assert sorted(g["last_name"] for g in found) == ["Каримов", "Каримова"]
    # Each row opens the guest's QR card: the link the QR carries
    assert all(g["link"].startswith("http://api.test/b/") for g in found)


def test_searching_for_nobody_says_nobody_was_found(client):
    desk = staff_headers(client, "desk")
    assert client.get("/api/desk/guests", params={"q": "Кари"}, headers=desk).json() == []
    assert RU["desk"]["nothing"] == "Никого не нашли"


# Stand

def test_a_prize_issued_before_shows_when_it_was_given(client, admin, stand, clock):  # noqa: F811
    load_market(client, admin)
    guest = make_guest(client, "R-1", "Иван", coins=100)
    clock("14:30")
    code = prize(buy(client, guest, market(client, guest), "Термокружка").json(), "Термокружка")["code"]
    first = client.post(f"/api/stand/{code}/issue", headers=stand).json()
    assert first["result"] == "issued"
    assert RU["stand"]["issued"] == "Приз выдан"
    clock("15:00")
    # Opened again: the red «Уже выдано в 14:30» instead of the button
    opened = client.get(f"/api/stand/{code}", headers=stand).json()
    assert opened["issued_at"].startswith("2026-12-13T14:30")
    assert (opened["partner"], opened["prize"], opened["first_name"]) == ("Coca-Cola", "Термокружка", "Иван")
    assert client.post(f"/api/stand/{code}/issue", headers=stand).json()["result"] == "already"
    assert RU["stand"]["already"] == "Уже выдано в {{time}}"


def test_a_code_that_does_not_exist_is_one_not_found_card(client, stand):  # noqa: F811
    r = client.get("/api/stand/NOSUCH", headers=stand)
    assert (r.status_code, r.json()["detail"]) == (404, "code_not_found")
    assert RU["stand"]["notFound"] == "Код не найден"


# Moderation

def sent_ago(seconds: int) -> None:
    with SessionLocal() as db:
        for s in db.scalars(select(Submission)):
            s.created_at = stages.now() - timedelta(seconds=seconds)
        db.commit()


def test_moderator_2_sees_their_name_beside_the_waiting_count(client, admin, guest, clock):  # noqa: F811
    t = setup(client, admin, clock)
    mod = moderator_headers(client, "2222")
    empty = queue(client, mod)
    # Nothing waits: «Самая старая ждёт» is left out
    assert (empty["moderator"], empty["waiting"], empty["oldest_seconds"]) == ("Модератор 2", 0, None)
    send_photo(client, guest, t["photo1"])
    sent_ago(seconds=30)
    q = queue(client, mod)
    assert q["waiting"] == 1
    # Under a minute: «меньше минуты»; later «7 мин»
    assert q["oldest_seconds"] == 30
    sent_ago(seconds=7 * 60 + 10)
    assert queue(client, mod)["oldest_seconds"] // 60 == 7
    assert (RU["live"]["waiting"], RU["live"]["oldest"]) == ("Ждут проверки", "Самая старая ждёт")
    assert (RU["moderate"]["oldestNow"], RU["live"]["minutes"]) == ("меньше минуты", "{{count}} мин")
    assert (RU["moderate"]["top20"], RU["moderate"]["empty"]) == ("Топ-20", "Очередь пуста")
    assert RU["moderate"]["penalty"] == "Отклонить со штрафом"


def test_the_queue_is_three_columns_from_1024_two_from_768_one_on_a_phone():
    css = (FRONTEND / "components" / "console" / "console.css").read_text("utf-8")
    grid = dict(re.findall(r"@media \(min-width: (\d+)px\) \{ \.gc-moderation-grid \{ grid-template-columns: repeat\((\d), ", css))
    assert grid == {"768": "2", "1024": "3"}
    assert ".gc-moderation-grid { display: grid; grid-template-columns: minmax(0, 1fr);" in css


def test_at_320px_the_card_buttons_and_the_waiting_panels_wrap_instead_of_spilling():
    css = (FRONTEND / "components" / "console" / "console.css").read_text("utf-8")
    actions = re.search(r"\.gc-moderation-card__actions \{[^}]*\}", css)
    assert actions and "repeat(2, minmax(0, 1fr))" in actions.group(0)
    # «меньше минуты» is shown in full, never cut to «меньше мин…»
    num = re.search(r"\.gc-stat-tile__num \{[^}]*\}", css)
    assert num and "nowrap" not in num.group(0) and "ellipsis" not in num.group(0)


# Hall

def test_the_hall_gives_ten_names_levels_and_points(client):
    g = guests("ID;Имя\n" + "".join(f"R-{i};Гость{i}\n" for i in range(1, 13)))
    for i in range(1, 13):
        score(g[f"Гость{i}"], 400 - i * 10, i)
    top = hall(client)["top"]
    assert [r["place"] for r in top] == list(range(1, 11))
    assert all(r["name"] and r["level"] and r["points"] > 0 for r in top)
    assert top[0]["level"] == "Эксперт форума"
    assert (RU["hall"]["forum"], RU["hall"]["title"]) == ("Форум", "Топ-10")


def test_the_hall_says_when_results_are_frozen_and_when_the_network_drops(client, admin):  # noqa: F811
    g: dict[str, Guest] = guests("ID;Имя\nR-1;Анна\n")
    score(g["Анна"], 10, 1)
    assert freeze(client, admin).status_code == 200
    assert hall(client)["frozen"] is True
    assert RU["hall"]["frozen"] == "Итоги зафиксированы"
    # The page keeps the last top 10 it had and shows this under the stripe
    assert RU["hall"]["offline"] == "Нет связи — показан последний рейтинг"
