from tests.conftest import open_link, staff_headers
from tests.test_guest_list import LIST, export, upload


def first_link(client) -> str:
    h = staff_headers(client, "admin")
    upload(client, h, LIST)
    return export(client, h)[0]["Ссылка"]


def test_first_visit_asks_consent_then_gives_10(client):
    guest = open_link(client, first_link(client))
    me = client.get("/api/me", headers=guest).json()
    assert me == {"first_name": "Иван", "consented": False, "arrival_points": 0}
    me = client.post("/api/consent", headers=guest).json()
    assert me == {"first_name": "Иван", "consented": True, "arrival_points": 10}


def test_second_visit_and_second_phone_add_nothing(client):
    link = first_link(client)
    client.post("/api/consent", headers=open_link(client, link))
    again = open_link(client, link)
    assert client.get("/api/me", headers=again).json()["consented"] is True
    client.post("/api/consent", headers=again)
    other_phone = open_link(client, link)
    me = client.get("/api/me", headers=other_phone).json()
    assert me == {"first_name": "Иван", "consented": True, "arrival_points": 10}


def test_wrong_code_shows_badge_not_found(client):
    link = first_link(client)
    broken = link[:-1] + ("a" if link[-1] != "a" else "b")
    r = client.get(broken.replace("http://api.test", ""), follow_redirects=False)
    assert r.headers["location"] == "http://app.test/app/welcome?error=badge"


def test_me_needs_a_guest_login(client):
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers={"Authorization": "Bearer junk"}).status_code == 401
    assert client.get("/api/me", headers=staff_headers(client, "desk")).status_code == 401
