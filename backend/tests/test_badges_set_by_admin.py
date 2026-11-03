"""Piece 20: badges set by the admin, in the «Бейджи» sheet or tab, from six rule types; coins through the ledger, the
hall announcement for badges marked «на экран», and every change worked out at once."""
import io

from openpyxl import load_workbook
from sqlalchemy import select, update

from app.db import SessionLocal
from app.guest_list import import_csv
from app.models import BadgeAward, Guest, ScoreEvent, Stage, Submission
from tests.conftest import moderator_headers, open_link
from tests.test_badges import codes, held, link, new, photos, row, send
from tests.test_levels import feed, profile
from tests.test_moderation import decide
from tests.test_quiz import load, play, questions, quiz, start
from tests.test_rating import freeze, hall, rating
from tests.test_submissions import ids
from tests.test_tasks import admin, clock, guest, upload  # noqa: F401 (fixtures)

LISTS = "/api/admin/lists/badges"


def person(reg: str, first: str, last: str = "") -> dict:
    with SessionLocal() as db:
        import_csv(db, f"ID;Имя;Фамилия\n{reg};{first};{last}\n".encode())
        g = db.scalar(select(Guest).where(Guest.reg_id == reg))
    from fastapi.testclient import TestClient
    from app.main import app
    return open_link(TestClient(app), f"http://api.test/b/{g.code}")


def guest_id(reg: str) -> int:
    with SessionLocal() as db:
        return db.scalar(select(Guest.id).where(Guest.reg_id == reg))


def badge_rows(client, admin) -> dict[str, dict]:
    r = client.get(LISTS, headers=admin)
    assert r.status_code == 200, r.text
    return {x["values"]["code"]: x for x in r.json()["rows"]}


def change(client, admin, code: str, confirm=True, **values):
    b = badge_rows(client, admin)[code]
    return client.put(f"{LISTS}/{b['id']}{'?confirm=true' if confirm else ''}",
                      json={"values": values, "version": b["version"]}, headers=admin)


def add(client, admin, confirm=True, **values):
    return client.post(f"{LISTS}{'?confirm=true' if confirm else ''}", json={"values": values}, headers=admin)


def coins_of(reg: str) -> tuple[int, int]:
    with SessionLocal() as db:
        g = db.scalar(select(Guest).where(Guest.reg_id == reg))
        return g.points, g.coins


def held_now(reg: str) -> set[str]:
    """What badge_awards records, with no feed load in between."""
    with SessionLocal() as db:
        return set(db.scalars(select(BadgeAward.badge).where(BadgeAward.guest_id == guest_id(reg))))


def test_lowering_photo_hunter_to_3_gives_it_at_once_to_every_guest_with_3(client, admin, guest, clock):
    load(client, admin, photos(5), [])
    t = ids(client, admin)
    other = person("R-2", "Мария")
    clock("09:30")
    for code in ("photo1", "photo2", "photo3"):
        send(client, guest, t[code])
    for code in ("photo1", "photo2"):
        send(client, other, t[code])
    assert held(profile(client, guest)) == []
    # The form says what the save changes before it is kept
    r = change(client, admin, "photo_hunter", confirm=False, count=3)
    assert r.status_code == 409
    assert r.json()["detail"]["impact"] == [{"code": "badge_recheck", "item": "photo_hunter", "gained": 1, "lost": 0}]
    assert change(client, admin, "photo_hunter", count=3).status_code == 200
    # At once: recorded before anyone opens the feed
    assert held_now("R-1") == {"photo_hunter"}
    assert held_now("R-2") == set()
    assert new(feed(client, guest)) == ["photo_hunter"]
    # The greyed condition is written from the rule
    shelf = {b["code"]: b for b in profile(client, other)["badges"]}
    assert (shelf["photo_hunter"]["count"], shelf["photo_hunter"]["kinds"]) == (3, "Фото, Фото+текст")


def test_freezing_gives_the_top_n_the_place_badge_and_unfreezing_takes_it_back(client, admin, clock):
    assert add(client, admin, code="top2", name="Призёр", rule="place", count=2, on_screen=True).status_code == 200
    load(client, admin, [row("l1", "Ссылка 1", method="Ссылка", points=30), row("l2", "Ссылка 2", method="Ссылка",
                                                                                 points=20)], [])
    t = ids(client, admin)
    a, b, c = person("R-1", "Анна"), person("R-2", "Борис"), person("R-3", "Вера")
    clock("09:30")
    link(client, a, t["l1"])
    link(client, a, t["l2"])
    link(client, b, t["l1"])
    link(client, c, t["l2"])
    assert held_now("R-1") == set()
    assert freeze(client, admin).status_code == 200
    assert (held_now("R-1"), held_now("R-2"), held_now("R-3")) == ({"top2"}, {"top2"}, set())
    assert codes(rating(client, a)["top"][0]["badges"]) == ["top2"]
    # Not announced: it comes from the freeze, not the guest's action
    assert hall(client)["badge"] is None
    assert freeze(client, admin, frozen=False).status_code == 200
    assert held_now("R-1") == set()


def test_a_20_coin_badge_switched_off_takes_the_20_coins_back(client, admin, guest, clock):
    assert change(client, admin, "photo_hunter", coins=20).status_code == 200
    load(client, admin, photos(5), [])
    t = ids(client, admin)
    clock("09:30")
    for i in range(1, 6):
        send(client, guest, t[f"photo{i}"])
    assert coins_of("R-1") == (50, 70)
    assert change(client, admin, "photo_hunter", active=False).status_code == 200
    assert coins_of("R-1") == (50, 50)
    with SessionLocal() as db:
        award, back = db.scalars(select(ScoreEvent).where(ScoreEvent.reason == "badge:photo_hunter")
                                 .order_by(ScoreEvent.id)).all()
        assert (back.action, back.reverses_id, back.coins) == ("badge", award.id, -20)
    assert held(profile(client, guest)) == []
    # Held by a guest once: it can only be switched off, not deleted
    b = badge_rows(client, admin)["photo_hunter"]
    assert client.delete(f"{LISTS}/{b['id']}", headers=admin).json()["detail"]["code"] == "in_use"
    # Switched on again, it is earned again and pays again
    assert change(client, admin, "photo_hunter", active=True).status_code == 200
    assert coins_of("R-1") == (50, 70)


def test_a_20_coin_badge_pays_at_once_with_no_multiplier_and_points_and_place_stay(client, admin, guest, clock):
    assert change(client, admin, "photo_hunter", coins=20).status_code == 200
    load(client, admin, photos(5), [])
    with SessionLocal() as db:
        db.execute(update(Stage).values(multiplier=2))
        db.commit()
    t = ids(client, admin)
    leader = person("R-2", "Борис")
    clock("09:30")
    send(client, leader, t["photo1"])
    send(client, leader, t["photo2"])
    send(client, leader, t["photo3"])
    for i in range(1, 5):
        send(client, guest, t[f"photo{i}"])
    before = rating(client, guest)
    points, coins = coins_of("R-1")
    send(client, guest, t["photo5"])
    # The fifth task's 10 × 2 points and 10 coins, and the badge's 20 coins only
    assert coins_of("R-1") == (points + 20, coins + 10 + 20)
    with SessionLocal() as db:
        e = db.scalar(select(ScoreEvent).where(ScoreEvent.reason == "badge:photo_hunter"))
        assert (e.action, e.base_points, e.points, e.multiplier, e.coins) == ("badge", 0, 0, 1, 20)
    after = rating(client, guest)
    assert [r["points"] for r in after["top"]] == [r["points"] + (20 if r["me"] else 0) for r in before["top"]]
    assert after["me"]["place"] == before["me"]["place"]


def test_an_on_screen_badge_shows_on_the_hall_with_first_name_and_last_initial(client, admin, clock):
    assert change(client, admin, "photo_hunter", on_screen=True).status_code == 200
    load(client, admin, photos(5), [])
    t = ids(client, admin)
    ivan = person("R-1", "Иван", "Петров")
    clock("09:30")
    for i in range(1, 6):
        send(client, ivan, t[f"photo{i}"])
    body = hall(client)["badge"]
    assert (body["name"], body["badge"]) == ("Иван П.", "Фотоохотник")
    # Every screen polling within the 15 seconds gets the same one
    assert hall(client)["badge"]["id"] == body["id"]
    # 15 seconds on, it has been shown: nothing else waits
    clock("09:31")
    assert hall(client)["badge"] is None


def test_a_badge_not_shown_within_60_seconds_is_dropped(client, admin, clock):
    assert change(client, admin, "photo_hunter", on_screen=True).status_code == 200
    load(client, admin, photos(5), [])
    t = ids(client, admin)
    ivan = person("R-1", "Иван", "Петров")
    clock("09:30")
    for i in range(1, 6):
        send(client, ivan, t[f"photo{i}"])
    clock("09:32")
    assert hall(client)["badge"] is None


def test_in_on_air_an_on_screen_badge_does_not_interrupt_the_hall(client, admin, clock):
    assert change(client, admin, "photo_hunter", on_screen=True).status_code == 200
    load(client, admin, photos(5), [])
    t = ids(client, admin)
    ivan = person("R-1", "Иван", "Петров")
    assert client.post("/api/hall/mode", json={"mode": "live"}, headers=admin).status_code == 200
    clock("09:30")
    for i in range(1, 6):
        send(client, ivan, t[f"photo{i}"])
    assert held_now("R-1") == {"photo_hunter"}
    assert hall(client)["badge"] is None
    for mode in ("pause", "logos"):
        assert client.post("/api/hall/mode", json={"mode": mode}, headers=admin).status_code == 200
        body = hall(client)["badge"]
        assert body is None if mode == "pause" else body["badge"] == "Фотоохотник"


def test_first_3_to_do_a_task_get_the_badge_and_a_rejection_moves_the_4th_in(client, admin, clock):
    load(client, admin, photos(1), [])
    t = ids(client, admin)
    assert add(client, admin, code="early", name="Ранняя пташка", rule="first_n", count=3,
               task_id=t["photo1"]).status_code == 200
    guests = [person(f"R-{i}", f"Гость {i}") for i in range(1, 5)]
    clock("09:30")
    for g in guests:
        send(client, g, t["photo1"])
    assert [held_now(f"R-{i}") for i in range(1, 5)] == [{"early"}, {"early"}, {"early"}, set()]
    with SessionLocal() as db:
        second = db.scalar(select(Submission.id).where(Submission.guest_id == guest_id("R-2")))
    assert decide(client, moderator_headers(client), second, "penalty").status_code == 200
    assert [held_now(f"R-{i}") for i in range(1, 5)] == [{"early"}, set(), {"early"}, {"early"}]


def test_a_badges_sheet_with_an_unknown_type_or_a_missing_number_is_refused_naming_the_rows(client, admin):
    load(client, admin, photos(1), [])
    before = {code: b["values"] for code, b in badge_rows(client, admin).items()}
    wb = load_workbook(io.BytesIO(client.get("/api/admin/tasks/export", headers=admin).content))
    ws = wb["Бейджи"]
    # A good row changed too: a refused file changes nothing of it either
    ws["D2"] = 2
    ws.append(["odd", "Странный", "Чудеса", 3])
    ws.append(["nonum", "Без числа", "Задания", None])
    ws.append(["badkind", "Плохой тип", "Задания", 2, "Танцы"])
    out = io.BytesIO()
    wb.save(out)
    r = upload(client, admin, out.getvalue())
    assert r.status_code == 200, r.text
    assert [(f["sheet"], f["row"], f["reason"]) for f in r.json()["failed"]] == [
        ("Бейджи", 7, "unknown_rule"), ("Бейджи", 8, "no_count"), ("Бейджи", 9, "unknown_kind")]
    # The old badges stay, each with its values as they were
    assert {code: b["values"] for code, b in badge_rows(client, admin).items()} == before
    assert sorted(before) == ["brand_friend", "erudite", "forum_spirit", "networker", "photo_hunter"]


def test_a_badges_sheet_adds_changes_and_switches_off_badges(client, admin, guest, clock):
    load(client, admin, photos(2), [])
    wb = load_workbook(io.BytesIO(client.get("/api/admin/tasks/export", headers=admin).content))
    ws = wb["Бейджи"]
    # photo_hunter goes (switched off), «Эрудит» changes, a new one comes
    ws.delete_rows(2)
    ws["D3"] = 3
    ws.append(["pair", "Пара фото", "Задания", 2, "Фото", None, None, 5, "да"])
    out = io.BytesIO()
    wb.save(out)
    clock("09:30")
    t = ids(client, admin)
    send(client, guest, t["photo1"])
    send(client, guest, t["photo2"])
    body = upload(client, admin, out.getvalue()).json()
    assert body["failed"] == []
    assert sorted((i["code"], i["change"]) for i in body["items"] if i["sheet"] == "Бейджи") == [
        ("erudite", "changed"), ("pair", "added"), ("photo_hunter", "hidden")]
    rows = badge_rows(client, admin)
    assert (rows["photo_hunter"]["values"]["active"], rows["erudite"]["values"]["count"]) == (False, 3)
    # The upload checks past activity at once, quietly
    assert held_now("R-1") == {"pair"}
    assert coins_of("R-1")[1] == 20 + 5


def test_a_badge_row_without_its_numbers_is_refused_naming_the_field(client, admin):
    r = add(client, admin, code="x", name="Икс", rule="bonuses")
    assert (r.status_code, r.json()["detail"]) == (400, {"code": "required", "field": "count"})
    r = add(client, admin, code="y", name="Игрек", rule="first_n", count=3)
    assert r.json()["detail"] == {"code": "required", "field": "task_id"}
    r = add(client, admin, code="z", name="Зет", rule="all_of_type")
    assert r.json()["detail"] == {"code": "required", "field": "kinds"}
    r = add(client, admin, code="w", name="Вэ", rule="magic", count=1)
    assert r.json()["detail"] == {"code": "bad_value", "field": "rule"}
    r = add(client, admin, code="k", name="Ка", rule="tasks", count=1, kinds="Танцы")
    assert r.json()["detail"] == {"code": "bad_kinds", "field": "kinds"}
    # badge:{ID} has to fit the ledger's reason
    r = add(client, admin, code="a" * 27, name="Длинный", rule="tasks", count=1)
    assert r.json()["detail"]["code"] == "length"


def test_a_badge_added_in_the_form_goes_at_once_to_guests_who_already_meet_it(client, admin, guest, clock):
    load(client, admin, [row("l1", "Ссылка 1", method="Ссылка"), row("l2", "Ссылка 2", method="Ссылка")], [])
    t = ids(client, admin)
    clock("09:30")
    link(client, guest, t["l1"])
    link(client, guest, t["l2"])
    r = add(client, admin, confirm=False, code="two", name="Два шага", rule="tasks", count=2, on_screen=True)
    assert r.json()["detail"]["impact"] == [{"code": "badge_recheck", "item": "two", "gained": 1, "lost": 0}]
    assert add(client, admin, code="two", name="Два шага", rule="tasks", count=2, kinds="действие",
               on_screen=True).status_code == 200
    assert held_now("R-1") == {"two"}
    # The type is kept as the file writes it
    assert badge_rows(client, admin)["two"]["values"]["kinds"] == "Действие"
    # An admin's recheck awards quietly
    assert hall(client)["badge"] is None
    assert new(feed(client, guest)) == ["two"]
    assert [b["code"] for b in profile(client, guest)["badges"]][-1] == "two"


def test_the_downloaded_file_holds_tags_five_badges_and_uploads_back_unchanged(client, admin):
    load(client, admin, photos(1), [])
    raw = client.get("/api/admin/tasks/export", headers=admin).content
    ws = load_workbook(io.BytesIO(raw))["Бейджи"]
    assert [list(r) for r in ws.iter_rows(values_only=True)] == [
        ["ID", "Название", "Тип правила", "Число", "Тип задания", "Партнёр", "Задание", "Монеты", "На экран"],
        ["photo_hunter", "Фотоохотник", "Задания", 5, "Фото, Фото+текст", None, None, 0, None],
        ["networker", "Нетворкер", "Все задания типа", None, "Нетворкинг", None, None, 0, None],
        ["erudite", "Эрудит", "Квизы подряд", 5, None, None, None, 0, None],
        ["brand_friend", "Друг бренда", "Задания", 3, None, "Любой один партнёр", None, 0, None],
        ["forum_spirit", "Дух форума", "Бонусы", 1, "Крейзи", None, None, 0, None],
    ]
    files = {"file": ("tasks.xlsx", raw, "application/octet-stream")}
    preview = client.post("/api/admin/tasks/import/preview", files=files, headers=admin).json()
    assert preview["failed"] == []
    assert [i for i in preview["items"] if i["sheet"] == "Бейджи"] == []


def test_the_log_records_a_badge_saved_in_the_form(client, admin):
    assert change(client, admin, "erudite", count=4).status_code == 200
    log = client.get("/api/admin/log", params={"kind": "badges"}, headers=admin).json()
    assert [(e["item"], e["field"], e["old_value"], e["new_value"]) for e in log] == [("erudite", "count", "5", "4")]


def test_a_retake_and_a_resend_takes_back_and_pays_the_coins_again(client, admin, guest, clock):
    assert change(client, admin, "photo_hunter", coins=20).status_code == 200
    load(client, admin, photos(5) + [row("text1", "Фото с подписью", method="Фото+текст")], [])
    t = ids(client, admin)
    clock("09:30")
    for i in range(1, 6):
        send(client, guest, t[f"photo{i}"])
    with SessionLocal() as db:
        first = db.scalar(select(Submission.id).where(Submission.task_id == t["photo1"]))
    decide(client, moderator_headers(client), first, "retake")
    assert coins_of("R-1")[1] == 40
    send(client, guest, t["text1"], text="Подпись")
    assert coins_of("R-1")[1] == 40 + 10 + 20


def test_changing_a_badges_coins_settles_with_the_guests_who_hold_it(client, admin, guest, clock):
    load(client, admin, photos(5), [])
    t = ids(client, admin)
    clock("09:30")
    for i in range(1, 6):
        send(client, guest, t[f"photo{i}"])
    assert held_now("R-1") == {"photo_hunter"}
    assert coins_of("R-1") == (50, 50)
    # Raised from 0 to 20: the holder gets the 20 at once, with no points
    assert change(client, admin, "photo_hunter", coins=20).status_code == 200
    assert coins_of("R-1") == (50, 70)
    # A new earner gets the same 20
    other = person("R-2", "Мария")
    for i in range(1, 6):
        send(client, other, t[f"photo{i}"])
    assert coins_of("R-2") == (50, 70)
    # Lowered back to 0: both holders' 20 are taken back by a reversal, and they keep the badge
    assert change(client, admin, "photo_hunter", coins=0).status_code == 200
    assert (coins_of("R-1"), coins_of("R-2")) == ((50, 50), (50, 50))
    assert (held_now("R-1"), held_now("R-2")) == ({"photo_hunter"}, {"photo_hunter"})
    with SessionLocal() as db:
        rows = db.scalars(select(ScoreEvent).where(ScoreEvent.guest_id == guest_id("R-1"),
                                                   ScoreEvent.reason == "badge:photo_hunter")
                          .order_by(ScoreEvent.id)).all()
        assert [(e.coins, e.reverses_id) for e in rows] == [(20, None), (-20, rows[0].id)]


def test_a_quiz_ended_by_its_timer_resets_the_run_even_before_anything_settles_it(client, admin, guest, clock):
    """4 perfect, the 5th left open until its timer ran out, then a 6th perfect: no «Эрудит» (piece 20)."""
    codes_ = [f"q{i}" for i in range(1, 7)]
    load(client, admin, [quiz(c, f"Квиз {c}", points=10, timer=60 if c == "q5" else None) for c in codes_],
         [q for c in codes_ for q in questions(c, 2)])
    t = ids(client, admin)
    clock("09:30")
    for c in codes_[:4]:
        assert play(client, guest, t[c], right=2)["result"]["correct"] == 2
    assert start(client, guest, t["q5"]).status_code == 200
    # Its minute runs out with nothing settling it; the 6th is played straight away
    clock("09:35")
    assert play(client, guest, t["q6"], right=2)["result"]["correct"] == 2
    assert held_now("R-1") == set()
    # Settled later, it keeps its place in the order: it finished at its deadline
    feed(client, guest)
    assert held_now("R-1") == set()
    with SessionLocal() as db:
        from app.models import QuizAttempt
        a = db.scalar(select(QuizAttempt).where(QuizAttempt.task_id == t["q5"]))
        assert (a.finished_at - a.started_at).total_seconds() == 60
