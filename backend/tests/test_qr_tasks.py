import io

import pytest
from openpyxl import load_workbook

from tests.test_tasks import STAGES, TASK_HEAD, admin, clock, guest, upload, xlsx  # noqa: F401 (fixtures)

HEAD = TASK_HEAD + ["Выполнение", "Ссылка"]


def row(code, stage, text, points=15, method=None, link=None, partner=None, package=None, start=None, end=None):
    return [code, stage, "Действие", text, points, None, partner, package, start, end, method, link]


def load(client, admin, rows):
    r = upload(client, admin, xlsx(STAGES, rows, task_head=HEAD))
    assert r.status_code == 200, r.text
    return r.json()


def qr_codes(client, admin) -> dict[str, str]:
    r = client.get("/api/admin/tasks/qr", headers=admin)
    assert r.status_code == 200
    return {t["code"]: t["qr_code"] for t in r.json()}


def scan(client, guest, code):
    return client.post("/api/scan", json={"code": code}, headers=guest)


def totals(client, guest):
    f = client.get("/api/feed", headers=guest).json()
    return f["points"], f["coins"]


ROWS = [
    row("qr1", 1, "Найти QR у стенда", method="QR"),
    row("qr3", 3, "QR этапа 3", method="QR"),
    row("link1", 1, "Зарегистрироваться на сайте", points=10, method="Ссылка", link="https://tag.tj/register"),
    row("plain", 1, "Сфотографировать небо", points=10),
    row("partner", 1, "QR партнёра", method="QR", partner="Coca-Cola", package="MF Партнёр"),
    row("quiz", 1, "Квиз с окном", method="QR", start="13.12.2026 09:00", end="13.12.2026 09:10"),
]


def test_scan_awards_once(client, admin, guest, clock):
    load(client, admin, ROWS)
    codes = qr_codes(client, admin)
    clock("09:30")
    base = totals(client, guest)  # the +10 for arriving
    r = scan(client, guest, codes["qr1"]).json()
    assert (r["result"], r["task"]["points"], r["task"]["coins"], r["task"]["done"]) == ("awarded", 15, 15, True)
    assert totals(client, guest) == (base[0] + 15, base[1] + 15)
    card = client.get(f"/api/tasks/{r['task']['id']}", headers=guest).json()
    assert (card["done"], card["state"]) == (True, "done")
    assert scan(client, guest, codes["qr1"]).json()["result"] == "already"
    assert totals(client, guest) == (base[0] + 15, base[1] + 15)


def test_partner_qr_gives_coins_by_the_rule(client, admin, guest, clock):
    load(client, admin, ROWS)
    clock("09:30")
    r = scan(client, guest, qr_codes(client, admin)["partner"]).json()
    assert (r["task"]["points"], r["task"]["coins"]) == (15, 23)


def test_scan_outside_its_stage_or_window_is_unavailable(client, admin, guest, clock):
    load(client, admin, ROWS)
    codes = qr_codes(client, admin)
    clock("11:00")  # stage 2
    assert scan(client, guest, codes["qr3"]).json()["result"] == "unavailable"
    assert scan(client, guest, codes["qr1"]).json()["result"] == "unavailable"
    clock("09:30")  # stage 1, but the quiz window closed at 09:10
    assert scan(client, guest, codes["quiz"]).json()["result"] == "unavailable"
    clock("09:05")
    assert scan(client, guest, codes["quiz"]).json()["result"] == "awarded"


def test_wrong_qr_is_not_found(client, admin, guest, clock):
    load(client, admin, ROWS)
    clock("09:30")
    code = qr_codes(client, admin)["qr1"]
    wrong = ("a" if code[0] != "a" else "b") + code[1:]
    r = scan(client, guest, wrong)
    assert (r.status_code, r.json()["detail"]) == (404, "qr_not_found")


def test_scan_needs_a_logged_in_guest(client, admin):
    load(client, admin, ROWS)
    assert scan(client, {}, qr_codes(client, admin)["qr1"]).status_code == 401


def test_link_task_is_confirmed_once(client, admin, guest, clock):
    load(client, admin, ROWS)
    clock("09:30")
    tasks = {t["text"]: t for t in client.get("/api/feed", headers=guest).json()["tasks"]}
    link = tasks["Зарегистрироваться на сайте"]
    assert (link["method"], link["link"]) == ("link", "https://tag.tj/register")
    r = client.post(f"/api/tasks/{link['id']}/complete", headers=guest).json()
    assert (r["result"], r["task"]["points"]) == ("awarded", 10)
    assert client.post(f"/api/tasks/{link['id']}/complete", headers=guest).json()["result"] == "already"
    # QR tasks and not-yet-doable tasks can't be confirmed by a button
    for name in ("Найти QR у стенда", "Сфотографировать небо"):
        assert client.post(f"/api/tasks/{tasks[name]['id']}/complete", headers=guest).status_code == 400


def test_qr_codes_survive_reupload(client, admin):
    load(client, admin, ROWS)
    before = qr_codes(client, admin)
    assert set(before) == {"qr1", "qr3", "partner", "quiz"}
    assert len(set(before.values())) == 4
    changed = [r[:] for r in ROWS]
    changed[0][3] = "Найти QR у стенда партнёра"
    body = load(client, admin, changed)
    assert body["changed"] == 1
    assert qr_codes(client, admin) == before


def test_method_and_link_round_trip_through_the_file(client, admin):
    load(client, admin, ROWS)
    wb = load_workbook(io.BytesIO(client.get("/api/admin/tasks/export", headers=admin).content))
    rows = {r[0].value: [c.value for c in r] for r in wb["Задания"].iter_rows(min_row=2)}
    assert rows["qr1"][10:12] == ["QR", None]
    assert rows["link1"][10:12] == ["Ссылка", "https://tag.tj/register"]
    assert rows["plain"][10:12] == [None, None]


@pytest.mark.parametrize("method,link,reason", [
    ("Танец", None, "unknown_method"),
    ("Ссылка", None, "no_link"),
    ("Ссылка", "tag.tj", "bad_link"),
])
def test_bad_method_rows_fail(client, admin, method, link, reason):
    body = load(client, admin, [row("x", 1, "Задание", method=method, link=link)])
    assert body["failed"] == [{"sheet": "Задания", "row": 2, "reason": reason}]


def test_qr_list_needs_the_password(client):
    assert client.get("/api/admin/tasks/qr").status_code == 401
