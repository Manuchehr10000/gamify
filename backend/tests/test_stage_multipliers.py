import io
from decimal import Decimal

import pytest
from openpyxl import Workbook, load_workbook
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Claim, QuizAttempt, ScoreEvent, Stage
from tests.conftest import moderator_headers
from tests.test_admin_settings import find, preview, save
from tests.test_market import buy, make_guest, market
from tests.test_moderation import decide, queue
from tests.test_qr_tasks import qr_codes, scan, totals
from tests.test_quiz import QUESTION_HEAD, answer, at, questions, start  # noqa: F401 (fixtures)
from tests.test_submissions import claim, ids, new_id, send_files
from tests.test_tasks import STAGE_HEAD, STAGES, TASK_HEAD, admin, clock, guest, upload  # noqa: F401 (fixtures)
from tests.test_tasks import xlsx as old_xlsx

HEAD = TASK_HEAD + ["Выполнение", "Ссылка", "Таймер, сек", "Требует"]
MARKET_PRIZES = [["P1", "Блокнот", "TAG", 10, 100]]


def row(code, stage, text, points=10, method="QR", type_="Действие"):
    return [code, stage, type_, text, points, None, None, None, None, None, method, None, None, None]


def quiz(code, text, points, stage=1):
    return row(code, stage, text, points, method="Квиз", type_="Квиз")


def xlsx(multipliers=(None, None, None, None), task_rows=(), question_rows=(), market=None, prizes=()) -> bytes:
    """The four stages with a «Множитель» each (None = blank cell), the tasks and, when given, questions and prizes."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Этапы"
    ws.append(STAGE_HEAD + ["Маркет", "Множитель"])
    for r, m in zip(STAGES, multipliers):
        ws.append(r + ["да" if r[0] == market else None, m])
    wt = wb.create_sheet("Задания")
    wt.append(HEAD)
    for r in task_rows:
        wt.append(r)
    if question_rows:
        wq = wb.create_sheet("Вопросы")
        wq.append(QUESTION_HEAD)
        for r in question_rows:
            wq.append(r)
    if prizes:
        wp = wb.create_sheet("Призы")
        wp.append(["ID", "Название", "Партнёр", "Цена в монетах", "Количество"])
        for r in prizes:
            wp.append(r)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def load(client, admin, **kw) -> dict:
    r = upload(client, admin, xlsx(**kw))
    assert r.status_code == 200, r.text
    assert r.json()["failed"] == [], r.json()
    return r.json()


def set_multiplier(client, admin, number: int, value) -> None:
    """The admin's stage form: a new «Множитель» for the stage."""
    r = save(client, admin, "stages", find(client, admin, "stages", "number", number), confirm=True, multiplier=value)
    assert r.status_code == 200, r.text


def awards() -> list[ScoreEvent]:
    with SessionLocal() as db:
        return list(db.scalars(select(ScoreEvent).where(ScoreEvent.action == "task").order_by(ScoreEvent.id)))


def test_points_are_multiplied_half_up_and_coins_stay(client, admin, guest, clock):
    load(client, admin, multipliers=(None, None, 1.5, None), task_rows=[row("qr3", 3, "QR этапа 3", points=5)])
    clock("15:00")
    assert scan(client, guest, qr_codes(client, admin)["qr3"]).json()["result"] == "awarded"
    # 5 × 1.5 = 7.5 → 8, not Python's banker's 8-or-7; coins 1:1 with the base points
    assert totals(client, guest) == (8, 5)
    (e,) = awards()
    assert (e.base_points, e.multiplier, e.points, e.coins) == (5, Decimal("1.5"), 8, 5)


def test_a_stage_at_one_pays_as_before(client, admin, guest, clock):
    load(client, admin, task_rows=[row("qr1", 1, "QR этапа 1", points=7)])
    clock("09:30")
    scan(client, guest, qr_codes(client, admin)["qr1"])
    assert totals(client, guest) == (7, 7)
    assert awards()[0].multiplier == 1


def test_a_link_confirmation_takes_the_running_stages_multiplier(client, admin, guest, clock):
    link = row("link1", 1, "Зарегистрироваться", points=5, method="Ссылка")
    link[11] = "https://tag.tj/register"
    load(client, admin, multipliers=(1.5, None, None, None), task_rows=[link])
    clock("09:30")
    r = client.post(f"/api/tasks/{ids(client, admin)['link1']}/complete", headers=guest)
    assert r.json()["result"] == "awarded", r.text
    assert totals(client, guest) == (8, 5)
    (e,) = awards()
    assert (e.base_points, e.multiplier, e.points) == (5, Decimal("1.5"), 8)


def test_a_claim_keeps_the_multiplier_it_was_made_at(client, admin, guest, clock):
    load(client, admin, multipliers=(2, None, None, None), task_rows=[row("photo1", 1, "Фото у стенда", method="Фото")])
    clock("09:30")
    cid = new_id()
    assert claim(client, guest, ids(client, admin)["photo1"], cid).json()["result"] == "claimed"
    with SessionLocal() as db:
        assert db.get(Claim, cid).multiplier == 2
    # The admin raises it before the photo arrives
    set_multiplier(client, admin, 1, 3)
    assert send_files(client, guest, cid).json()["result"] == "awarded"
    assert totals(client, guest) == (20, 10)
    assert awards()[0].multiplier == 2


def test_a_new_claim_after_the_change_takes_the_new_multiplier(client, admin, guest, clock):
    load(client, admin, multipliers=(2, None, None, None), task_rows=[row("text1", 1, "Отзыв", method="Текст")])
    clock("09:30")
    set_multiplier(client, admin, 1, 3)
    assert claim(client, guest, ids(client, admin)["text1"], new_id(), "Отлично").json()["result"] == "awarded"
    assert totals(client, guest) == (30, 10)


@pytest.mark.parametrize("action", ["retake", "penalty"])
def test_a_rejection_takes_back_exactly_what_was_paid(client, admin, guest, clock, action):
    load(client, admin, multipliers=(2.5, None, None, None), task_rows=[row("text1", 1, "Отзыв", points=5, method="Текст")])
    clock("09:30")
    claim(client, guest, ids(client, admin)["text1"], new_id(), "Отлично")
    # 5 × 2.5 = 12.5 → 13
    assert totals(client, guest) == (13, 5)
    # A later change doesn't touch what is taken back
    set_multiplier(client, admin, 1, 4)
    moderator = moderator_headers(client)
    sid = queue(client, moderator)["items"][0]["id"]
    assert decide(client, moderator, sid, action).json()["result"] == "decided"
    assert totals(client, guest) == (0, 0)
    with SessionLocal() as db:
        back = db.scalar(select(ScoreEvent).where(ScoreEvent.action == action))
    assert (back.base_points, back.multiplier, back.points) == (-13, 1, -13)


def test_the_bonus_is_a_share_of_the_multiplied_points(client, admin, guest, clock):
    load(client, admin, multipliers=(2, None, None, None), task_rows=[row("text1", 1, "Отзыв", points=35, method="Текст")])
    clock("09:30")
    claim(client, guest, ids(client, admin)["text1"], new_id(), "Отлично")
    assert totals(client, guest) == (70, 35)
    moderator = moderator_headers(client)
    decide(client, moderator, queue(client, moderator)["items"][0]["id"], "bonus")
    # 50% of 70: 35 more points, coins as they were
    assert totals(client, guest) == (105, 35)
    with SessionLocal() as db:
        bonus = db.scalar(select(ScoreEvent).where(ScoreEvent.action == "bonus"))
    assert (bonus.base_points, bonus.multiplier, bonus.points) == (35, 1, 35)


def test_the_market_task_takes_the_stage_running_at_the_purchase(client, admin, clock):
    load(client, admin, multipliers=(None, None, 2, 3), market=3, prizes=MARKET_PRIZES,
         task_rows=[row("buy", 3, "Обменять монеты в маркете", points=15, method="Маркет")])
    guest = make_guest(client, "R-1", "Иван", coins=100)
    clock("17:00")
    assert buy(client, guest, market(client, guest), "Блокнот").status_code == 200
    assert totals(client, guest) == (45, 100 - 10 + 15)


@pytest.mark.parametrize("cell", [1.3, "1,3", 0.5, 5.5, 6, "два"])
def test_a_bad_multiplier_in_the_sheet_is_refused(client, admin, cell):
    r = upload(client, admin, xlsx(multipliers=(cell, None, None, None)))
    assert r.json()["failed"] == [{"sheet": "Этапы", "row": 2, "reason": "bad_multiplier"}]


def test_halves_read_with_a_comma_or_a_dot_and_blank_is_one(client, admin):
    load(client, admin, multipliers=("1,5", 2.5, None, 5))
    with SessionLocal() as db:
        got = {s.number: s.multiplier for s in db.scalars(select(Stage))}
    assert got == {1: Decimal("1.5"), 2: Decimal("2.5"), 3: 1, 4: 5}


@pytest.mark.parametrize("value", [1.3, "1,3", 0, 5.5, "x", True])
def test_a_bad_multiplier_in_the_form_is_refused(client, admin, value):
    load(client, admin)
    r = save(client, admin, "stages", find(client, admin, "stages", "number", 1), confirm=True, multiplier=value)
    assert r.status_code == 400
    assert r.json()["detail"] == {"code": "bad_multiplier", "field": "multiplier"}


def test_the_form_takes_halves_and_blank_is_one(client, admin):
    load(client, admin)
    set_multiplier(client, admin, 1, "2,5")
    assert find(client, admin, "stages", "number", 1)["values"]["multiplier"] == 2.5
    set_multiplier(client, admin, 1, None)
    assert find(client, admin, "stages", "number", 1)["values"]["multiplier"] == 1
    # The change log names the field and both values
    log = client.get("/api/admin/log", params={"kind": "stages"}, headers=admin).json()
    assert [(e["field"], e["old_value"], e["new_value"]) for e in log[:2]] == [
        ("multiplier", "2.5", "1"), ("multiplier", "1", "2.5")]


def test_the_feed_sends_the_current_stages_multiplier(client, admin, guest, clock):
    load(client, admin, multipliers=(2, None, None, None), task_rows=[row("qr1", 1, "QR"), row("qr2", 2, "QR 2")])
    clock("09:30")
    stage = client.get("/api/feed", headers=guest).json()["stage"]
    assert (stage["number"], stage["multiplier"]) == (1, 2)
    # Cards keep the base points; the «×2» corner says they are multiplied
    assert client.get("/api/feed", headers=guest).json()["tasks"][0]["points"] == 10
    clock("11:00")
    assert client.get("/api/feed", headers=guest).json()["stage"]["multiplier"] == 1


def test_a_quiz_pays_at_the_multiplier_from_start(client, admin, guest, at):
    load(client, admin, multipliers=(2, None, None, None), task_rows=[quiz("q1", "Квиз", 50)],
         question_rows=questions("q1", 5))
    at("09:30:00")
    task_id = ids(client, admin)["q1"]
    state = start(client, guest, task_id).json()
    set_multiplier(client, admin, 1, 3)
    while state["question"]:
        q = state["question"]["number"]
        state = answer(client, guest, task_id, q, 1 if q <= 3 else 2).json()
    # 3 of 5: the share is 30, × 2 from «Начать»; coins are the plain share
    assert state["result"] == {"correct": 3, "total": 5, "points": 60, "coins": 30, "speed": None}
    with SessionLocal() as db:
        assert db.scalar(select(QuizAttempt.multiplier)) == 2


def test_a_quiz_share_is_rounded_up_then_multiplied_once(client, admin, guest, at):
    load(client, admin, multipliers=(1.5, None, None, None), task_rows=[quiz("q1", "Квиз", 10)],
         question_rows=questions("q1", 3))
    at("09:30:00")
    task_id = ids(client, admin)["q1"]
    state = start(client, guest, task_id).json()
    while state["question"]:
        q = state["question"]["number"]
        state = answer(client, guest, task_id, q, 1 if q <= 1 else 2).json()
    # 1 of 3 of 10 = 3.33 → 4, × 1.5 = 6
    assert state["result"]["points"] == 6


def test_one_of_three_on_a_ten_point_quiz_at_one_gives_four(client, admin, guest, at):
    load(client, admin, task_rows=[quiz("q1", "Квиз", 10)], question_rows=questions("q1", 3))
    at("09:30:00")
    task_id = ids(client, admin)["q1"]
    state = start(client, guest, task_id).json()
    while state["question"]:
        q = state["question"]["number"]
        state = answer(client, guest, task_id, q, 1 if q <= 1 else 2).json()
    assert state["result"]["points"] == 4


def test_export_writes_the_column_and_uploads_back_unchanged(client, admin):
    load(client, admin, multipliers=(None, 1.5, 2, 5), task_rows=[row("qr1", 1, "QR")])
    data = client.get("/api/admin/tasks/export", headers=admin).content
    sheet = list(load_workbook(io.BytesIO(data))["Этапы"].iter_rows(values_only=True))
    col = sheet[0].index("Множитель")
    assert [r[col] for r in sheet[1:]] == [1, 1.5, 2, 5]
    assert preview(client, admin, data)["items"] == []
    body = upload(client, admin, data).json()
    assert (body["stages_changed"], body["failed"]) == (0, [])


def test_an_older_file_without_the_column_leaves_the_multipliers(client, admin):
    load(client, admin, multipliers=(2, None, None, None))
    r = upload(client, admin, old_xlsx(task_rows=[]))
    assert r.json()["failed"] == []
    assert find(client, admin, "stages", "number", 1)["values"]["multiplier"] == 2
