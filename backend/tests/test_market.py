import io
import threading

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from app import ledger
from app.db import SessionLocal
from app.guest_list import import_csv
from app.models import Guest
from tests.conftest import open_link, staff_headers
from tests.test_tasks import STAGE_HEAD, STAGES, TASK_HEAD, admin, clock, upload, xlsx  # noqa: F401 (fixtures)

TASKS_HEAD = TASK_HEAD + ["Выполнение", "Ссылка"]
PRIZE_HEAD = ["ID", "Название", "Партнёр", "Цена в монетах", "Количество"]
# Stage 3 opens the market, at 14:00
MARKET_STAGES = [r + (["да"] if r[0] == 3 else [None]) for r in STAGES]
PRIZES = [
    ["P1", "Термокружка", "Coca-Cola", 30, 5],
    ["P2", "Футболка", "Alif", 50, 1],
    ["P3", "Блокнот", "TAG", 10, 100],
]
TASKS = [["buy", 3, "Действие", "Обменять монеты в маркете", 15, None, None, None, None, None, "Маркет", None]]


def market_file(prizes=PRIZES, tasks=TASKS, stages=MARKET_STAGES) -> bytes:
    wb = load_workbook(io.BytesIO(xlsx(stages, tasks, stage_head=STAGE_HEAD + ["Маркет"], task_head=TASKS_HEAD)))
    if prizes is not None:
        ws = wb.create_sheet("Призы")
        ws.append(PRIZE_HEAD)
        for r in prizes:
            ws.append(r)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def load(client, admin, **kw) -> dict:
    r = upload(client, admin, market_file(**kw))
    assert r.status_code == 200, r.text
    return r.json()


def make_guest(client, reg: str, name: str, coins: int = 0) -> dict:
    with SessionLocal() as db:
        import_csv(db, f"ID;Имя\n{reg};{name}\n".encode())
        g = db.scalar(select(Guest).where(Guest.reg_id == reg))
        if coins:
            ledger.write(db, g.id, "test_coins", "bonus", 0, coins)
            db.commit()
    return open_link(client, f"http://api.test/b/{g.code}")


@pytest.fixture
def stand(client):
    return staff_headers(client, "stand")


def market(client, guest) -> dict:
    r = client.get("/api/market", headers=guest)
    assert r.status_code == 200, r.text
    return r.json()


def prize(m: dict, name: str) -> dict:
    return next(p for p in m["prizes"] if p["name"] == name)


def buy(client, guest, m: dict, name: str):
    return client.post(f"/api/market/{prize(m, name)['id']}/buy", headers=guest)


def test_upload_shows_prizes_with_price_and_left(client, admin, clock):
    body = load(client, admin)
    assert (body["prizes_added"], body["failed"]) == (3, [])
    guest = make_guest(client, "R-1", "Иван")
    clock("09:30")
    m = market(client, guest)
    assert [(p["name"], p["partner"], p["price"], p["left"]) for p in m["prizes"]] == [
        ("Термокружка", "Coca-Cola", 30, 5), ("Футболка", "Alif", 50, 1), ("Блокнот", "TAG", 10, 100)]
    assert all(p["code"] is None for p in m["prizes"])


def test_market_is_locked_before_its_stage(client, admin, clock):
    load(client, admin)
    guest = make_guest(client, "R-1", "Иван", coins=100)
    clock("11:00")
    m = market(client, guest)
    assert m["open"] is False
    assert m["opens_at"].startswith("2026-12-13T14:00:00+05:00")
    r = buy(client, guest, m, "Термокружка")
    assert (r.status_code, r.json()["detail"]) == (409, "market_closed")
    assert market(client, guest)["coins"] == 100


def test_no_market_stage_means_never_open(client, admin, clock):
    load(client, admin, stages=[r + [None] for r in STAGES])
    guest = make_guest(client, "R-1", "Иван", coins=100)
    clock("15:00")
    m = market(client, guest)
    assert (m["open"], m["opens_at"]) == (False, None)


def test_buy_takes_coins_and_gives_a_code_once(client, admin, clock):
    load(client, admin)
    guest = make_guest(client, "R-1", "Иван", coins=100)
    clock("14:30")
    m = market(client, guest)
    assert m["open"] is True
    r = buy(client, guest, m, "Термокружка")
    assert r.status_code == 200, r.text
    m = r.json()
    mug = prize(m, "Термокружка")
    # 100 − 30, plus the market task's 15 for the first purchase
    assert m["coins"] == 85
    assert mug["left"] == 4 and len(mug["code"]) == 6 and mug["issued_at"] is None
    assert client.get("/api/feed", headers=guest).json()["coins"] == 85

    again = buy(client, guest, m, "Термокружка")
    assert (again.status_code, again.json()["detail"]) == (409, "already_bought")
    m = market(client, guest)
    assert m["coins"] == 85 and prize(m, "Термокружка")["code"] == mug["code"]


def test_too_few_coins(client, admin, clock):
    load(client, admin)
    guest = make_guest(client, "R-1", "Иван", coins=20)
    clock("14:30")
    r = buy(client, guest, market(client, guest), "Термокружка")
    assert (r.status_code, r.json()["detail"]) == (409, "not_enough_coins")
    m = market(client, guest)
    assert (m["coins"], prize(m, "Термокружка")["left"], prize(m, "Термокружка")["code"]) == (20, 5, None)


def test_sold_out(client, admin, clock):
    load(client, admin)
    first = make_guest(client, "R-1", "Иван", coins=100)
    second = make_guest(client, "R-2", "Мария", coins=100)
    clock("14:30")
    assert buy(client, first, market(client, first), "Футболка").status_code == 200
    m = market(client, second)
    assert prize(m, "Футболка")["left"] == 0
    r = buy(client, second, m, "Футболка")
    assert (r.status_code, r.json()["detail"]) == (409, "sold_out")
    assert market(client, second)["coins"] == 100


def test_two_guests_after_the_last_item_at_once(client, admin, clock):
    load(client, admin)
    guests = [make_guest(client, f"R-{i}", f"Гость {i}", coins=100) for i in range(2)]
    clock("14:30")
    shirt = prize(market(client, guests[0]), "Футболка")["id"]
    start = threading.Barrier(2)
    results = [None, None]

    def go(i):
        start.wait()
        results[i] = client.post(f"/api/market/{shirt}/buy", headers=guests[i])

    threads = [threading.Thread(target=go, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    codes = sorted(r.status_code for r in results)
    assert codes == [200, 409]
    loser = guests[[r.status_code for r in results].index(409)]
    assert results[[r.status_code for r in results].index(409)].json()["detail"] == "sold_out"
    assert market(client, loser)["coins"] == 100


def test_one_guest_cant_spend_the_same_coins_twice(client, admin, clock):
    load(client, admin)
    guest = make_guest(client, "R-1", "Иван", coins=60)
    clock("14:30")
    m = market(client, guest)
    ids = [prize(m, "Термокружка")["id"], prize(m, "Футболка")["id"]]
    start = threading.Barrier(2)
    results = [None, None]

    def go(i):
        start.wait()
        results[i] = client.post(f"/api/market/{ids[i]}/buy", headers=guest)

    threads = [threading.Thread(target=go, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(r.status_code for r in results) == [200, 409]
    assert market(client, guest)["coins"] >= 0


def test_stand_hands_the_prize_over_once(client, admin, stand, clock):
    load(client, admin)
    guest = make_guest(client, "R-1", "Иван", coins=100)
    clock("14:30")
    code = prize(buy(client, guest, market(client, guest), "Термокружка").json(), "Термокружка")["code"]

    r = client.get(f"/api/stand/{code.upper()}", headers=stand)
    assert r.status_code == 200, r.text
    assert r.json() == {"prize": "Термокружка", "partner": "Coca-Cola", "first_name": "Иван", "issued_at": None}

    clock("14:45")
    r = client.post(f"/api/stand/{code}/issue", headers=stand).json()
    assert r["result"] == "issued" and r["handover"]["issued_at"].startswith("2026-12-13T14:45:00+05:00")
    assert prize(market(client, guest), "Термокружка")["issued_at"].startswith("2026-12-13T14:45")

    clock("15:00")
    again = client.post(f"/api/stand/{code}/issue", headers=stand).json()
    assert again["result"] == "already" and again["handover"]["issued_at"].startswith("2026-12-13T14:45")
    assert client.get(f"/api/stand/{code}", headers=stand).json()["issued_at"].startswith("2026-12-13T14:45")


def test_stand_needs_the_pin_and_a_real_code(client, admin, stand, clock):
    load(client, admin)
    guest = make_guest(client, "R-1", "Иван", coins=100)
    clock("14:30")
    code = prize(buy(client, guest, market(client, guest), "Термокружка").json(), "Термокружка")["code"]
    desk = staff_headers(client, "desk")
    for h in ({}, guest, desk, admin):
        assert client.get(f"/api/stand/{code}", headers=h).status_code == 401
        assert client.post(f"/api/stand/{code}/issue", headers=h).status_code == 401
    assert client.post("/api/staff/login", json={"role": "stand", "secret": "0000"}).status_code == 401
    wrong = client.get("/api/stand/zzzzzz", headers=stand)
    assert (wrong.status_code, wrong.json()["detail"]) == (404, "code_not_found")
    assert client.post("/api/stand/zzzzzz/issue", headers=stand).status_code == 404


def test_market_needs_a_guest(client, admin):
    load(client, admin)
    assert client.get("/api/market").status_code == 401
    assert client.get("/api/market", headers=admin).status_code == 401
    assert client.post("/api/market/1/buy").status_code == 401


def test_first_purchase_completes_the_market_task_once(client, admin, clock):
    load(client, admin)
    guest = make_guest(client, "R-1", "Иван", coins=100)
    clock("14:30")
    before = client.get("/api/feed", headers=guest).json()
    card = next(t for t in before["tasks"] if t["text"] == "Обменять монеты в маркете")
    assert (card["method"], card["done"]) == ("market", False)

    buy(client, guest, market(client, guest), "Блокнот")
    after = client.get("/api/feed", headers=guest).json()
    assert (after["points"], after["coins"]) == (before["points"] + 15, before["coins"] - 10 + 15)
    assert next(t for t in after["tasks"] if t["id"] == card["id"])["done"] is True

    buy(client, guest, market(client, guest), "Термокружка")
    last = client.get("/api/feed", headers=guest).json()
    assert (last["points"], last["coins"]) == (after["points"], after["coins"] - 30)


def test_reupload_keeps_purchases_and_updates_left(client, admin, stand, clock):
    load(client, admin)
    guest = make_guest(client, "R-1", "Иван", coins=200)
    clock("14:30")
    m = buy(client, guest, market(client, guest), "Термокружка").json()
    code = prize(m, "Термокружка")["code"]
    buy(client, guest, m, "Футболка")

    # Fewer mugs, and the T-shirt row removed from the file
    body = load(client, admin, prizes=[["P1", "Термокружка", "Coca-Cola", 30, 2], ["P3", "Блокнот", "TAG", 10, 100]])
    assert (body["prizes_added"], body["prizes_changed"], body["prizes_hidden"]) == (0, 1, 1)
    m = market(client, guest)
    assert prize(m, "Термокружка")["left"] == 1 and prize(m, "Термокружка")["code"] == code
    # The guest who bought the removed prize still sees it and can collect it
    assert prize(m, "Футболка")["code"] is not None
    assert client.get(f"/api/stand/{code}", headers=stand).status_code == 200
    other = make_guest(client, "R-2", "Мария", coins=100)
    assert "Футболка" not in [p["name"] for p in market(client, other)["prizes"]]

    # A quantity below what is sold is refused, and the sales stand
    body = load(client, admin, prizes=[["P1", "Термокружка", "Coca-Cola", 30, 0]])
    assert body["failed"] == [{"sheet": "Призы", "row": 2, "reason": "below_sold"}]
    assert prize(market(client, guest), "Термокружка")["left"] == 1
    assert prize(market(client, guest), "Термокружка")["code"] == code


def test_file_without_prizes_sheet_leaves_prizes(client, admin):
    load(client, admin)
    body = load(client, admin, prizes=None)
    assert (body["prizes_added"], body["prizes_hidden"], body["failed"]) == (0, 0, [])
    guest = make_guest(client, "R-1", "Иван")
    assert len(market(client, guest)["prizes"]) == 3


def test_prize_rows_that_fail(client, admin):
    rows = [["", "Без ID", "A", 10, 1], ["P1", "", "A", 10, 1], ["P2", "Приз", "", 10, 1],
            ["P3", "Приз", "A", "дорого", 1], ["P4", "Приз", "A", 10, -1], ["P5", "Приз", "A", 10, 1],
            ["P5", "Приз", "A", 10, 1]]
    body = load(client, admin, prizes=rows)
    assert body["prizes_added"] == 0
    assert [(f["sheet"], f["row"], f["reason"]) for f in body["failed"]] == [
        ("Призы", 2, "no_id"), ("Призы", 3, "no_name"), ("Призы", 4, "no_partner"), ("Призы", 5, "bad_price"),
        ("Призы", 6, "bad_quantity"), ("Призы", 8, "duplicate_id")]


def test_bad_market_cell_and_missing_prize_column(client, admin):
    stages = [r + (["может быть"] if r[0] == 3 else [None]) for r in STAGES]
    body = load(client, admin, stages=stages)
    assert ("Этапы", 4, "bad_market") in [(f["sheet"], f["row"], f["reason"]) for f in body["failed"]]

    wb = load_workbook(io.BytesIO(market_file()))
    wb["Призы"].delete_cols(4)
    out = io.BytesIO()
    wb.save(out)
    r = upload(client, admin, out.getvalue())
    assert r.status_code == 400 and "Призы: Цена в монетах" in r.json()["detail"]["items"]


def test_download_gives_prizes_and_market_stage_back(client, admin):
    load(client, admin)
    data = client.get("/api/admin/tasks/export", headers=admin).content
    wb = load_workbook(io.BytesIO(data))
    assert [c.value for c in wb["Этапы"][1]] == STAGE_HEAD + ["Маркет"]
    assert [wb["Этапы"].cell(row=n, column=6).value for n in range(2, 6)] == [None, None, "да", None]
    assert [[c.value for c in r] for r in wb["Призы"].iter_rows(min_row=1)] == [PRIZE_HEAD] + PRIZES
    assert wb["Задания"]["K2"].value == "Маркет"
    body = upload(client, admin, data).json()
    assert (body["changed"], body["stages_changed"], body["prizes_changed"], body["failed"]) == (0, 0, 0, [])
