from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db import SessionLocal
from app.guest_list import import_csv
from app.models import Guest, ScoreEvent
from tests.conftest import moderator_headers, open_link, staff_headers
from tests.test_guest_list import export, upload
from tests.test_market import buy, make_guest, market
from tests.test_market import load as load_market
from tests.test_moderation import decide, queue, setup
from tests.test_submissions import send_photo
from tests.test_tasks import admin, clock, guest  # noqa: F401 (fixtures)

T0 = datetime(2026, 12, 13, 5, 0, tzinfo=timezone.utc)


def guests(text: str) -> dict[str, Guest]:
    """Load a guest list and return the guests by first name."""
    with SessionLocal() as db:
        import_csv(db, text.encode())
        return {g.first_name: g for g in db.scalars(select(Guest))}


def score(g: Guest, points: int, minute: int, reason: str | None = None, coins: int = 0) -> None:
    """Give a guest points at T0 + minute, so who reached a score first is known."""
    with SessionLocal() as db:
        db.add(ScoreEvent(guest_id=g.id, reason=reason or f"seed{minute}", points=points, coins=coins,
                          created_at=T0 + timedelta(minutes=minute)))
        db.commit()


def login(client, g: Guest) -> dict:
    return open_link(client, f"http://api.test/b/{g.code}")


def rating(client, h) -> dict:
    r = client.get("/api/rating", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def hall(client) -> dict:
    r = client.get("/api/hall")
    assert r.status_code == 200, r.text
    return r.json()


def freeze(client, h, frozen=True):
    return client.post("/api/admin/rating/freeze", json={"frozen": frozen}, headers=h)


def names(rows) -> list[str]:
    return [r["name"] for r in rows]


def test_ties_go_to_whoever_reached_the_score_first(client):
    g = guests("ID;Фамилия;Имя\nR-1;Алиева;Анна\nR-2;Бобоев;Борис\nR-3;Валиев;Вали\n")
    score(g["Анна"], 120, 1)
    # Вали reached 90 later than Борис, though his first points came earlier
    score(g["Вали"], 50, 2)
    score(g["Борис"], 90, 3)
    score(g["Вали"], 40, 4)
    # A market buy changes only coins: it doesn't move the time Борис reached his score
    score(g["Борис"], 0, 5, reason="buy:1", coins=-10)
    body = rating(client, login(client, g["Вали"]))
    assert [(r["place"], r["name"], r["points"]) for r in body["top"]] == [
        (1, "Анна А.", 120), (2, "Борис Б.", 90), (3, "Вали В.", 90)]
    assert [r["me"] for r in body["top"]] == [False, False, True]
    assert body["me"] == {"place": 3, "points": 90}
    assert body["frozen"] is False


def test_a_guest_outside_the_top_20_sees_their_own_place(client):
    g = guests("ID;Имя\n" + "".join(f"R-{i};Гость{i}\n" for i in range(1, 41)))
    for i in range(1, 41):
        score(g[f"Гость{i}"], 1000 - i * 10, i)
    body = rating(client, login(client, g["Гость34"]))
    assert len(body["top"]) == 20
    assert names(body["top"])[:2] == ["Гость1", "Гость2"]
    assert not any(r["me"] for r in body["top"])
    assert body["me"] == {"place": 34, "points": 660}


def test_hall_needs_no_login_and_follows_new_points(client):
    g = guests("ID;Имя\n" + "".join(f"R-{i};Гость{i}\n" for i in range(1, 13)))
    for i in range(1, 13):
        score(g[f"Гость{i}"], 100 - i, i)
    body = hall(client)
    assert body["frozen"] is False
    assert [r["place"] for r in body["top"]] == list(range(1, 11))
    assert names(body["top"])[0] == "Гость1"
    assert "Гость12" not in names(body["top"])
    # Read-only: nothing else answers without a login
    assert client.post("/api/hall").status_code == 405
    score(g["Гость12"], 500, 20)
    assert names(hall(client)["top"])[0] == "Гость12"


def test_rating_needs_a_logged_in_guest(client):
    assert client.get("/api/rating").status_code == 401
    assert client.get("/api/rating", headers=staff_headers(client, "admin")).status_code == 401


def test_not_ranked_guests_play_and_buy_but_appear_nowhere(client, admin, clock):
    load_market(client, admin)
    h = make_guest(client, "R-1", "Иван")
    # The volunteer is marked «нет» in the guest list
    r = upload(client, admin, "ID регистрации;Имя;В рейтинге\nR-1;Иван;\nR-2;Волонтёр;нет\n")
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        vol = db.scalar(select(Guest).where(Guest.reg_id == "R-2"))
        ivan = db.scalar(select(Guest).where(Guest.reg_id == "R-1"))
    score(ivan, 10, 1)
    score(vol, 5000, 2, coins=100)
    vh = login(client, vol)
    # They still earn and buy
    clock("15:00")
    m = market(client, vh)
    assert m["coins"] == 100
    assert buy(client, vh, m, "Термокружка").status_code == 200
    assert names(rating(client, h)["top"]) == ["Иван"]
    assert rating(client, vh)["me"] is None
    assert names(hall(client)["top"]) == ["Иван"]
    assert [r["first_name"] for r in freeze(client, admin).json()["top"]] == ["Иван"]
    # Download gives the column back
    assert {r["ID регистрации"]: r["В рейтинге"] for r in export(client, admin)} == {"R-1": "да", "R-2": "нет"}
    # A file without the column leaves the mark as it was
    upload(client, admin, "ID регистрации;Имя\nR-2;Волонтёр\n")
    assert {r["ID регистрации"]: r["В рейтинге"] for r in export(client, admin)}["R-2"] == "нет"


def test_not_ranked_guests_stay_out_of_the_top20_moderation_filter(client, admin, guest, clock):
    t = setup(client, admin, clock)
    send_photo(client, guest, t["photo1"])
    upload(client, admin, "ID регистрации;Имя;В рейтинге\nR-1;Иван;\nR-2;Волонтёр;нет\n")
    with SessionLocal() as db:
        vol = db.scalar(select(Guest).where(Guest.reg_id == "R-2"))
    vh = login(client, vol)
    score(vol, 5000, 1)
    send_photo(client, vh, t["photo1"])
    mod = moderator_headers(client)
    assert queue(client, mod)["waiting"] == 2
    assert [i["guest"] for i in queue(client, mod, top20="true")["items"]] == ["Иван"]


def test_freeze_keeps_places_whatever_changes_after(client, admin, guest, clock):
    t = setup(client, admin, clock)
    g = guests("ID;Имя\nR-2;Анна\nR-3;Борис\n")
    score(g["Анна"], 20, 1)
    score(g["Борис"], 10, 2)
    # Иван sends a photo worth 15 points: he is in the top 3
    send_photo(client, guest, t["photo1"])
    live = names(hall(client)["top"])
    assert live == ["Анна", "Иван", "Борис"]
    r = freeze(client, admin)
    assert r.status_code == 200, r.text
    assert r.json()["frozen"] is True
    # A moderator then rejects Иван's photo, and Борис earns more
    mod = moderator_headers(client)
    assert decide(client, mod, queue(client, mod)["items"][0]["id"], "penalty").status_code == 200
    score(g["Борис"], 100, 3)
    body = hall(client)
    assert body["frozen"] is True
    assert names(body["top"]) == live
    assert [r["points"] for r in body["top"]] == [20, 15, 10]
    mine = rating(client, guest)
    assert mine["frozen"] is True
    assert names(mine["top"]) == live
    assert mine["me"] == {"place": 2, "points": 15}
    # Pressing it again keeps the first freeze
    assert [r["first_name"] for r in freeze(client, admin).json()["top"]] == live
    # Undo: live places again
    r = freeze(client, admin, frozen=False)
    assert r.json() == {"frozen": False, "top": []}
    assert hall(client)["frozen"] is False
    assert names(hall(client)["top"]) == ["Борис", "Анна", "Иван"]
    assert rating(client, guest)["me"] == {"place": 3, "points": 0}


def test_frozen_list_has_full_names_companies_and_points(client, admin):
    g = guests("ID;Фамилия;Имя;Компания\n" + "".join(f"R-{i};Фамилия{i};Гость{i};Компания{i}\n" for i in range(1, 13)))
    for i in range(1, 13):
        score(g[f"Гость{i}"], 100 - i, i)
    body = freeze(client, admin).json()
    assert len(body["top"]) == 10
    assert body["top"][0] == {"place": 1, "first_name": "Гость1", "last_name": "Фамилия1", "company": "Компания1",
                              "points": 99}


def test_freeze_needs_the_admin_password(client, guest):
    with SessionLocal() as db:
        g = db.scalar(select(Guest))
    score(g, 10, 1)
    for h in ({}, guest, staff_headers(client, "desk"), moderator_headers(client)):
        assert freeze(client, h).status_code == 401
        assert freeze(client, h, frozen=False).status_code == 401
    assert hall(client)["frozen"] is False


def test_hall_with_nobody_ranked_is_empty(client):
    assert hall(client) == {"frozen": False, "top": []}


def test_freeze_with_nobody_ranked_says_so(client, admin):
    r = freeze(client, admin)
    assert r.status_code == 409
    assert r.json()["detail"] == "nobody_ranked"
    assert hall(client)["frozen"] is False


def test_reading_the_freeze_state_changes_nothing(client, admin):
    g = guests("ID;Имя\nR-2;Анна\n")
    score(g["Анна"], 20, 1)
    assert freeze(client, admin, frozen=None).json() == {"frozen": False, "top": []}
    assert hall(client)["frozen"] is False
    freeze(client, admin)
    assert [r["first_name"] for r in freeze(client, admin, frozen=None).json()["top"]] == ["Анна"]
