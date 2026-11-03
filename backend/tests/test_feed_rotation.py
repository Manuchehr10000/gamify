import io
from datetime import timedelta
from threading import Barrier, Thread

from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
from sqlalchemy import select, update

from app import stages
from app.db import SessionLocal
from app.main import app
from app.models import Claim, Submission, Task
from tests.conftest import moderator_headers
from tests.test_admin_settings import find, save
from tests.test_market import make_guest
from tests.test_moderation import decide, queue
from tests.test_qr_tasks import HEAD, qr_codes, scan, totals
from tests.test_submissions import claim, ids, new_id, send_files, send_photo
from tests.test_tasks import STAGE_HEAD, STAGES, admin, clock, guest, upload  # noqa: F401 (fixtures)

TASK_HEAD = HEAD + ["Таймер, сек", "Требует", "Лимит"]
QUESTION_HEAD = ["ID задания", "№ вопроса", "Вопрос", "Вариант 1", "Вариант 2", "Вариант 3", "Вариант 4",
                 "Правильный (1–4)"]


def task(code, text, method="QR", stage=1, limit=None, start=None, end=None, points=10):
    return [code, stage, "Действие", text, points, None, None, None, start, end, method, None, None, None, limit]


def xlsx(task_rows, batch=None, questions=()) -> bytes:
    """Both sheets with the new columns: «Карточек в ленте» on every stage (blank = 15) and «Лимит» on tasks."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Этапы"
    ws.append(STAGE_HEAD + ["Маркет", "Карточек в ленте"])
    for r in STAGES:
        ws.append(r + [None, batch])
    wt = wb.create_sheet("Задания")
    wt.append(TASK_HEAD)
    for r in task_rows:
        wt.append(r)
    if questions:
        wq = wb.create_sheet("Вопросы")
        wq.append(QUESTION_HEAD)
        for r in questions:
            wq.append(r)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def load(client, admin, task_rows, batch=None, questions=()):
    r = upload(client, admin, xlsx(task_rows, batch, questions))
    assert r.status_code == 200, r.text
    assert r.json()["failed"] == [], r.json()
    return ids(client, admin)


def catalog(n=40) -> list[list]:
    """n stage-1 QR tasks, «Задание 1» … «Задание n» in the order the file gives them."""
    return [task(f"T{i:02d}", f"Задание {i}") for i in range(1, n + 1)]


def shown(feed: dict) -> list[str]:
    return [t["text"] for t in feed["tasks"]]


def nums(feed: dict) -> list[int]:
    return [int(t["text"].split()[-1]) for t in feed["tasks"] if t["text"].startswith("Задание ")]


def get(client, guest) -> dict:
    r = client.get("/api/feed", headers=guest)
    assert r.status_code == 200, r.text
    return r.json()


def nxt(client, guest) -> dict:
    """A page load of /app: the app opened or reloaded."""
    r = client.post("/api/feed/next", headers=guest)
    assert r.status_code == 200, r.text
    return r.json()


def card(client, guest, task_id) -> dict:
    r = client.get(f"/api/tasks/{task_id}", headers=guest)
    assert r.status_code == 200, r.text
    return r.json()


def submission(task_id) -> Submission:
    with SessionLocal() as db:
        return db.scalar(select(Submission).where(Submission.task_id == task_id).order_by(Submission.id.desc()))


# Card states ------------------------------------------------------------------------------------------------------

PHOTO_ROWS = [task("photo1", "Селфи у входа", method="Фото", points=15), *catalog(20)]


def test_a_sent_photo_shows_on_review_with_the_points_already_counted(client, admin, guest, clock):
    t = load(client, admin, PHOTO_ROWS)
    clock("09:30")
    base = totals(client, guest)
    assert card(client, guest, t["photo1"])["state"] == "available"
    assert send_photo(client, guest, t["photo1"]).json()["task"]["state"] == "review"
    assert totals(client, guest) == (base[0] + 15, base[1] + 15)
    assert card(client, guest, t["photo1"])["state"] == "review"
    assert get(client, guest)["tasks"][0]["state"] == "review"


def test_accept_shows_done(client, admin, guest, clock):
    t = load(client, admin, PHOTO_ROWS)
    clock("09:30")
    send_photo(client, guest, t["photo1"])
    assert decide(client, moderator_headers(client), submission(t["photo1"]).id, "accept").status_code == 200
    assert card(client, guest, t["photo1"])["state"] == "done"
    # Decided, it leaves the feed like any done card
    assert "Селфи у входа" not in shown(get(client, guest))


def test_bonus_shows_done_and_retake_shows_available_pinned_with_the_warning(client, admin, guest, clock):
    rows = PHOTO_ROWS + [task("photo2", "Фото со сцены", method="Фото")]
    t = load(client, admin, rows)
    clock("09:30")
    send_photo(client, guest, t["photo1"])
    send_photo(client, guest, t["photo2"])
    mod = moderator_headers(client)
    decide(client, mod, submission(t["photo1"]).id, "bonus")
    decide(client, mod, submission(t["photo2"]).id, "retake")
    assert card(client, guest, t["photo1"])["state"] == "done"
    retake = card(client, guest, t["photo2"])
    assert (retake["state"], retake["review"]) == ("available", "retake")
    f = get(client, guest)
    # Pinned above the batch, outside its 15
    assert shown(f)[0] == "Фото со сцены" and len(f["tasks"]) == 16


def test_a_penalty_shows_the_warning_and_leaves_the_feed(client, admin, guest, clock):
    t = load(client, admin, PHOTO_ROWS)
    clock("09:30")
    send_photo(client, guest, t["photo1"])
    decide(client, moderator_headers(client), submission(t["photo1"]).id, "penalty")
    c = card(client, guest, t["photo1"])
    assert (c["state"], c["review"]) == ("done", "penalty")
    assert "Селфи у входа" not in shown(get(client, guest))


def test_an_undecided_photo_shows_done_once_its_stage_ends_and_stays_in_the_queue(client, admin, guest, clock):
    t = load(client, admin, PHOTO_ROWS)
    clock("09:30")
    send_photo(client, guest, t["photo1"])
    clock("10:31")
    assert card(client, guest, t["photo1"])["state"] == "done"
    mod = moderator_headers(client)
    assert [i["task"] for i in queue(client, mod)["items"]] == ["Селфи у входа"]
    # The «Топ-20» check before the ceremony still finds it
    assert [i["task"] for i in queue(client, mod, top20=True)["items"]] == ["Селфи у входа"]


def test_an_undecided_photo_is_pinned_above_a_full_batch(client, admin, guest, clock):
    t = load(client, admin, PHOTO_ROWS)
    clock("09:30")
    send_photo(client, guest, t["photo1"])
    f = nxt(client, guest)
    assert f["tasks"][0]["state"] == "review" and shown(f)[0] == "Селфи у входа"
    assert len(f["tasks"]) == 16 and nums(f) == list(range(1, 16))


# Limits -----------------------------------------------------------------------------------------------------------

def guests(client, n) -> list[dict]:
    return [make_guest(client, f"R-{i}", f"Гость {i}") for i in range(n)]


def test_fifty_guests_claiming_a_task_with_ten_places_at_once_ten_get_it(client, admin, clock):
    t = load(client, admin, [task("photo1", "Селфи у входа", method="Фото", limit=10)])
    clock("09:30")
    many = guests(client, 50)
    gate = Barrier(50)
    answers: list[str] = []

    def go(h):
        gate.wait()
        answers.append(claim(TestClient(app), h, t["photo1"], new_id()).json()["result"])

    threads = [Thread(target=go, args=(h,)) for h in many]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert sorted(answers) == ["claimed"] * 10 + ["limit"] * 40
    with SessionLocal() as db:
        holders = set(db.scalars(select(Claim.guest_id).where(Claim.state == "open")))
    states = {card(client, h, t["photo1"])["state"] for h in many}
    assert states == {"available", "full"}
    late = make_guest(client, "R-late", "Опоздавший")
    assert card(client, late, t["photo1"])["state"] == "full"
    assert get(client, late)["tasks"][0]["state"] == "full"
    assert len(holders) == 10


def fill(client, admin, clock, n=2):
    """A photo task with n places, both taken by guests whose photos arrived; one more guest waiting."""
    t = load(client, admin, [task("photo1", "Селфи у входа", method="Фото", limit=n)])
    clock("09:30")
    first, second, third = guests(client, 3)
    assert send_photo(client, first, t["photo1"]).json()["result"] == "awarded"
    assert send_photo(client, second, t["photo1"]).json()["result"] == "awarded"
    assert card(client, third, t["photo1"])["state"] == "full"
    assert claim(client, third, t["photo1"], new_id()).json()["result"] == "limit"
    return t["photo1"], first, second, third


def test_a_penalty_frees_the_place(client, admin, clock):
    task_id, first, second, third = fill(client, admin, clock)
    decide(client, moderator_headers(client), submission_task_guest(task_id, 1).id, "penalty")
    assert card(client, third, task_id)["state"] == "available"
    assert claim(client, third, task_id, new_id()).json()["result"] == "claimed"


def test_a_retake_keeps_the_place_and_that_guest_can_send_again(client, admin, clock):
    task_id, first, second, third = fill(client, admin, clock)
    decide(client, moderator_headers(client), submission_task_guest(task_id, 1).id, "retake")
    assert card(client, third, task_id)["state"] == "full"
    assert claim(client, third, task_id, new_id()).json()["result"] == "limit"
    assert card(client, first, task_id)["state"] == "available"
    assert send_photo(client, first, task_id).json()["result"] == "awarded"


def submission_task_guest(task_id, guest_id) -> Submission:
    with SessionLocal() as db:
        return db.scalar(select(Submission).where(Submission.task_id == task_id, Submission.guest_id == guest_id))


def test_raising_the_limit_makes_a_full_task_available(client, admin, clock):
    task_id, first, second, third = fill(client, admin, clock)
    r = save(client, admin, "tasks", find(client, admin, "tasks", "code", "photo1"), limit=3)
    assert r.status_code == 200, r.text
    assert card(client, third, task_id)["state"] == "available"
    assert claim(client, third, task_id, new_id()).json()["result"] == "claimed"


def test_a_lapsed_claim_frees_its_place(client, admin, clock):
    t = load(client, admin, [task("photo1", "Селфи у входа", method="Фото", limit=1)])
    clock("09:30")
    first, second = guests(client, 2)
    assert claim(client, first, t["photo1"], "c1").json()["result"] == "claimed"
    assert card(client, second, t["photo1"])["state"] == "full"
    clock("10:29")
    with SessionLocal() as db:
        # The claim was made at 09:30; 60 minutes on it lapses
        db.execute(update(Claim).values(expires_at=stages.now() - timedelta(minutes=1)))
        db.commit()
    assert card(client, second, t["photo1"])["state"] == "available"
    assert claim(client, second, t["photo1"], "c2").json()["result"] == "claimed"


def test_scanning_a_full_qr_task_gets_nothing(client, admin, clock):
    t = load(client, admin, [task("qr1", "QR у стенда", limit=1)])
    clock("09:30")
    first, second = guests(client, 2)
    code = qr_codes(client, admin)["qr1"]
    assert scan(client, first, code).json()["result"] == "awarded"
    base = totals(client, second)
    r = scan(client, second, code)
    assert (r.status_code, r.json()["result"], r.json()["task"]["state"]) == (200, "limit", "full")
    assert totals(client, second) == base
    # The guest who did it still sees it done
    assert scan(client, first, code).json()["result"] == "already"


def test_a_full_link_task_and_a_full_quiz_refuse(client, admin, clock):
    rows = [[*task("link1", "Ссылка", method="Ссылка", limit=1)[:11], "https://tag.tj", None, None, 1],
            task("quiz1", "Квиз", method="Квиз", limit=1)]
    t = load(client, admin, rows, questions=[["quiz1", 1, "Вопрос", "А", "Б", None, None, 1]])
    clock("09:30")
    first, second = guests(client, 2)
    assert client.post(f"/api/tasks/{t['link1']}/complete", headers=first).json()["result"] == "awarded"
    assert client.post(f"/api/tasks/{t['link1']}/complete", headers=second).json()["result"] == "limit"
    # A quiz takes its place at «Начать»
    assert client.post(f"/api/quiz/{t['quiz1']}/start", headers=first).status_code == 200
    r = client.post(f"/api/quiz/{t['quiz1']}/start", headers=second)
    assert (r.status_code, r.json()["detail"]) == (409, "limit")
    assert client.post(f"/api/quiz/{t['quiz1']}/start", headers=first).status_code == 200


# Rotation ---------------------------------------------------------------------------------------------------------

def test_forty_tasks_rotate_fifteen_at_a_time(client, admin, guest, clock):
    load(client, admin, catalog(40))
    clock("09:30")
    assert nums(nxt(client, guest)) == list(range(1, 16))
    assert nums(nxt(client, guest)) == list(range(16, 31))
    assert nums(nxt(client, guest)) == list(range(31, 41)) + list(range(1, 6))


def test_an_open_time_window_always_shows_first_and_counts_toward_b(client, admin, guest, clock):
    window = task("quiz", "Квиз с окном", start="13.12.2026 09:00", end="13.12.2026 10:00")
    load(client, admin, [window, *catalog(40)])
    clock("09:30")
    for expected in (list(range(1, 15)), list(range(15, 29)), list(range(29, 41)) + list(range(1, 3))):
        f = nxt(client, guest)
        assert shown(f)[0] == "Квиз с окном" and nums(f) == expected and len(f["tasks"]) == 15
    # Closed, it leaves; the rotation fills the batch again
    clock("10:05")
    assert nums(nxt(client, guest)) == list(range(3, 18))


def test_open_windows_alone_fill_the_batch(client, admin, guest, clock):
    windows = [task(f"W{i}", f"Окно {i}", start="13.12.2026 09:00", end="13.12.2026 10:00") for i in range(6)]
    load(client, admin, [*windows, *catalog(10)], batch=5)
    clock("09:30")
    f = nxt(client, guest)
    assert len(f["tasks"]) == 5 and nums(f) == []


def test_the_rotation_continues_after_closing_and_reopening_the_app(client, admin, guest, clock):
    load(client, admin, catalog(40))
    clock("09:30")
    nxt(client, guest)
    nxt(client, guest)
    # A new phone session: nothing on the phone, the place is kept on the server
    assert nums(nxt(TestClient(app), guest)) == list(range(31, 41)) + list(range(1, 6))


def test_polls_and_returning_from_a_task_keep_the_batch(client, admin, guest, clock):
    t = load(client, admin, catalog(40))
    clock("09:30")
    nxt(client, guest)
    second = nxt(client, guest)
    assert nums(get(client, guest)) == nums(second) == list(range(16, 31))
    card(client, guest, t["T20"])
    assert nums(get(client, guest)) == list(range(16, 31))
    # A card done in between drops out and the batch fills from the next one
    scan(client, guest, qr_codes(client, admin)["T20"])
    assert nums(get(client, guest)) == [n for n in range(16, 32) if n != 20]
    # 31 has been shown now: the next page load starts after it, not at it again
    assert nums(nxt(client, guest)) == [*range(32, 41), *range(1, 7)]


def test_a_done_task_leaves_the_rotation_and_the_batch_keeps_b_cards(client, admin, guest, clock):
    t = load(client, admin, catalog(40))
    clock("09:30")
    nxt(client, guest)
    scan(client, guest, qr_codes(client, admin)["T05"])
    f = nxt(client, guest)
    assert len(f["tasks"]) == 15 and 5 not in nums(f)
    for _ in range(3):
        assert 5 not in nums(nxt(client, guest))
    assert card(client, guest, t["T05"])["state"] == "done"


def test_tasks_added_or_switched_off_dont_skip_or_repeat_others(client, admin, guest, clock):
    load(client, admin, catalog(40))
    clock("09:30")
    nxt(client, guest)
    # «Задание 15», the last one shown, is switched off; the next batch still starts at 16
    r = save(client, admin, "tasks", find(client, admin, "tasks", "code", "T15"), active=False, confirm=True)
    assert r.status_code == 200, r.text
    assert nums(nxt(client, guest)) == list(range(16, 31))


def test_full_cards_stay_in_the_rotation_with_their_label(client, admin, clock):
    load(client, admin, [task("T01", "Задание 1", limit=1), *catalog(40)[1:]], batch=5)
    clock("09:30")
    first, second = guests(client, 2)
    scan(client, first, qr_codes(client, admin)["T01"])
    f = nxt(client, second)
    assert nums(f) == [1, 2, 3, 4, 5] and f["tasks"][0]["state"] == "full"


# Settings ---------------------------------------------------------------------------------------------------------

def test_batch_size_outside_5_to_50_is_refused_naming_the_range(client, admin):
    load(client, admin, catalog(5))
    stage = find(client, admin, "stages", "number", 1)
    assert stage["values"]["batch_size"] == 15
    for bad in (4, 51):
        r = save(client, admin, "stages", stage, batch_size=bad)
        assert (r.status_code, r.json()["detail"]) == (400, {"code": "out_of_range", "field": "batch_size",
                                                              "min": 5, "max": 50})
    assert save(client, admin, "stages", stage, batch_size=5, confirm=True).status_code == 200
    # The file refuses it too, naming the range
    r = upload(client, admin, xlsx(catalog(5), batch=51))
    assert r.json()["failed"][0] | {"row": 0} == {"sheet": "Этапы", "row": 0, "reason": "bad_batch_size", "min": 5,
                                                  "max": 50}


def test_a_new_stage_from_the_form_gets_fifteen_cards(client, admin):
    r = client.post("/api/admin/lists/stages?confirm=true", json={"values": {
        "number": 1, "name": "Начало", "starts_at": "2026-12-13T09:00", "ends_at": "2026-12-13T10:30",
        "batch_size": None}}, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["values"]["batch_size"] == 15


def test_limit_and_batch_size_round_trip_through_the_file(client, admin):
    load(client, admin, [task("qr1", "QR у стенда", limit=7), task("qr2", "Без лимита")], batch=20)
    wb = load_workbook(io.BytesIO(client.get("/api/admin/tasks/export", headers=admin).content))
    stages_sheet = list(wb["Этапы"].iter_rows(values_only=True))
    col = stages_sheet[0].index("Карточек в ленте")
    assert {r[col] for r in stages_sheet[1:]} == {20}
    tasks_sheet = list(wb["Задания"].iter_rows(values_only=True))
    assert tasks_sheet[0][-1] == "Лимит"
    assert {r[0]: r[-1] for r in tasks_sheet[1:]} == {"qr1": 7, "qr2": None}
    # An older file without the columns leaves both as they are
    r = upload(client, admin, xlsx_without_new_columns())
    assert r.status_code == 200 and r.json()["failed"] == []
    with SessionLocal() as db:
        assert db.scalar(select(Task.limit).where(Task.code == "qr1")) == 7
    assert find(client, admin, "stages", "number", 1)["values"]["batch_size"] == 20


def xlsx_without_new_columns() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Этапы"
    ws.append(STAGE_HEAD)
    for r in STAGES:
        ws.append(r)
    wt = wb.create_sheet("Задания")
    wt.append(HEAD)
    for r in (task("qr1", "QR у стенда"), task("qr2", "Без лимита")):
        wt.append(r[:len(HEAD)])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
