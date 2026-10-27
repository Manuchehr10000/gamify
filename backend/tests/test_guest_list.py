import csv
import io

from tests.conftest import staff_headers

LIST = "ID регистрации;Фамилия;Имя;Телефон;Компания\nR-1;Иванов;Иван;+992 90 111 22 33;ТАГ\nR-2;Петрова;Анна;900000002;\n"


def upload(client, headers, text: str, encoding="utf-8"):
    files = {"file": ("guests.csv", text.encode(encoding), "text/csv")}
    return client.post("/api/admin/guests/import", files=files, headers=headers)


def export(client, headers) -> list[dict]:
    r = client.get("/api/admin/guests/export", headers=headers)
    assert r.status_code == 200
    return list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))


def test_import_reports_added_and_failed_rows(client):
    h = staff_headers(client, "admin")
    text = LIST + ";Сидоров;Пётр;;\nR-4;Кузнецов;;;\nR-1;Иванов;Иван;;\n"
    r = upload(client, h, text)
    assert r.status_code == 200
    body = r.json()
    assert body["added"] == 2
    assert body["failed"] == [
        {"row": 4, "reason": "no_reg_id"},
        {"row": 5, "reason": "no_first_name"},
        {"row": 6, "reason": "duplicate_reg_id"},
    ]


def test_import_reads_excel_windows_1251_with_commas(client):
    h = staff_headers(client, "admin")
    r = upload(client, h, "ID,ФИО,Телефон\nR-9,Саидов Фаррух Олимович,992900000009\n", encoding="cp1251")
    assert r.json()["added"] == 1
    row = export(client, h)[0]
    assert (row["Фамилия"], row["Имя"]) == ("Саидов", "Фаррух")


def test_import_without_required_columns_says_which(client):
    r = upload(client, staff_headers(client, "admin"), "Фамилия;Телефон\nИванов;1\n")
    assert r.status_code == 400
    assert r.json()["detail"] == {"code": "missing_columns", "columns": ["reg_id", "first_name"]}


def test_export_gives_each_guest_a_random_link(client):
    h = staff_headers(client, "admin")
    upload(client, h, LIST)
    rows = export(client, h)
    links = [r["Ссылка"] for r in rows]
    assert len(set(links)) == 2
    for row in rows:
        assert row["Ссылка"].startswith("http://api.test/b/")
        assert row["ID регистрации"] not in row["Ссылка"]


def test_reupload_keeps_old_links_and_adds_new_guests(client):
    h = staff_headers(client, "admin")
    upload(client, h, LIST)
    before = {r["ID регистрации"]: r["Ссылка"] for r in export(client, h)}
    r = upload(client, h, LIST + "R-3;Новый;Гость;;\nR-5;Ещё;Один;;\n")
    assert r.json()["added"] == 2
    assert r.json()["updated"] == 2
    after = {r["ID регистрации"]: r["Ссылка"] for r in export(client, h)}
    assert {k: after[k] for k in before} == before
    assert len(after) == 4


def test_admin_screens_need_the_password(client):
    assert client.get("/api/admin/guests/export").status_code == 401
    assert client.post("/api/staff/login", json={"role": "admin", "secret": "nope"}).status_code == 401
    desk = staff_headers(client, "desk")
    assert client.get("/api/admin/guests/export", headers=desk).status_code == 401
