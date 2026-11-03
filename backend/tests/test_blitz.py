import io
import time
from datetime import datetime, timedelta
from decimal import Decimal
from threading import Barrier, Thread

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
from sqlalchemy import select, update

from app import stages
from app.db import SessionLocal
from app.main import app
from app.models import QuizAttempt, ScoreEvent, Stage
from tests.test_admin_settings import find, save
from tests.test_market import make_guest
from tests.test_qr_tasks import totals
from tests.test_quiz import HEAD as QUIZ_HEAD, QUESTION_HEAD, qr, questions, quiz
from tests.test_tasks import DUSHANBE, STAGE_HEAD, STAGES, admin, guest, upload  # noqa: F401 (fixtures)

HEAD = QUIZ_HEAD + ["Лимит", "Блиц", "Бонус за скорость", "Без потерь, сек", "Время бонуса, сек"]
START = datetime(2026, 12, 13, 9, 30, tzinfo=DUSHANBE)


def blitz(code, text, points=50, coins=None, timer=60, bonus=None, grace=None, until=None, flag="да", **kw):
    """A quiz row with the blitz columns (None = blank cell)."""
    return quiz(code, text, points=points, coins=coins, timer=timer, **kw) + [None, flag, bonus, grace, until]


def xlsx(task_rows, question_rows) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Этапы"
    ws.append(STAGE_HEAD)
    for r in STAGES:
        ws.append(r)
    wt = wb.create_sheet("Задания")
    wt.append(HEAD)
    for r in task_rows:
        wt.append(r + [None] * (len(HEAD) - len(r)))
    wq = wb.create_sheet("Вопросы")
    wq.append(QUESTION_HEAD)
    for r in question_rows:
        wq.append(r)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def load(client, admin, task_rows, question_rows) -> dict:
    r = upload(client, admin, xlsx(task_rows, question_rows))
    assert r.status_code == 200, r.text
    assert r.json()["failed"] == [], r.json()
    return r.json()


@pytest.fixture
def tick(monkeypatch):
    """The server clock, in seconds (fractions too) after 09:30:00 on the forum day."""
    def set_(seconds: float):
        t = START + timedelta(seconds=seconds)
        monkeypatch.setattr(stages, "now", lambda: t)
    return set_


def task_id(client, admin, code) -> int:
    return find(client, admin, "tasks", "code", code)["id"]


def start(client, guest, tid):
    r = client.post(f"/api/quiz/{tid}/start", headers=guest)
    assert r.status_code == 200, r.text
    return r.json()


def answer(client, guest, tid, question, option, **extra):
    r = client.post(f"/api/quiz/{tid}/answer", json={"question": question, "option": option, **extra}, headers=guest)
    assert r.status_code == 200, r.text
    return r.json()


def speed_rows(tid) -> list[ScoreEvent]:
    with SessionLocal() as db:
        return list(db.scalars(select(ScoreEvent).where(ScoreEvent.reason == f"speed:{tid}")))


def times(tid) -> dict:
    with SessionLocal() as db:
        return db.scalar(select(QuizAttempt.times).where(QuizAttempt.task_id == tid))


@pytest.mark.parametrize("took, bonus", [(2, 20), (3, 20), (7.5, 10), (12, 0), (12.5, 0)])
def test_the_bonus_is_full_in_the_grace_window_then_falls_to_zero(client, admin, guest, tick, took, bonus):
    load(client, admin, [blitz("B1", "Блиц")], questions("B1", 1))
    tid = task_id(client, admin, "B1")
    tick(0)
    base = totals(client, guest)
    start(client, guest, tid)
    tick(took)
    state = answer(client, guest, tid, 1, 1)
    # 008's points whatever the speed, the bonus on top
    assert state["result"] == {"correct": 1, "total": 1, "points": 50, "coins": 50, "speed": bonus}
    assert totals(client, guest) == (base[0] + 50 + bonus, base[1] + 50)
    assert [(e.points, e.coins, e.action) for e in speed_rows(tid)] == ([(bonus, 0, "speed")] if bonus else [])


def test_four_of_five_shows_the_end_line_and_pays_the_bonus_in_points_only(client, admin, guest, tick):
    load(client, admin, [blitz("B1", "Блиц", points=50, coins=50)], questions("B1", 5))
    tid = task_id(client, admin, "B1")
    tick(0)
    base = totals(client, guest)
    state = start(client, guest, tid)
    # Right at 1 s, 7.5 s (half), 12 s (none) and 1 s; question 4 wrong at once: no bonus, no penalty
    at = 0.0
    for took, option in [(1, 1), (7.5, 1), (12, 1), (0.5, 2), (1, 1)]:
        at += took
        tick(at)
        state = answer(client, guest, tid, state["question"]["number"], option)
    assert state["result"] == {"correct": 4, "total": 5, "points": 40, "coins": 40, "speed": 50}
    assert totals(client, guest) == (base[0] + 40 + 50, base[1] + 40)
    # Its own row, shown apart from 008's, at the stage's multiplier; paid once however often the quiz is finished
    (row,) = speed_rows(tid)
    assert (row.reason, row.action, row.base_points, row.points, row.coins) == (f"speed:{tid}", "speed", 50, 50, 0)
    client.post(f"/api/quiz/{tid}/finish", headers=guest)
    assert start(client, guest, tid)["result"]["speed"] == 50
    assert len(speed_rows(tid)) == 1
    # In the rating and the profile like any other points
    me = client.get("/api/rating", headers=guest).json()["me"]
    assert me["points"] == base[0] + 90
    history = client.get("/api/profile", headers=guest).json()["history"]
    assert next(e for e in history if e["text"] == "Блиц")["bonus"] == 50


def test_the_stage_multiplier_from_the_start_applies_to_the_bonus(client, admin, guest, tick):
    load(client, admin, [blitz("B1", "Блиц", bonus=15)], questions("B1", 1))
    with SessionLocal() as db:
        db.execute(update(Stage).where(Stage.number == 1).values(multiplier=Decimal("1.5")))
        db.commit()
    tid = task_id(client, admin, "B1")
    tick(0)
    start(client, guest, tid)
    with SessionLocal() as db:
        db.execute(update(Stage).where(Stage.number == 1).values(multiplier=Decimal(3)))
        db.commit()
    tick(1)
    # 15 × 1.5 = 22.5, halves up
    assert answer(client, guest, tid, 1, 1)["result"]["speed"] == 23
    (row,) = speed_rows(tid)
    assert (row.base_points, row.multiplier, row.points) == (15, Decimal("1.5"), 23)


def test_a_blitz_crossing_into_the_next_stage_keeps_the_stage_it_started_in(client, admin, guest, tick):
    load(client, admin, [blitz("B1", "Блиц")], questions("B1", 1))
    tid = task_id(client, admin, "B1")
    # Stage 1 ends at 10:30, an hour after START
    tick(3600 - 2)
    start(client, guest, tid)
    tick(3600 + 1)
    assert answer(client, guest, tid, 1, 1)["result"]["speed"] == 20
    with SessionLocal() as db:
        first = db.scalar(select(Stage.id).where(Stage.number == 1))
    (row,) = speed_rows(tid)
    assert row.stage_id == first


def test_the_phone_clock_plays_no_part(client, admin, guest, tick):
    load(client, admin, [blitz("B1", "Блиц")], questions("B1", 1))
    tid = task_id(client, admin, "B1")
    tick(0)
    start(client, guest, tid)
    tick(7.5)
    # A phone 5 minutes off sends its time along: the server times the answer by its own clock only
    wrong = (START + timedelta(minutes=5)).isoformat()
    state = client.post(f"/api/quiz/{tid}/answer", json={"question": 1, "option": 1, "sent_at": wrong, "at": wrong},
                        headers={**guest, "Date": "Sun, 13 Dec 2026 04:35:00 GMT"}).json()
    assert state["result"]["speed"] == 10


def test_a_reload_keeps_the_moment_the_question_was_first_sent(client, admin, guest, tick):
    load(client, admin, [blitz("B1", "Блиц")], questions("B1", 2))
    tid = task_id(client, admin, "B1")
    tick(0)
    start(client, guest, tid)
    tick(1)
    state = answer(client, guest, tid, 1, 1)
    sent = times(tid)["2"]["sent"]
    tick(6)
    again = start(client, guest, tid)
    assert again["question"] == state["question"]
    assert times(tid)["2"]["sent"] == sent
    tick(8.5)
    # Question 2 counts from 1 s, not from the reload at 6 s: 7.5 s, half the bonus
    assert answer(client, guest, tid, 2, 1)["result"]["speed"] == 20 + 10


def test_unanswered_questions_when_time_runs_out_get_no_bonus(client, admin, guest, tick):
    load(client, admin, [blitz("B1", "Блиц", timer=10)], questions("B1", 3))
    tid = task_id(client, admin, "B1")
    tick(0)
    start(client, guest, tid)
    tick(1)
    answer(client, guest, tid, 1, 1)
    tick(11)
    state = start(client, guest, tid)
    assert state["result"] == {"correct": 1, "total": 3, "points": 17, "coins": 17, "speed": 20}
    # An answer after the timer is ignored
    assert answer(client, guest, tid, 2, 1)["result"]["speed"] == 20


def test_a_quiz_that_isnt_a_blitz_pays_no_bonus(client, admin, guest, tick):
    load(client, admin, [blitz("Q1", "Квиз", flag=None)], questions("Q1", 1))
    tid = task_id(client, admin, "Q1")
    tick(0)
    start(client, guest, tid)
    tick(1)
    assert answer(client, guest, tid, 1, 1)["result"]["speed"] is None
    assert speed_rows(tid) == []


def test_blank_numbers_download_as_the_defaults(client, admin):
    load(client, admin, [blitz("B1", "Блиц"), blitz("B2", "Свой блиц", bonus=30, grace=2, until=10)],
         questions("B1", 1) + questions("B2", 1))
    raw = client.get("/api/admin/tasks/export", headers=admin).content
    wb = load_workbook(io.BytesIO(raw))
    head = [c.value for c in wb["Задания"][1]]
    assert head[-4:] == ["Блиц", "Бонус за скорость", "Без потерь, сек", "Время бонуса, сек"]
    tasks = {r[0].value: [c.value for c in r][-4:] for r in wb["Задания"].iter_rows(min_row=2)}
    assert tasks == {"B1": ["да", 20, 3, 12], "B2": ["да", 30, 2, 10]}
    # Uploading the download changes nothing
    body = upload(client, admin, raw).json()
    assert (body["added"], body["changed"], body["failed"]) == (0, 0, [])


@pytest.mark.parametrize("cells, reason", [
    ((None, 12, 12), "bad_speed_window"),
    ((None, 5, 4), "bad_speed_window"),
    ((None, None, 3), "bad_speed_window"),
    ((-1, None, None), "bad_speed_bonus"),
    ((10.5, None, None), "bad_speed_bonus"),
    ((None, "три", None), "bad_grace_seconds"),
])
def test_bad_blitz_numbers_refuse_the_whole_upload(client, admin, cells, reason):
    bonus, grace, until = cells
    body = upload(client, admin, xlsx([qr("HALL", "Зал"), blitz("B1", "Блиц", bonus=bonus, grace=grace, until=until)],
                                      questions("B1", 1))).json()
    assert [(f["row"], f["reason"]) for f in body["failed"]] == [(3, reason)]
    assert body["added"] == 0
    assert client.get("/api/admin/lists/tasks", headers=admin).json()["rows"] == []


def test_blitz_on_a_task_that_isnt_a_quiz_refuses_the_upload(client, admin):
    row = qr("HALL", "Зал") + [None, "да"]
    body = upload(client, admin, xlsx([row], [])).json()
    assert [(f["row"], f["reason"]) for f in body["failed"]] == [(2, "blitz_quiz_only")]
    load(client, admin, [qr("HALL", "Зал")], [])
    r = save(client, admin, "tasks", find(client, admin, "tasks", "code", "HALL"), blitz=True)
    assert (r.status_code, r.json()["detail"]) == (400, {"code": "quiz_only", "field": "blitz"})


def test_an_upload_changing_a_running_blitz_is_refused_and_it_stays_playable(client, admin, guest, tick):
    rows = [blitz("B1", "Блиц"), quiz("Q2", "Другой квиз")]
    load(client, admin, rows, questions("B1", 2) + questions("Q2", 1))
    tid = task_id(client, admin, "B1")
    tick(0)
    start(client, guest, tid)
    tick(1)
    answer(client, guest, tid, 1, 1)
    # Mid-blitz: a file raising its bonus (and renaming the other quiz) is refused whole, naming the blitz's row
    changed = [blitz("B1", "Блиц", bonus=100), quiz("Q2", "Новый текст")]
    body = upload(client, admin, xlsx(changed, questions("B1", 2) + questions("Q2", 1))).json()
    assert body["failed"] == [{"sheet": "Задания", "row": 2, "reason": "blitz_running"}]
    assert find(client, admin, "tasks", "code", "Q2")["values"]["text"] == "Другой квиз"
    assert find(client, admin, "tasks", "code", "B1")["values"]["speed_bonus"] == 20
    # The blitz plays on with its stored settings
    tick(2)
    assert answer(client, guest, tid, 2, 1)["result"]["speed"] == 40
    # Its other columns aren't locked by this piece
    body = upload(client, admin, xlsx([blitz("B1", "Блиц", points=60), quiz("Q2", "Другой квиз")],
                                      questions("B1", 2) + questions("Q2", 1))).json()
    assert body["failed"] == []


def test_the_form_refuses_a_bonus_change_while_the_window_is_open(client, admin, tick):
    load(client, admin, [blitz("B1", "Блиц", timer=None, start="13.12.2026 09:25", end="13.12.2026 09:35")],
         questions("B1", 1))
    tick(0)
    row = find(client, admin, "tasks", "code", "B1")
    for change in ({"speed_bonus": 40}, {"grace_seconds": 2}, {"bonus_seconds": 20}, {"blitz": False}):
        r = save(client, admin, "tasks", row, **change)
        assert (r.status_code, r.json()["detail"]) == (409, {"code": "quiz_running"}), change
    # Closing the window in the same save doesn't let it through: judged by the window guests play by
    r = save(client, admin, "tasks", row, speed_bonus=40, window_end="2026-12-13T09:29")
    assert r.status_code == 409
    # Its other fields follow their own rules
    assert save(client, admin, "tasks", row, text="Блиц финала").status_code == 200
    tick(6 * 60)
    row = find(client, admin, "tasks", "code", "B1")
    assert save(client, admin, "tasks", row, speed_bonus=40).status_code == 200


def test_the_form_sets_the_blitz_and_the_file_gives_it_back(client, admin, tick):
    load(client, admin, [quiz("Q1", "Квиз")], questions("Q1", 1))
    tick(0)
    row = find(client, admin, "tasks", "code", "Q1")
    assert (row["values"]["blitz"], row["values"]["speed_bonus"], row["values"]["grace_seconds"],
            row["values"]["bonus_seconds"]) == (False, 20, 3, 12)
    r = save(client, admin, "tasks", row, grace_seconds=8, bonus_seconds=8)
    assert (r.status_code, r.json()["detail"]) == (400, {"code": "bad_speed_window", "field": "grace_seconds"})
    r = save(client, admin, "tasks", row, blitz=True, speed_bonus=25, grace_seconds=None, bonus_seconds=15)
    assert r.status_code == 200, r.text
    assert {k: r.json()["values"][k] for k in ("blitz", "speed_bonus", "grace_seconds", "bonus_seconds")} == {
        "blitz": True, "speed_bonus": 25, "grace_seconds": 3, "bonus_seconds": 15}
    wb = load_workbook(io.BytesIO(client.get("/api/admin/tasks/export", headers=admin).content))
    tasks = {r[0].value: [c.value for c in r][-4:] for r in wb["Задания"].iter_rows(min_row=2)}
    assert tasks["Q1"] == ["да", 25, 3, 15]
    fields = {f["name"]: f for f in client.get("/api/admin/lists/tasks", headers=admin).json()["fields"]}
    assert {fields[k]["effect"] for k in ("blitz", "speed_bonus", "grace_seconds", "bonus_seconds")} == {"locked"}


def test_many_guests_answering_at_once_all_get_a_quick_reply(client, admin, tick):
    """A small stand-in for the load check (1.5 × the expected guests within 10 s): guests answering at the same
    moment don't wait on each other, as each attempt has its own lock."""
    n = 40
    load(client, admin, [blitz("B1", "Блиц")], questions("B1", 2))
    tid = task_id(client, admin, "B1")
    tick(0)
    guests = [make_guest(client, f"R-{i}", f"Гость {i}") for i in range(n)]
    for g in guests:
        start(client, g, tid)
    tick(1)
    gate = Barrier(n)
    replies: list[tuple[int, float]] = []

    def go(g):
        c = TestClient(app)
        gate.wait()
        began = time.perf_counter()
        r = c.post(f"/api/quiz/{tid}/answer", json={"question": 1, "option": 1}, headers=g)
        replies.append((r.status_code, time.perf_counter() - began))

    threads = [Thread(target=go, args=(g,)) for g in guests]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert [s for s, _ in replies] == [200] * n
    took = sorted(t for _, t in replies)
    assert took[int(n * 0.95) - 1] < 1.0
