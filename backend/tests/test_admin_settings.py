import io
import struct

import pytest
from openpyxl import load_workbook
from sqlalchemy import select, text

from app.db import SessionLocal
from app.models import Guest
from tests.conftest import moderator_headers, staff_headers
from tests.test_qr_tasks import HEAD, ROWS, load, row
from tests.test_quiz import at, questions, quiz, xlsx as quiz_xlsx  # noqa: F401 (fixtures)
from tests.test_tasks import STAGES, admin, catalog, clock, feed, guest, upload, xlsx  # noqa: F401 (fixtures)

PNG = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + b"\x00" * 17


def rows(client, admin, kind) -> dict:
    r = client.get(f"/api/admin/lists/{kind}", headers=admin)
    assert r.status_code == 200, r.text
    return r.json()


def find(client, admin, kind, key, value) -> dict:
    return next(r for r in rows(client, admin, kind)["rows"] if r["values"][key] == value)


def save(client, h, kind, r, confirm=False, **values):
    path = f"/api/admin/lists/{kind}/{r['id']}" + ("?confirm=true" if confirm else "")
    return client.put(path, json={"values": values, "version": r["version"]}, headers=h)


def log(client, h, **params) -> list[dict]:
    r = client.get("/api/admin/log", params=params, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def card(client, guest, code_text):
    return next((t for t in feed(client, guest)["tasks"] if t["text"] == code_text), None)


def preview(client, h, data: bytes) -> dict:
    files = {"file": ("tasks.xlsx", data, "application/octet-stream")}
    r = client.post("/api/admin/tasks/import/preview", files=files, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def version(client) -> int:
    return client.get("/api/version").json()["version"]


def test_a_task_points_change_reaches_phones_and_the_log(client, admin, guest, clock):
    load(client, admin, ROWS)
    clock("09:30")
    assert card(client, guest, "Сфотографировать небо")["points"] == 10
    before = version(client)
    task = find(client, admin, "tasks", "code", "plain")
    r = save(client, admin, "tasks", task, points=25)
    assert r.status_code == 200, r.text
    assert r.json()["version"] == task["version"] + 1
    # The phones poll the version and reload the feed when it moves
    assert version(client) > before
    assert card(client, guest, "Сфотографировать небо")["points"] == 25
    event = next(e for e in log(client, admin, kind="tasks", item="plain") if e["field"] == "points")
    assert (event["staff_name"], event["item"], event["field"], event["old_value"], event["new_value"],
            event["source"]) == ("Администратор", "plain", "points", "10", "25", "form")


def test_a_value_outside_its_limits_is_refused_naming_field_and_range(client, admin):
    load(client, admin, ROWS)
    task = find(client, admin, "tasks", "code", "plain")
    r = save(client, admin, "tasks", task, points=100000)
    assert (r.status_code, r.json()["detail"]) == (400, {"code": "out_of_range", "field": "points", "min": 0,
                                                          "max": 10000})
    assert find(client, admin, "tasks", "code", "plain")["values"]["points"] == 10
    s = next(s for s in client.get("/api/admin/settings", headers=admin).json() if s["key"] == "hall_top")
    r = client.put("/api/admin/settings/hall_top", json={"value": 50, "version": s["version"]}, headers=admin)
    assert (r.status_code, r.json()["detail"]) == (400, {"code": "out_of_range", "field": "hall_top", "min": 3,
                                                          "max": 30})
    # The form lists each field's limits and effect rule
    points = next(f for f in rows(client, admin, "tasks")["fields"] if f["name"] == "points")
    assert (points["min"], points["max"], points["effect"]) == (0, 10000, "now")


def test_questions_are_locked_while_the_blitz_is_open(client, admin, guest, at):
    data = quiz_xlsx([quiz("B1", "Блиц", start="13.12.2026 09:00", end="13.12.2026 09:10"),
                      quiz("T1", "С таймером", timer=60)], questions("B1", 2) + questions("T1", 2))
    assert upload(client, admin, data).json()["failed"] == []
    at("09:05:00")
    blitz = [q for q in rows(client, admin, "questions")["rows"] if q["values"]["number"] == 1]
    for q in blitz:
        r = save(client, admin, "questions", q, text="Новый вопрос")
        if q["values"]["task_id"] == find(client, admin, "tasks", "code", "B1")["id"]:
            assert (r.status_code, r.json()["detail"]) == (409, {"code": "quiz_running"})
    b1 = find(client, admin, "tasks", "code", "B1")["id"]
    r = client.post("/api/admin/lists/questions", headers=admin, json={"values": {
        "task_id": b1, "number": 3, "text": "Ещё", "option1": "А", "option2": "Б", "correct": 1}})
    assert (r.status_code, r.json()["detail"]) == (409, {"code": "quiz_running"})
    # An upload changing them is refused too, naming the quiz's row
    data = quiz_xlsx([quiz("B1", "Блиц", start="13.12.2026 09:00", end="13.12.2026 09:10"),
                      quiz("T1", "С таймером", timer=60)], questions("B1", 3) + questions("T1", 2))
    assert upload(client, admin, data).json()["failed"] == [{"sheet": "Задания", "row": 2, "reason": "quiz_running"}]

    # A quiz without a window is locked while a guest's attempt is within its timer
    t1 = find(client, admin, "tasks", "code", "T1")["id"]
    assert client.post(f"/api/quiz/{t1}/start", headers=guest).status_code == 200
    at("09:05:30")
    q = next(q for q in rows(client, admin, "questions")["rows"] if q["values"]["task_id"] == t1)
    assert save(client, admin, "questions", q, text="Другой").status_code == 409
    at("09:11:00")
    assert save(client, admin, "questions", q, text="Другой").status_code == 200
    q = next(q for q in rows(client, admin, "questions")["rows"] if q["values"]["task_id"] == b1)
    assert save(client, admin, "questions", q, text="После блица").status_code == 200


def test_one_bad_row_in_a_hundred_refuses_the_whole_file(client, admin):
    tasks = catalog(100)
    tasks[57][4] = "много"
    body = upload(client, admin, xlsx(task_rows=tasks)).json()
    assert body["failed"] == [{"sheet": "Задания", "row": 59, "reason": "bad_points", "min": 0, "max": 10000}]
    assert (body["added"], body["stages_added"]) == (0, 0)
    assert rows(client, admin, "tasks")["rows"] == []
    assert rows(client, admin, "stages")["rows"] == []
    # The preview names it the same way
    assert preview(client, admin, xlsx(task_rows=tasks))["failed"] == body["failed"]


def test_a_task_added_in_the_form_shows_as_hidden_in_the_preview(client, admin):
    load(client, admin, ROWS)
    stage = find(client, admin, "stages", "number", 1)["id"]
    r = client.post("/api/admin/lists/tasks", headers=admin, json={"values": {
        "code": "NEW", "stage_id": stage, "type": "action", "text": "Из формы", "points": 5, "active": True}})
    assert r.status_code == 200, r.text
    data = xlsx(STAGES, ROWS, task_head=HEAD)
    body = preview(client, admin, data)
    assert body["items"] == [{"sheet": "Задания", "code": "NEW", "name": "Из формы", "change": "hidden"}]
    assert body["hidden"] == 1
    # Nothing changes until the admin confirms (sends the file to the import)
    assert find(client, admin, "tasks", "code", "NEW")["values"]["active"] is True
    assert upload(client, admin, data).json()["hidden"] == 1
    assert find(client, admin, "tasks", "code", "NEW")["values"]["active"] is False
    fields = [e["field"] for e in log(client, admin, item="NEW")]
    assert (fields[0], fields[-1]) == ("active", "_created")
    # The form's add logged the new row's values
    assert next(e for e in log(client, admin, item="NEW") if e["field"] == "points")["new_value"] == "5"
    assert log(client, admin, item="NEW")[0]["source"] == "excel"


def test_exporting_and_uploading_the_same_file_previews_no_changes(client, admin):
    rows_ = ROWS + [row("p2", 2, "Партнёрское с монетами", partner="Альфа")]
    load(client, admin, rows_)
    task = find(client, admin, "tasks", "code", "plain")
    assert save(client, admin, "tasks", task, points=33, coins=None).status_code == 200
    data = client.get("/api/admin/tasks/export", headers=admin).content
    body = preview(client, admin, data)
    assert body["items"] == [] and body["failed"] == []
    assert (body["added"], body["changed"], body["hidden"], body["stages_changed"], body["prizes_changed"]) == (
        0, 0, 0, 0, 0)


def test_the_second_of_two_saves_from_the_same_version_is_refused(client, admin):
    load(client, admin, ROWS)
    task = find(client, admin, "tasks", "code", "plain")
    assert save(client, admin, "tasks", task, text="Первая вкладка").status_code == 200
    r = save(client, admin, "tasks", task, text="Вторая вкладка")
    assert (r.status_code, r.json()["detail"]) == (409, {"code": "stale"})
    assert find(client, admin, "tasks", "code", "plain")["values"]["text"] == "Первая вкладка"


def test_a_task_guests_have_done_can_only_be_switched_off(client, admin, guest, clock):
    load(client, admin, ROWS)
    clock("09:30")
    link = find(client, admin, "tasks", "code", "link1")
    assert client.post(f"/api/tasks/{link['id']}/complete", headers=guest).json()["result"] == "awarded"
    r = client.delete(f"/api/admin/lists/tasks/{link['id']}", headers=admin)
    assert (r.status_code, r.json()["detail"]) == (409, {"code": "in_use"})
    assert save(client, admin, "tasks", link, confirm=True, active=False).status_code == 200
    # One nobody used is deleted
    plain = find(client, admin, "tasks", "code", "qr3")
    assert client.delete(f"/api/admin/lists/tasks/{plain['id']}", headers=admin).status_code == 200
    assert "qr3" not in [r["values"]["code"] for r in rows(client, admin, "tasks")["rows"]]
    assert log(client, admin, item="qr3")[0]["field"] == "_deleted"


def test_switching_off_an_open_task_asks_first_and_says_what_changes(client, admin, guest, clock):
    load(client, admin, ROWS)
    clock("09:30")
    task = find(client, admin, "tasks", "code", "plain")
    logged = len(log(client, admin))
    r = save(client, admin, "tasks", task, active=False)
    assert (r.status_code, r.json()["detail"]) == (
        409, {"code": "confirm", "impact": [{"code": "task_off", "item": "plain", "done": 0}]})
    # Cancelled: nothing changed
    assert card(client, guest, "Сфотографировать небо") is not None
    assert find(client, admin, "tasks", "code", "plain")["version"] == task["version"]
    assert len(log(client, admin)) == logged
    assert save(client, admin, "tasks", task, confirm=True, active=False).status_code == 200
    assert card(client, guest, "Сфотографировать небо") is None


def test_a_partner_logo_shows_in_the_partners_list(client, admin):
    load(client, admin, ROWS)
    partner = find(client, admin, "partners", "name", "Coca-Cola")
    assert partner["extra"]["logo"] is False
    files = {"file": ("logo.png", PNG, "image/png")}
    r = client.post(f"/api/admin/partners/{partner['id']}/logo", files=files, headers=admin)
    assert r.status_code == 200, r.text
    assert find(client, admin, "partners", "name", "Coca-Cola")["extra"]["logo"] is True
    r = client.get(f"/api/partners/{partner['id']}/logo")
    assert (r.status_code, r.content, r.headers["content-type"], r.headers["x-content-type-options"]) == (
        200, PNG, "image/png", "nosniff")
    # SVG can carry script: refused, as is anything over 1 MB
    svg = {"file": ("logo.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml")}
    assert client.post(f"/api/admin/partners/{partner['id']}/logo", files=svg, headers=admin).status_code == 400
    big = {"file": ("logo.png", PNG + b"\x00" * (1024 * 1024), "image/png")}
    assert client.post(f"/api/admin/partners/{partner['id']}/logo", files=big, headers=admin).status_code == 413
    # Only the admin uploads
    assert client.post(f"/api/admin/partners/{partner['id']}/logo", files=files).status_code == 401


def test_the_log_filtered_by_one_admin_exports_only_their_changes(client, admin):
    load(client, admin, ROWS)
    r = client.post("/api/admin/lists/staff", headers=admin, json={"values": {
        "name": "Второй админ", "role": "admin", "secret": "second-pass", "active": True}})
    assert r.status_code == 200, r.text
    second_id = r.json()["id"]
    token = client.post("/api/staff/login", json={"role": "admin", "secret": "second-pass"}).json()["token"]
    second = {"Authorization": f"Bearer {token}"}
    task = find(client, admin, "tasks", "code", "plain")
    assert save(client, second, "tasks", task, points=11).status_code == 200
    task = find(client, admin, "tasks", "code", "plain")
    assert save(client, admin, "tasks", task, points=12).status_code == 200
    # The coins follow the rule, so they moved with the points
    mine = log(client, admin, staff_id=second_id)
    assert [(e["staff_name"], e["field"], e["new_value"]) for e in mine] == [("Второй админ", "coins", "11"),
                                                                            ("Второй админ", "points", "11")]
    raw = client.get("/api/admin/log/export", params={"staff_id": second_id}, headers=admin)
    assert raw.status_code == 200
    sheet = load_workbook(io.BytesIO(raw.content))["Журнал"]
    lines = [[c.value for c in r] for r in sheet.iter_rows(min_row=2)]
    assert sorted((r[1], r[4], r[5], r[6]) for r in lines) == [("Второй админ", "Баллы", "10", "11"),
                                                               ("Второй админ", "Монеты", "10", "11")]


def test_a_switched_off_moderator_is_refused_at_the_next_action(client, admin):
    mod = moderator_headers(client)
    assert client.get("/api/moderation/queue", headers=mod).status_code == 200
    account = find(client, admin, "staff", "name", "Модератор 1")
    assert "secret" not in account["values"]
    assert save(client, admin, "staff", account, active=False).status_code == 200
    assert client.get("/api/moderation/queue", headers=mod).status_code == 401
    assert client.post("/api/moderator/login", json={"secret": "1111"}).status_code == 401


def test_staff_access_rules(client, admin):
    admin_row = find(client, admin, "staff", "name", "Администратор")
    r = save(client, admin, "staff", admin_row, active=False)
    assert (r.status_code, r.json()["detail"]) == (400, {"code": "last_admin", "field": "active"})
    # A moderator PIN another moderator has is refused; a new desk PIN replaces the old one
    mod = find(client, admin, "staff", "name", "Модератор 2")
    r = save(client, admin, "staff", mod, secret="1111")
    assert (r.status_code, r.json()["detail"]) == (400, {"code": "secret_taken", "field": "secret"})
    desk = find(client, admin, "staff", "name", "Стойка регистрации")
    assert save(client, admin, "staff", desk, secret="4321").status_code == 200
    assert client.post("/api/staff/login", json={"role": "desk", "secret": "1234"}).status_code == 401
    assert client.post("/api/staff/login", json={"role": "desk", "secret": "4321"}).status_code == 200
    r = client.delete(f"/api/admin/lists/staff/{desk['id']}", headers=admin)
    assert (r.status_code, r.json()["detail"]) == (409, {"code": "shared_account"})
    # The last active admin can't delete their account either
    r = client.delete(f"/api/admin/lists/staff/{admin_row['id']}", headers=admin)
    assert (r.status_code, r.json()["detail"]) == (409, {"code": "last_admin"})
    assert log(client, admin, kind="staff")[0]["new_value"] == "••••"
    # Only the admin opens the settings
    for h in ({}, moderator_headers(client), staff_headers(client, "stand")):
        assert client.get("/api/admin/lists/tasks", headers=h).status_code == 401
        assert client.get("/api/admin/settings", headers=h).status_code == 401
        assert client.get("/api/admin/log", headers=h).status_code == 401


def test_a_setting_applies_from_now_on(client, admin):
    from app.guest_list import import_csv
    with SessionLocal() as db:
        import_csv(db, "ID;Имя\nR-1;Иван\nR-2;Мария\n".encode())
        codes = list(db.scalars(select(Guest.code).order_by(Guest.id)))
    from tests.conftest import open_link
    first = open_link(client, f"http://api.test/b/{codes[0]}")
    client.post("/api/consent", headers=first)
    s = next(s for s in client.get("/api/admin/settings", headers=admin).json() if s["key"] == "arrival_points")
    assert (s["value"], s["effect"]) == (10, "now")
    r = client.put("/api/admin/settings/arrival_points", json={"value": 25, "version": s["version"]}, headers=admin)
    assert r.status_code == 200, r.text
    second = open_link(client, f"http://api.test/b/{codes[1]}")
    assert client.post("/api/consent", headers=second).json()["arrival_points"] == 25
    assert client.get("/api/me", headers=first).json()["arrival_points"] == 10
    (event,) = log(client, admin, kind="settings")
    assert (event["item"], event["old_value"], event["new_value"]) == ("arrival_points", "10", "25")


def test_the_partner_multiplier_mid_stage_asks_first_and_moves_rule_coins(client, admin, guest, clock):
    load(client, admin, ROWS)
    clock("09:30")
    assert card(client, guest, "QR партнёра")["coins"] == 23
    s = next(s for s in client.get("/api/admin/settings", headers=admin).json()
             if s["key"] == "partner_coin_multiplier")
    body = {"value": 2, "version": s["version"]}
    r = client.put("/api/admin/settings/partner_coin_multiplier", json=body, headers=admin)
    assert (r.status_code, r.json()["detail"]) == (
        409, {"code": "confirm", "impact": [{"code": "rule_coins", "count": 1}, {"code": "setting_live"}]})
    assert card(client, guest, "QR партнёра")["coins"] == 23
    r = client.put("/api/admin/settings/partner_coin_multiplier?confirm=true", json=body, headers=admin)
    assert r.status_code == 200
    assert card(client, guest, "QR партнёра")["coins"] == 30
    # Each task whose coins moved has its own log row
    event = next(e for e in log(client, admin, kind="tasks", item="partner") if e["field"] == "coins")
    assert (event["old_value"], event["new_value"]) == ("23", "30")
    # «NaN» parses as a number but is no value
    s = next(s for s in client.get("/api/admin/settings", headers=admin).json()
             if s["key"] == "partner_coin_multiplier")
    r = client.put("/api/admin/settings/partner_coin_multiplier", json={"value": "NaN", "version": s["version"]},
                   headers=admin)
    assert (r.status_code, r.json()["detail"]) == (400, {"code": "bad_value", "field": "partner_coin_multiplier"})


def test_the_guest_list_preview_and_whole_refusal(client, admin):
    files = {"file": ("g.csv", "ID;Имя\nR-1;Иван\n".encode(), "text/csv")}
    assert client.post("/api/admin/guests/import", files=files, headers=admin).json()["added"] == 1
    files = {"file": ("g.csv", "ID;Имя\nR-1;Иван Петрович\nR-2;Мария\n".encode(), "text/csv")}
    body = client.post("/api/admin/guests/import/preview", files=files, headers=admin).json()
    assert body["items"] == [{"reg_id": "R-1", "name": "Иван Петрович", "change": "changed"},
                             {"reg_id": "R-2", "name": "Мария", "change": "added"}]
    with SessionLocal() as db:
        assert db.scalar(select(Guest.first_name).where(Guest.reg_id == "R-1")) == "Иван"
    # A list without R-1 never hides R-1: they may already have points
    files = {"file": ("g.csv", "ID;Имя\nR-2;Мария\n".encode(), "text/csv")}
    assert client.post("/api/admin/guests/import/preview", files=files, headers=admin).json()["items"] == [
        {"reg_id": "R-2", "name": "Мария", "change": "added"}]


def test_the_log_cannot_be_edited_or_deleted(client, admin):
    load(client, admin, ROWS)
    assert log(client, admin)
    with SessionLocal() as db:
        for sql in ("UPDATE change_events SET new_value = 'x'", "DELETE FROM change_events"):
            with pytest.raises(Exception, match="append-only"):
                db.execute(text(sql))
            db.rollback()


def test_excel_rows_are_held_to_the_form_limits(client, admin):
    tasks = catalog(4)
    tasks[0][4] = 10001
    tasks[1][0] = "X" * 33
    tasks[2][6] = "П" * 101
    body = upload(client, admin, xlsx(task_rows=tasks)).json()
    assert body["failed"] == [
        {"sheet": "Задания", "row": 2, "reason": "bad_points", "min": 0, "max": 10000},
        {"sheet": "Задания", "row": 3, "reason": "too_long", "column": "ID", "max": 32},
        {"sheet": "Задания", "row": 4, "reason": "too_long", "column": "Партнёр", "max": 100}]
    assert rows(client, admin, "tasks")["rows"] == []


def test_a_stage_past_points_were_earned_in_stays(client, admin, guest, clock):
    load(client, admin, ROWS)
    clock("09:30")
    link = find(client, admin, "tasks", "code", "link1")
    assert client.post(f"/api/tasks/{link['id']}/complete", headers=guest).json()["result"] == "awarded"
    first = find(client, admin, "stages", "number", 1)
    second = find(client, admin, "stages", "number", 2)
    with SessionLocal() as db:
        db.execute(text("UPDATE tasks SET stage_id = :s WHERE stage_id = :f"), {"s": second["id"], "f": first["id"]})
        db.commit()
    r = client.delete(f"/api/admin/lists/stages/{first['id']}", headers=admin)
    assert (r.status_code, r.json()["detail"]) == (409, {"code": "in_use"})


def test_a_quiz_added_in_the_form_round_trips_and_needs_an_active_qr(client, admin):
    load(client, admin, ROWS)
    stage = find(client, admin, "stages", "number", 1)["id"]
    qr = find(client, admin, "tasks", "code", "qr1")
    assert save(client, admin, "tasks", qr, active=False).status_code == 200
    values = {"code": "Q", "stage_id": stage, "type": "quiz", "text": "Квиз из формы", "points": 5,
              "method": "quiz", "requires_task_id": qr["id"], "active": True}
    r = client.post("/api/admin/lists/tasks", headers=admin, json={"values": values})
    assert (r.status_code, r.json()["detail"]) == (400, {"code": "bad_value", "field": "requires_task_id"})
    del values["requires_task_id"]
    assert client.post("/api/admin/lists/tasks", headers=admin, json={"values": values}).status_code == 200
    # Exported before it has questions, the file uploads back with no changes
    body = preview(client, admin, client.get("/api/admin/tasks/export", headers=admin).content)
    assert (body["items"], body["failed"]) == ([], [])
