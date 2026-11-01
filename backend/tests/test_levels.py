import io

from openpyxl import load_workbook
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Guest, ScoreEvent
from tests.conftest import moderator_headers
from tests.test_market import market_file, make_guest, market, buy
from tests.test_moderation import decide, queue
from tests.test_qr_tasks import load, row
from tests.test_rating import guests, hall, login, rating, score
from tests.test_submissions import ids, send_photo
from tests.test_tasks import STAGES, TASK_HEAD, admin, clock, guest, upload, xlsx  # noqa: F401 (fixtures)

TAG = [["Новичок форума", 0], ["Участник", 50], ["Актив", 150], ["Эксперт форума", 300], ["Легенда MF", 500]]
ROWS = [row("photo25", 1, "Селфи у входа", points=25, method="Фото"),
        row("photo20", 1, "Фото со спикером", points=20, method="Фото")]


def feed(client, h) -> dict:
    r = client.get("/api/feed", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def profile(client, h) -> dict:
    r = client.get("/api/profile", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def top_up(client, h, points: int) -> None:
    """Bring the logged-in guest to exactly `points`."""
    have = feed(client, h)["points"]
    with SessionLocal() as db:
        g = db.scalar(select(Guest))
        db.add(ScoreEvent(guest_id=g.id, reason=f"seed{points}", points=points - have))
        db.commit()


def levels_file(levels, tasks=None) -> bytes:
    wb = load_workbook(io.BytesIO(xlsx(STAGES, tasks, task_head=TASK_HEAD)))
    ws = wb.create_sheet("Уровни")
    ws.append(["Название", "Баллов от"])
    for r in levels:
        ws.append(r)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def export_levels(client, admin) -> list[list]:
    r = client.get("/api/admin/tasks/export", headers=admin)
    assert r.status_code == 200
    ws = load_workbook(io.BytesIO(r.content))["Уровни"]
    return [list(v) for v in ws.iter_rows(values_only=True)]


def test_bar_shows_the_level_and_points_to_the_next(client, admin, guest, clock):
    clock("09:30")
    top_up(client, guest, 140)
    f = feed(client, guest)
    assert (f["level"], f["to_next"]) == ("Участник", 10)
    top_up(client, guest, 520)
    f = feed(client, guest)
    # Nothing after the top level
    assert (f["level"], f["to_next"]) == ("Легенда MF", None)


def test_crossing_a_threshold_shows_the_moment_once(client, admin, guest, clock):
    load(client, admin, ROWS)
    t = ids(client, admin)
    clock("09:30")
    top_up(client, guest, 140)
    feed(client, guest)  # the moment for «Участник», reached on the way to 140
    assert feed(client, guest)["new_level"] is None
    assert send_photo(client, guest, t["photo25"]).json()["result"] == "awarded"
    f = feed(client, guest)
    assert (f["points"], f["level"], f["new_level"]) == (165, "Актив", "Актив")
    # Not again after a reload
    assert feed(client, guest)["new_level"] is None


def test_a_rejection_drops_the_level_quietly_and_climbing_again_shows_it_again(client, admin, guest, clock):
    load(client, admin, ROWS)
    t = ids(client, admin)
    clock("09:30")
    top_up(client, guest, 140)
    feed(client, guest)
    send_photo(client, guest, t["photo25"])
    assert feed(client, guest)["new_level"] == "Актив"
    mod = moderator_headers(client)
    assert decide(client, mod, queue(client, mod)["items"][0]["id"], "penalty").status_code == 200
    f = feed(client, guest)
    assert (f["points"], f["level"], f["to_next"], f["new_level"]) == (140, "Участник", 10, None)
    send_photo(client, guest, t["photo20"])
    f = feed(client, guest)
    assert (f["points"], f["new_level"]) == (160, "Актив")
    assert feed(client, guest)["new_level"] is None


def test_climbing_back_after_a_rejection_shows_the_moment_without_a_feed_load_between(client, admin, guest, clock):
    load(client, admin, ROWS)
    t = ids(client, admin)
    clock("09:30")
    top_up(client, guest, 140)
    feed(client, guest)
    send_photo(client, guest, t["photo25"])
    assert feed(client, guest)["new_level"] == "Актив"
    mod = moderator_headers(client)
    decide(client, mod, queue(client, mod)["items"][0]["id"], "penalty")
    # Back to 140 and straight past 150 again, the feed not opened in between
    send_photo(client, guest, t["photo20"])
    f = feed(client, guest)
    assert (f["points"], f["new_level"]) == (160, "Актив")


def test_a_new_level_below_doesnt_show_the_old_level_again(client, admin, guest, clock):
    clock("09:30")
    top_up(client, guest, 60)
    assert feed(client, guest)["new_level"] == "Участник"
    added = [["Новичок форума", 0], ["Гость", 25]] + TAG[1:]
    assert upload(client, admin, levels_file(added)).json()["levels_changed"] is True
    f = feed(client, guest)
    assert (f["level"], f["new_level"]) == ("Участник", None)


def test_profile_shows_level_totals_and_every_done_task(client, admin, clock):
    tasks = [["buy", 3, "Действие", "Обменять монеты в маркете", 15, None, None, None, None, None, "Маркет", None],
             ["photoA", 3, "Действие", "Селфи у входа", 20, None, None, None, None, None, "Фото", None],
             ["photoB", 3, "Действие", "Фото со спикером", 30, None, None, None, None, None, "Фото", None]]
    r = upload(client, admin, market_file(tasks=tasks))
    assert r.status_code == 200, r.text
    t = ids(client, admin)
    clock("14:30")
    g = make_guest(client, "R-1", "Иван", coins=100)
    client.post("/api/consent", headers=g)  # +10 for coming
    send_photo(client, g, t["photoA"])
    send_photo(client, g, t["photoB"])
    mod = moderator_headers(client)
    items = {i["task"]: i["id"] for i in queue(client, mod)["items"]}
    decide(client, mod, items["Селфи у входа"], "bonus")
    decide(client, mod, items["Фото со спикером"], "penalty")
    assert buy(client, g, market(client, g), "Блокнот").status_code == 200

    p = profile(client, g)
    # 10 + 20 + 10 bonus + 30 − 30 + 15 for the market task
    assert (p["points"], p["level"], p["to_next"]) == (55, "Участник", 95)
    assert p["coins"] == 100 + 20 + 30 - 30 - 10 + 15
    got = [(e["kind"], e["text"], e["points"], e["coins"], e["bonus"], e["rejected"]) for e in p["history"]]
    assert got == [
        ("task", "Обменять монеты в маркете", 15, 15, 0, False),
        ("buy", "Блокнот", 0, -10, 0, False),
        ("task", "Фото со спикером", 30, 30, 0, True),
        ("task", "Селфи у входа", 20, 20, 10, False),
        ("arrival", "", 10, 0, 0, False),
    ]


def test_profile_coins_go_below_zero_when_a_rejection_takes_spent_coins(client, admin, clock):
    tasks = [["photoB", 3, "Действие", "Фото со спикером", 30, None, None, None, None, None, "Фото", None]]
    upload(client, admin, market_file(tasks=tasks))
    t = ids(client, admin)
    clock("14:30")
    g = make_guest(client, "R-1", "Иван")
    send_photo(client, g, t["photoB"])
    assert buy(client, g, market(client, g), "Блокнот").status_code == 200
    mod = moderator_headers(client)
    decide(client, mod, queue(client, mod)["items"][0]["id"], "penalty")
    assert profile(client, g)["coins"] == -10


def test_profile_needs_a_guest(client, admin):
    assert client.get("/api/profile").status_code == 401
    assert client.get("/api/profile", headers=admin).status_code == 401


def test_rating_and_hall_show_the_level_beside_each_name(client, admin):
    g = guests("ID;Фамилия;Имя\nR-1;Алиева;Анна\nR-2;Бобоев;Борис\n")
    score(g["Анна"], 520, 1)
    score(g["Борис"], 140, 2)
    want = [("Анна А.", "Легенда MF"), ("Борис Б.", "Участник")]
    assert [(r["name"], r["level"]) for r in rating(client, login(client, g["Анна"]))["top"]] == want
    assert [(r["name"], r["level"]) for r in hall(client)["top"]] == want


def test_new_thresholds_from_the_file_apply_without_a_deploy(client, admin, guest, clock):
    clock("09:30")
    top_up(client, guest, 140)
    assert feed(client, guest)["level"] == "Участник"
    new = [["Новичок форума", 0], ["Участник", 40], ["Актив", 120], ["Эксперт форума", 250], ["Легенда MF", 400]]
    r = upload(client, admin, levels_file(new))
    assert r.status_code == 200, r.text
    assert (r.json()["levels_changed"], r.json()["failed"]) == (True, [])
    f = feed(client, guest)
    assert (f["level"], f["to_next"]) == ("Актив", 110)
    # Downloading gives it back
    assert export_levels(client, admin) == [["Название", "Баллов от"]] + new


def test_a_bad_levels_sheet_fails_with_the_reason_and_the_old_levels_stay(client, admin, guest, clock):
    clock("09:30")
    top_up(client, guest, 140)
    no_zero = [["Участник", 50], ["Актив", 150]]
    out_of_order = [["Новичок форума", 0], ["Актив", 150], ["Участник", 50]]
    for levels, failed in ((no_zero, [{"sheet": "Уровни", "row": 2, "reason": "no_zero_level"}]),
                           (out_of_order, [{"sheet": "Уровни", "row": 4, "reason": "levels_out_of_order"}]),
                           ([], [{"sheet": "Уровни", "row": 2, "reason": "no_zero_level"}])):
        r = upload(client, admin, levels_file(levels))
        assert r.status_code == 200, r.text
        assert (r.json()["levels_changed"], r.json()["failed"]) == (False, failed)
        # The tasks on the other sheets still load
        tasks = load_workbook(io.BytesIO(client.get("/api/admin/tasks/export", headers=admin).content))["Задания"]
        assert tasks.max_row == 1 + 42
        assert export_levels(client, admin)[1:] == TAG
        f = feed(client, guest)
        assert (f["level"], f["to_next"]) == ("Участник", 10)


def test_the_empty_template_comes_with_tags_five_levels(client, admin):
    assert export_levels(client, admin) == [["Название", "Баллов от"]] + TAG


def test_a_file_without_levels_leaves_them(client, admin):
    upload(client, admin, levels_file([["Старт", 0], ["Финиш", 100]]))
    r = upload(client, admin, xlsx())
    assert r.status_code == 200
    assert r.json()["levels_changed"] is False
    assert export_levels(client, admin)[1:] == [["Старт", 0], ["Финиш", 100]]
