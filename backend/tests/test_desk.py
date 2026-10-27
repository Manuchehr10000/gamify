from tests.conftest import open_link, staff_headers
from tests.test_guest_list import LIST, upload


def test_desk_finds_guest_by_phone_or_name(client):
    upload(client, staff_headers(client, "admin"), LIST)
    desk = staff_headers(client, "desk")
    by_phone = client.get("/api/desk/guests", params={"q": "111 22"}, headers=desk).json()
    assert [g["last_name"] for g in by_phone] == ["Иванов"]
    by_name = client.get("/api/desk/guests", params={"q": "анна петр"}, headers=desk).json()
    assert [g["first_name"] for g in by_name] == ["Анна"]


def test_desk_qr_logs_the_phone_in_as_that_guest(client):
    upload(client, staff_headers(client, "admin"), LIST)
    desk = staff_headers(client, "desk")
    found = client.get("/api/desk/guests", params={"q": "900000002"}, headers=desk).json()[0]
    guest = open_link(client, found["link"])
    assert client.get("/api/me", headers=guest).json()["first_name"] == "Анна"


def test_walk_in_gets_a_working_qr(client):
    desk = staff_headers(client, "desk")
    r = client.post("/api/desk/guests", headers=desk,
                    json={"first_name": "Зарина", "last_name": "Каримова", "phone": "+992 93 555 00 11",
                          "company": "Сомон"})
    walk_in = r.json()
    assert walk_in["phone"] == "992935550011"
    guest = open_link(client, walk_in["link"])
    me = client.post("/api/consent", headers=guest).json()
    assert me == {"first_name": "Зарина", "consented": True, "arrival_points": 10}


def test_desk_needs_the_pin(client):
    assert client.get("/api/desk/guests", params={"q": "ив"}).status_code == 401
    assert client.post("/api/staff/login", json={"role": "desk", "secret": "0000"}).status_code == 401
    assert client.post("/api/desk/guests", json={"first_name": "A", "phone": "1"}).status_code == 401
