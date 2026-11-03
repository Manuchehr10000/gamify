import io
from datetime import datetime

import pytest
from openpyxl import Workbook, load_workbook

from app import stages
from tests.test_qr_tasks import HEAD as QR_HEAD, qr_codes, scan, totals
from tests.test_tasks import DUSHANBE, STAGE_HEAD, STAGES, admin, clock, guest, upload  # noqa: F401 (fixtures)

HEAD = QR_HEAD + ["Таймер, сек", "Требует"]
QUESTION_HEAD = ["ID задания", "№ вопроса", "Вопрос", "Вариант 1", "Вариант 2", "Вариант 3", "Вариант 4",
                 "Правильный (1–4)"]


def quiz(code, text, points=50, coins=None, timer=None, requires=None, partner=None, start=None, end=None, stage=1):
    return [code, stage, "Квиз", text, points, coins, partner, None, start, end, "Квиз", None, timer, requires]


def qr(code, text):
    return [code, 1, "Территориальное", text, 10, None, None, None, None, None, "QR", None, None, None]


def questions(code, n, correct=1):
    return [[code, i, f"Вопрос {i}", "А", "Б", "В", "Г", correct] for i in range(1, n + 1)]


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
        wt.append(r)
    wq = wb.create_sheet("Вопросы")
    wq.append(QUESTION_HEAD)
    for r in question_rows:
        wq.append(r)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def load(client, admin, task_rows, question_rows):
    r = upload(client, admin, xlsx(task_rows, question_rows))
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def at(monkeypatch):
    """The server clock to the second, Dushanbe time on the forum day."""
    def set_(hhmmss: str):
        h, m, s = map(int, hhmmss.split(":"))
        t = datetime(2026, 12, 13, h, m, s, tzinfo=DUSHANBE)
        monkeypatch.setattr(stages, "now", lambda: t)
    return set_


def card(client, guest, text):
    return next((t for t in client.get("/api/feed", headers=guest).json()["tasks"] if t["text"] == text), None)


def start(client, guest, task_id):
    return client.post(f"/api/quiz/{task_id}/start", headers=guest)


def answer(client, guest, task_id, question, option):
    return client.post(f"/api/quiz/{task_id}/answer", json={"question": question, "option": option}, headers=guest)


def play(client, guest, task_id, right: int):
    """Answer every question, the first `right` of them with option 1 (the right one in `questions`)."""
    state = start(client, guest, task_id).json()
    while state["question"]:
        q = state["question"]["number"]
        state = answer(client, guest, task_id, q, 1 if q <= right else 2).json()
    return state


def test_quiz_opens_one_question_at_a_time_with_shuffled_options(client, admin, guest, at):
    body = load(client, admin, [quiz("Q1", "Квиз о форуме")], questions("Q1", 5))
    assert (body["added"], body["failed"]) == (1, [])
    at("09:30:00")
    task = card(client, guest, "Квиз о форуме")
    assert (task["method"], task["locked"]) == ("quiz", False)
    state = start(client, guest, task["id"]).json()
    assert (state["total"], state["answered"], state["seconds_left"], state["result"]) == (5, 0, None, None)
    first = state["question"]
    assert (first["number"], first["text"]) == (1, "Вопрос 1")
    assert sorted(o["n"] for o in first["options"]) == [1, 2, 3, 4]
    assert {o["text"] for o in first["options"]} == {"А", "Б", "В", "Г"}
    # Never the right answer, and the same order after a reload
    assert all(set(o) == {"n", "text"} for o in first["options"])
    assert start(client, guest, task["id"]).json()["question"] == first
    # Shuffled: across the 5 questions the order isn't always the file's
    orders, state = [], start(client, guest, task["id"]).json()
    while state["question"]:
        orders.append([o["n"] for o in state["question"]["options"]])
        state = answer(client, guest, task["id"], state["question"]["number"], 1).json()
    assert len(orders) == 5
    assert any(o != [1, 2, 3, 4] for o in orders)


def test_three_of_five_pays_three_fifths_and_hides_the_answers(client, admin, guest, at):
    load(client, admin, [quiz("Q1", "Квиз")], questions("Q1", 5))
    at("09:30:00")
    task = card(client, guest, "Квиз")
    base = totals(client, guest)
    state = play(client, guest, task["id"], right=3)
    assert state["result"] == {"correct": 3, "total": 5, "points": 30, "coins": 30, "speed": None}
    # Only the score: no question comes back with its right option
    assert state["question"] is None
    assert set(state) == {"text", "total", "answered", "question", "seconds_left", "result"}
    assert totals(client, guest) == (base[0] + 30, base[1] + 30)
    assert client.get(f"/api/tasks/{task['id']}", headers=guest).json()["done"] is True


def test_partner_quiz_pays_coins_by_the_rule(client, admin, guest, at):
    load(client, admin, [quiz("P1", "Квиз партнёра", points=25, partner="Coca-Cola")], questions("P1", 2))
    at("09:30:00")
    base = totals(client, guest)
    state = play(client, guest, card(client, guest, "Квиз партнёра")["id"], right=2)
    assert (state["result"]["points"], state["result"]["coins"]) == (25, 38)
    assert totals(client, guest) == (base[0] + 25, base[1] + 38)


def test_points_round_up(client, admin, guest, at):
    load(client, admin, [quiz("Q1", "Квиз", points=10)], questions("Q1", 3))
    at("09:30:00")
    state = play(client, guest, card(client, guest, "Квиз")["id"], right=1)
    assert (state["result"]["points"], state["result"]["coins"]) == (4, 4)


def test_reload_keeps_the_countdown(client, admin, guest, at):
    load(client, admin, [quiz("B1", "Блиц", timer=60)], questions("B1", 5))
    at("09:30:00")
    task = card(client, guest, "Блиц")
    assert task["timer_seconds"] == 60
    assert start(client, guest, task["id"]).json()["seconds_left"] == 60
    at("09:30:30")
    assert start(client, guest, task["id"]).json()["seconds_left"] == 30


def test_timer_end_closes_the_quiz_and_unanswered_count_as_wrong(client, admin, guest, at):
    load(client, admin, [quiz("B1", "Блиц", timer=60)], questions("B1", 5))
    at("09:30:00")
    task_id = card(client, guest, "Блиц")["id"]
    base = totals(client, guest)
    start(client, guest, task_id)
    for q in (1, 2, 3):
        answer(client, guest, task_id, q, 1)
    at("09:31:00")
    state = client.post(f"/api/quiz/{task_id}/finish", headers=guest).json()
    assert state["result"] == {"correct": 3, "total": 5, "points": 30, "coins": 30, "speed": None}
    assert totals(client, guest) == (base[0] + 30, base[1] + 30)


def test_timer_end_pays_even_if_the_screen_was_closed(client, admin, guest, at):
    load(client, admin, [quiz("B1", "Блиц", timer=60)], questions("B1", 5))
    at("09:30:00")
    task_id = card(client, guest, "Блиц")["id"]
    base = totals(client, guest)
    start(client, guest, task_id)
    answer(client, guest, task_id, 1, 1)
    at("09:32:00")
    assert totals(client, guest) == (base[0] + 10, base[1] + 10)
    assert client.get(f"/api/tasks/{task_id}", headers=guest).json()["done"] is True


def test_timer_end_counts_in_the_hall_before_the_guest_comes_back(client, admin, guest, at):
    load(client, admin, [quiz("B1", "Блиц", timer=60)], questions("B1", 5))
    at("09:30:00")
    task_id = card(client, guest, "Блиц")["id"]
    start(client, guest, task_id)
    answer(client, guest, task_id, 1, 1)
    at("09:32:00")
    # The guest never reopens the app; the projector still shows the blitz's points
    assert [p["points"] for p in client.get("/api/hall").json()["top"]] == [10]


def test_answer_after_the_timer_is_ignored(client, admin, guest, at):
    load(client, admin, [quiz("B1", "Блиц", timer=60)], questions("B1", 5))
    at("09:30:00")
    task_id = card(client, guest, "Блиц")["id"]
    start(client, guest, task_id)
    answer(client, guest, task_id, 1, 1)
    at("09:31:05")
    r = answer(client, guest, task_id, 2, 1)
    assert r.status_code == 200
    assert r.json()["result"]["correct"] == 1
    assert r.json()["answered"] == 1


def test_finished_quiz_shows_the_result_and_takes_no_more_answers(client, admin, guest, at):
    load(client, admin, [quiz("Q1", "Квиз")], questions("Q1", 5))
    at("09:30:00")
    task_id = card(client, guest, "Квиз")["id"]
    play(client, guest, task_id, right=3)
    points = totals(client, guest)
    again = start(client, guest, task_id).json()
    assert again["result"] == {"correct": 3, "total": 5, "points": 30, "coins": 30, "speed": None}
    assert again["question"] is None
    assert answer(client, guest, task_id, 1, 1).json()["result"]["correct"] == 3
    client.post(f"/api/quiz/{task_id}/finish", headers=guest)
    assert totals(client, guest) == points


def test_unfinished_quiz_continues_where_it_stopped(client, admin, guest, at):
    load(client, admin, [quiz("Q1", "Квиз")], questions("Q1", 5))
    at("09:30:00")
    task_id = card(client, guest, "Квиз")["id"]
    start(client, guest, task_id)
    answer(client, guest, task_id, 1, 1)
    answer(client, guest, task_id, 2, 1)
    state = start(client, guest, task_id).json()
    assert (state["answered"], state["question"]["number"]) == (2, 3)
    # Out of turn or a made-up option is refused; a retry of a taken answer changes nothing
    assert answer(client, guest, task_id, 4, 1).status_code == 400
    assert answer(client, guest, task_id, 3, 7).status_code == 400
    assert answer(client, guest, task_id, 1, 2).json()["answered"] == 2


def test_window_quiz_leaves_the_feed_when_it_closes(client, admin, guest, at):
    load(client, admin, [quiz("W1", "Квиз на 5 минут", start="13.12.2026 09:30", end="13.12.2026 09:35")],
         questions("W1", 2))
    at("09:31:00")
    task = card(client, guest, "Квиз на 5 минут")
    assert task["window_end"].startswith("2026-12-13T09:35")
    at("09:35:00")
    assert card(client, guest, "Квиз на 5 минут") is None
    assert start(client, guest, task["id"]).status_code == 409


def test_quiz_started_before_the_close_finishes_within_its_timer(client, admin, guest, at):
    load(client, admin, [quiz("W1", "Квиз", timer=120, start="13.12.2026 09:30", end="13.12.2026 09:35")],
         questions("W1", 2))
    at("09:34:30")
    task_id = card(client, guest, "Квиз")["id"]
    start(client, guest, task_id)
    at("09:35:30")
    answer(client, guest, task_id, 1, 1)
    state = answer(client, guest, task_id, 2, 1).json()
    assert state["result"]["correct"] == 2


def test_quiz_needs_the_hall_check_in_first(client, admin, guest, at):
    load(client, admin, [quiz("M1", "Вопросы по мастер-классу", requires="HALL"), qr("HALL", "Отметиться в зале")],
         questions("M1", 2))
    at("09:30:00")
    task = card(client, guest, "Вопросы по мастер-классу")
    assert task["locked"] is True
    r = start(client, guest, task["id"])
    assert (r.status_code, r.json()["detail"]) == (403, "check_in_first")
    assert scan(client, guest, qr_codes(client, admin)["HALL"]).json()["result"] == "awarded"
    assert card(client, guest, "Вопросы по мастер-классу")["locked"] is False
    assert start(client, guest, task["id"]).status_code == 200


@pytest.mark.parametrize("task_row,question_rows,failed", [
    (quiz("Q2", "Без вопросов"), [], [("Задания", 3, "no_questions")]),
    (quiz("Q2", "Плохой ответ"), [["Q2", 1, "Вопрос", "А", "Б", None, None, 5]],
     [("Вопросы", 7, "bad_correct"), ("Задания", 3, "no_questions")]),
    (quiz("Q2", "Ответ без варианта"), [["Q2", 1, "Вопрос", "А", "Б", None, None, 3]],
     [("Вопросы", 7, "bad_correct"), ("Задания", 3, "no_questions")]),
    (quiz("Q2", "Один вариант"), [["Q2", 1, "Вопрос", "А", None, None, None, 1]],
     [("Вопросы", 7, "bad_options"), ("Задания", 3, "no_questions")]),
    (quiz("Q2", "Таймер", timer="минута"), questions("Q2", 1), [("Задания", 3, "bad_timer")]),
    (quiz("Q2", "Требует", requires="NOPE"), questions("Q2", 1), [("Задания", 3, "unknown_requires")]),
])
def test_bad_quiz_rows_refuse_the_file(client, admin, task_row, question_rows, failed):
    body = load(client, admin, [quiz("Q1", "Хороший квиз"), task_row], questions("Q1", 5) + question_rows)
    assert body["added"] == 0
    assert sorted((f["sheet"], f["row"], f["reason"]) for f in body["failed"]) == sorted(failed)


def test_quiz_fails_when_its_hall_qr_row_fails(client, admin):
    bad_qr = qr("HALL", "Зал")
    bad_qr[2] = "Неизвестный тип"
    body = load(client, admin, [quiz("M1", "Мастер-класс", requires="HALL"), bad_qr], questions("M1", 2))
    assert body["added"] == 0
    assert sorted((f["row"], f["reason"]) for f in body["failed"]) == [(2, "unknown_requires"), (3, "unknown_type")]


def test_quiz_fails_when_its_hall_qr_row_breaks_on_reupload(client, admin):
    load(client, admin, [quiz("M1", "Мастер-класс", requires="HALL"), qr("HALL", "Зал")], questions("M1", 2))
    bad_qr = qr("HALL", "Зал")
    bad_qr[2] = "Неизвестный тип"
    body = load(client, admin, [quiz("M1", "Мастер-класс", requires="HALL"), bad_qr], questions("M1", 2))
    assert sorted((f["row"], f["reason"]) for f in body["failed"]) == [(2, "unknown_requires"), (3, "unknown_type")]
    # Refused whole: both stay as they were
    assert body["hidden"] == 0


def test_question_for_a_task_that_is_not_a_quiz_fails(client, admin):
    body = load(client, admin, [quiz("Q1", "Квиз"), qr("HALL", "Зал")], questions("Q1", 2) + questions("HALL", 1))
    assert body["failed"] == [{"sheet": "Вопросы", "row": 4, "reason": "not_a_quiz"}]


def test_quiz_round_trips_through_the_file(client, admin):
    rows = [quiz("M1", "Квиз", timer=60, requires="HALL"), qr("HALL", "Зал")]
    qs = questions("M1", 2) + [["M1", 3, "Три варианта", "А", "Б", "В", None, 3]]
    load(client, admin, rows, qs)
    raw = client.get("/api/admin/tasks/export", headers=admin).content
    wb = load_workbook(io.BytesIO(raw))
    assert [c.value for c in wb["Задания"][1]][-7:-4] == ["Таймер, сек", "Требует", "Лимит"]
    tasks = {r[0].value: [c.value for c in r] for r in wb["Задания"].iter_rows(min_row=2)}
    assert tasks["M1"][10:15] == ["Квиз", None, 60, "HALL", None]
    assert tasks["HALL"][10:15] == ["QR", None, None, None, None]
    assert [c.value for c in wb["Вопросы"][1]] == QUESTION_HEAD
    assert [[c.value for c in r] for r in wb["Вопросы"].iter_rows(min_row=2)] == qs
    # Uploading the downloaded file changes nothing
    body = upload(client, admin, raw).json()
    assert (body["added"], body["changed"], body["failed"]) == (0, 0, [])


def test_reupload_replaces_the_questions(client, admin, guest, at):
    load(client, admin, [quiz("Q1", "Квиз")], questions("Q1", 5))
    body = load(client, admin, [quiz("Q1", "Квиз")], questions("Q1", 2))
    assert body["changed"] == 1
    at("09:30:00")
    assert play(client, guest, card(client, guest, "Квиз")["id"], right=2)["result"]["total"] == 2
