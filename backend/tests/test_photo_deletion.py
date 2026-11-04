import os
from datetime import datetime

from sqlalchemy import select, text

from app import photos, stages
from app.db import SessionLocal, engine
from app.models import JobRun, ScoreEvent, Stage, Submission
from tests.conftest import moderator_headers
from tests.test_feed_rotation import card, fill, nxt
from tests.test_live import TASKS, live, partner
from tests.test_market import load as load_market, make_guest
from tests.test_moderation import decide, queue
from tests.test_partner_report import open_photo, photo_links, report, set_date, submission_ids, task_rows
from tests.test_qr_tasks import totals
from tests.test_submissions import ids, jpeg, send_photo, send_text
from tests.test_tasks import DUSHANBE, admin, clock  # noqa: F401 (fixtures)

JOBS = {"X-Jobs-Secret": "jobs-secret"}


def setup(client, admin, clock) -> dict[str, int]:
    load_market(client, admin, tasks=TASKS)
    clock("09:30")
    return ids(client, admin)


def delete(client, guest, submission_id):
    return client.delete(f"/api/submissions/{submission_id}/photo", headers=guest)


def at(monkeypatch, *ymd_hm):
    """The server clock at a forum-local moment after the forum."""
    t = datetime(*ymd_hm, tzinfo=DUSHANBE)
    monkeypatch.setattr(stages, "now", lambda: t)


def stored(submission_id) -> tuple[bool, bool, str]:
    """(photo kept, thumbnail kept, status)."""
    with SessionLocal() as db:
        s = db.get(Submission, submission_id)
        return s.photo is not None, s.thumb is not None, s.status


def kept() -> int:
    with SessionLocal() as db:
        return photos.remaining(db)


def big_jpeg() -> bytes:
    """A photo near the size cap that doesn't compress, so the table really holds its bytes."""
    return jpeg()[:-2] + b"\x00" + os.urandom(900 * 1024) + b"\xff\xd9"


def run_jobs(client) -> dict:
    r = client.post("/api/jobs/run", headers=JOBS)
    assert r.status_code == 200, r.text
    return next(j for j in r.json() if j["job"] == photos.JOB)


def test_deleting_an_accepted_photo_keeps_the_points(client, admin, clock):
    t = setup(client, admin, clock)
    ivan = make_guest(client, "R-1", "Иван")
    send_photo(client, ivan, t["selfie"])
    [sid] = submission_ids()
    mod = moderator_headers(client)
    assert decide(client, mod, sid, "accept").json()["result"] == "decided"
    before = totals(client, ivan)
    task = client.get(f"/api/tasks/{t['selfie']}", headers=ivan).json()
    assert (task["photo_id"], task["photo_undecided"]) == (sid, False)
    r = delete(client, ivan, sid)
    assert (r.status_code, r.json()["result"]) == (200, "deleted")
    assert stored(sid) == (False, False, "accepted")
    assert totals(client, ivan) == before
    assert client.get(f"/api/submissions/{sid}/photo", headers=mod).status_code == 404
    task = r.json()["task"]
    assert (task["photo_id"], task["review"], task["state"]) == (None, "", "done")
    # Gone already: nothing more to delete
    assert delete(client, ivan, sid).status_code == 404


def test_deleting_an_undecided_photo_withdraws_it_and_frees_its_place(client, admin, clock):
    task_id, first, second, third = fill(client, admin, clock)
    sid = submission_ids()[0]
    before = totals(client, first)
    task = card(client, first, task_id)
    assert (task["photo_id"], task["photo_undecided"], task["state"]) == (sid, True, "review")
    r = delete(client, first, sid)
    assert (r.status_code, r.json()["result"]) == (200, "withdrawn")
    assert stored(sid) == (False, False, "withdrawn")
    # Points and coins back, as a take-back row like a penalty's
    assert totals(client, first) == (before[0] - 10, before[1] - 10)
    with SessionLocal() as db:
        row = db.scalar(select(ScoreEvent).where(ScoreEvent.reason == f"withdraw:{sid}"))
        assert (row.action, row.points, row.coins, row.reverses_id) == ("withdraw", -10, -10, None)
    # The place frees for the guest who was waiting
    assert card(client, third, task_id)["state"] == "available"
    # Out of the moderator's queue; the task stays closed for the guest, and can't be sent again
    assert [i["id"] for i in queue(client, moderator_headers(client))["items"]] == [submission_ids()[1]]
    task = card(client, first, task_id)
    assert (task["state"], task["review"], task["done"], task["photo_id"]) == ("done", "withdrawn", True, None)
    assert send_photo(client, first, task_id).json()["result"] == "already"


def test_a_withdrawn_card_leaves_the_batch_and_does_not_come_back(client, admin, clock):
    task_id, first, _, _ = fill(client, admin, clock)
    # Undecided: pinned above the batch, «На проверке»
    assert [(x["id"], x["state"]) for x in nxt(client, first)["tasks"]] == [(task_id, "review")]
    assert delete(client, first, submission_ids()[0]).json()["result"] == "withdrawn"
    for _ in range(3):
        assert task_id not in [x["id"] for x in nxt(client, first)["tasks"]]
        assert task_id not in [x["id"] for x in client.get("/api/feed", headers=first).json()["tasks"]]


def test_deleting_a_rejected_photo_changes_nothing_else(client, admin, clock):
    t = setup(client, admin, clock)
    ivan, anna = make_guest(client, "R-1", "Иван"), make_guest(client, "R-2", "Анна")
    send_photo(client, ivan, t["selfie"])
    send_photo(client, anna, t["selfie"])
    penalized, retaken = submission_ids()
    mod = moderator_headers(client)
    decide(client, mod, penalized, "penalty")
    decide(client, mod, retaken, "retake")
    before = totals(client, ivan), totals(client, anna)
    events = client.get("/api/admin/balance-check", headers=admin).json()
    assert delete(client, ivan, penalized).json()["result"] == "deleted"
    assert delete(client, anna, retaken).json()["result"] == "deleted"
    assert (totals(client, ivan), totals(client, anna)) == before
    assert (stored(penalized), stored(retaken)) == ((False, False, "penalty"), (False, False, "retake"))
    with SessionLocal() as db:
        assert not db.scalar(select(ScoreEvent).where(ScoreEvent.action == "withdraw"))
    assert client.get("/api/admin/balance-check", headers=admin).json() == events == []
    # The one sent back may still be sent again
    assert send_photo(client, anna, t["selfie"]).json()["result"] == "awarded"


def test_only_the_guests_own_photo_and_not_a_text(client, admin, clock):
    t = setup(client, admin, clock)
    ivan, anna = make_guest(client, "R-1", "Иван"), make_guest(client, "R-2", "Анна")
    send_photo(client, ivan, t["selfie"])
    send_text(client, ivan, t["text"], "Хорошо")
    photo, written = submission_ids()
    assert delete(client, anna, photo).status_code == 404
    assert delete(client, ivan, written).status_code == 404
    assert client.delete(f"/api/submissions/{photo}/photo").status_code == 401
    assert stored(photo) == (True, True, "")


def test_a_decision_made_while_confirming_decides_what_the_delete_does(client, admin, clock):
    t = setup(client, admin, clock)
    ivan = make_guest(client, "R-1", "Иван")
    send_photo(client, ivan, t["selfie"])
    [sid] = submission_ids()
    # The guest's page still says undecided; the moderator accepts first
    assert card(client, ivan, t["selfie"])["photo_undecided"] is True
    before = totals(client, ivan)
    decide(client, moderator_headers(client), sid, "accept")
    assert delete(client, ivan, sid).json()["result"] == "deleted"
    assert totals(client, ivan) == before
    assert stored(sid) == (False, False, "accepted")


def test_the_profile_offers_the_delete_and_shows_the_withdrawal(client, admin, clock):
    t = setup(client, admin, clock)
    ivan = make_guest(client, "R-1", "Иван")
    send_photo(client, ivan, t["selfie"])
    send_text(client, ivan, t["text"], "Хорошо")
    [sid, _] = submission_ids()
    history = {e["text"]: e for e in client.get("/api/profile", headers=ivan).json()["history"]}
    assert (history["Селфи у входа"]["photo_id"], history["Селфи у входа"]["photo_undecided"]) == (sid, True)
    assert history["Напишите отзыв"]["photo_id"] is None
    delete(client, ivan, sid)
    entry = next(e for e in client.get("/api/profile", headers=ivan).json()["history"] if e["text"] == "Селфи у входа")
    assert (entry["withdrawn"], entry["rejected"], entry["photo_id"]) == (True, False, None)


def test_a_withdrawal_leaves_live_and_the_partner_file_and_they_still_match(client, admin, clock):
    t = setup(client, admin, clock)
    ivan, anna = make_guest(client, "R-1", "Иван"), make_guest(client, "R-2", "Анна")
    send_photo(client, ivan, t["cola"])
    send_photo(client, anna, t["cola"])
    assert partner(live(client, admin), "Кока-Кола")["completions"] == 2
    delete(client, ivan, submission_ids()[0])
    page = partner(live(client, admin), "Кока-Кола")
    rows = task_rows(report(client, admin))
    assert (page["completions"], page["guests"]) == (1, 1)
    # Not counted as rejected either
    assert rows["Фото с бутылкой"][1:] == [1, 1, 0]
    assert (rows["Итого"][1], rows["Итого"][2]) == (page["completions"], page["guests"])


def test_admins_see_the_count_from_seven_days_before(client, admin, clock, monkeypatch):
    t = setup(client, admin, clock)
    for n in range(3):
        send_photo(client, make_guest(client, f"R-{n}", f"Гость {n}"), t["selfie"])
    send_text(client, make_guest(client, "R-9", "Олег"), t["text"], "Хорошо")
    guest = make_guest(client, "R-10", "Анна")
    assert client.get("/api/admin/photo-deletion", headers=guest).status_code == 401
    # Default: the last stage ends 13.12.2026 → deleted 12.01.2027; the banner from 05.01.2027
    at(monkeypatch, 2027, 1, 4, 23, 59)
    r = client.get("/api/admin/photo-deletion", headers=admin)
    assert r.json() == {"date": "2027-01-12", "count": 3, "locked": False}
    at(monkeypatch, 2027, 1, 5, 0, 0)
    assert client.get("/api/admin/photo-deletion", headers=admin).json() == {
        "date": "2027-01-12", "count": 3, "locked": True}
    # A guest's own deletion lowers the live count
    first = make_guest(client, "R-0", "Гость 0")
    delete(client, first, submission_ids()[0])
    assert client.get("/api/admin/photo-deletion", headers=admin).json()["count"] == 2


def test_the_date_is_locked_once_the_banner_shows(client, admin, monkeypatch):
    at(monkeypatch, 2027, 1, 1, 12, 0)
    assert set_date(client, admin, "2027-01-20").status_code == 200
    at(monkeypatch, 2027, 1, 13, 0, 0)
    r = set_date(client, admin, "2027-03-01")
    assert (r.status_code, r.json()["detail"]["code"]) == (409, "photo_date_locked")
    assert client.get("/api/admin/photo-deletion", headers=admin).json()["date"] == "2027-01-20"


def test_a_date_must_leave_the_seven_days_warning(client, admin, clock, monkeypatch):
    setup(client, admin, clock)
    at(monkeypatch, 2027, 1, 1, 12, 0)
    for day in ("2026-12-20", "2027-01-01", "2027-01-07"):
        r = set_date(client, admin, day)
        assert (r.status_code, r.json()["detail"]["code"]) == (409, "photo_date_too_soon"), day
    # Blank falls back to the stages' default (12.01.2027): fine on 01.01, too soon once it is 6 days away
    assert set_date(client, admin, "").status_code == 200
    assert set_date(client, admin, "2027-03-01").status_code == 200
    at(monkeypatch, 2027, 1, 6, 12, 0)
    r = set_date(client, admin, "")
    assert (r.status_code, r.json()["detail"]["code"]) == (409, "photo_date_too_soon")
    # Exactly 7 days away is fine, and from then on the date is locked
    assert set_date(client, admin, "2027-01-13").status_code == 200
    assert client.get("/api/admin/photo-deletion", headers=admin).json() == {
        "date": "2027-01-13", "count": 0, "locked": True}


def test_a_stage_change_after_the_banner_does_not_move_the_date(client, admin, clock, monkeypatch):
    setup(client, admin, clock)
    at(monkeypatch, 2027, 1, 5, 0, 1)
    run_jobs(client)
    with SessionLocal() as db:
        last = db.scalar(select(Stage).order_by(Stage.ends_at.desc()).limit(1))
        last.ends_at = datetime(2027, 1, 1, 18, 0, tzinfo=DUSHANBE)
        db.commit()
    assert client.get("/api/admin/photo-deletion", headers=admin).json() == {
        "date": "2027-01-12", "count": 0, "locked": True}


def size() -> tuple[int, int]:
    with engine.connect() as c:
        return (c.scalar(text("SELECT pg_total_relation_size('submissions')")),
                c.scalar(text("SELECT pg_database_size(current_database())")))


def test_the_job_deletes_every_photo_on_the_date_and_shrinks_the_database(client, admin, clock, monkeypatch):
    t = setup(client, admin, clock)
    for n in range(5):
        g = make_guest(client, f"R-{n}", f"Гость {n}")
        send_photo(client, g, t["cola"], data=big_jpeg())
    send_text(client, g, t["text"], "Хорошо")
    mod = moderator_headers(client)
    for sid in submission_ids()[:4]:
        decide(client, mod, sid, "accept")
    links = photo_links(report(client, admin))
    assert len(links) == 4
    # The day before: nothing is deleted (the date was kept as announced on the first run since the banner)
    at(monkeypatch, 2027, 1, 11, 23, 59)
    assert run_jobs(client)["detail"] == "дата удаления фото закреплена: 12.01.2027"
    assert run_jobs(client)["detail"] == ""
    assert kept() == 5
    before = size()
    at(monkeypatch, 2027, 1, 12, 3, 0)
    run = run_jobs(client)
    assert (run["result"], run["detail"]) == ("ok", "удалено фото в этом запуске: 5; сжатие — в следующем"), run
    # The next run, a minute later, compacts the table and writes the final entry: the count, start, the end of the
    # last batch, and the day Neon's restore history (7 days unless configured) lets go of them
    at(monkeypatch, 2027, 1, 12, 3, 1)
    run = run_jobs(client)
    assert run["detail"] == ("удалено фото: 5; начало 12.01.2027 03:00, конец 12.01.2027 03:00; "
                             "в истории восстановления Neon до 19.01.2027")
    with SessionLocal() as db:
        assert db.scalar(select(Submission.id).where(
            Submission.photo.is_not(None) | Submission.thumb.is_not(None))) is None
        # Submissions, texts and points stay
        assert len(db.scalars(select(Submission)).all()) == 6
        assert db.scalar(select(Submission.text).where(Submission.text != "")) == "Хорошо"
    after = size()
    assert after[0] < before[0] - 4 * 1024 * 1024
    assert after[1] < before[1] - 4 * 1024 * 1024
    # Every partner link and the moderator's view answer «not found»
    for link in links:
        assert open_photo(client, link).status_code == 404
    assert client.get(f"/api/submissions/{submission_ids()[0]}/photo", headers=mod).status_code == 404
    # The next runs find nothing and write no second final entry
    assert run_jobs(client)["detail"] == ""
    with SessionLocal() as db:
        assert db.scalar(select(text("count(*)")).select_from(JobRun).where(
            JobRun.job == photos.JOB, JobRun.detail.startswith(photos.DONE))) == 1


def test_a_stopped_job_is_finished_by_the_next_run(client, admin, clock, monkeypatch):
    t = setup(client, admin, clock)
    for n in range(3):
        send_photo(client, make_guest(client, f"R-{n}", f"Гость {n}"), t["selfie"])
    monkeypatch.setattr(photos, "BATCH", 1)

    class Down:
        def connect(self):
            raise RuntimeError("остановлен")
    at(monkeypatch, 2027, 1, 12, 3, 0)
    assert run_jobs(client)["detail"] == "удалено фото в этом запуске: 3; сжатие — в следующем"
    assert kept() == 0
    # Stopped at the compaction: the next run does it, and the final entry, once, with the last batch's end
    monkeypatch.setattr(photos, "engine", Down())
    at(monkeypatch, 2027, 1, 12, 3, 1)
    assert run_jobs(client)["result"] == "failed"
    monkeypatch.setattr(photos, "engine", engine)
    at(monkeypatch, 2027, 1, 12, 3, 2)
    run = run_jobs(client)
    assert run["detail"].startswith("удалено фото: 3; начало 12.01.2027 03:00, конец 12.01.2027 03:00")
    assert run_jobs(client)["detail"] == ""
