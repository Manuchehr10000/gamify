from datetime import timedelta
from threading import Barrier, Thread

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import Claim, JobRun, ScoreEvent, Stage, Submission
from app.photos import jpeg_size, strip_metadata
from tests.conftest import moderator_headers
from tests.test_market import make_guest
from tests.test_qr_tasks import load, row, totals
from tests.test_submissions import ROWS, claim, ids, jpeg, send_files, send_photo, submissions
from tests.test_tasks import DUSHANBE, admin, clock, guest  # noqa: F401 (fixtures)

CLAIM_ROWS = ROWS + [row("window", 1, "Фото до 09:40", method="Фото", end="13.12.2026 09:40")]


def setup(client, admin, clock):
    load(client, admin, CLAIM_ROWS)
    clock("09:30")
    return ids(client, admin)


def claims() -> list[Claim]:
    with SessionLocal() as db:
        return list(db.scalars(select(Claim).order_by(Claim.created_at)))


def awards() -> list[ScoreEvent]:
    with SessionLocal() as db:
        return list(db.scalars(select(ScoreEvent).where(ScoreEvent.action == "task")))


def stage_id(number: int) -> int:
    with SessionLocal() as db:
        return db.scalar(select(Stage.id).where(Stage.number == number))


def with_gps(width=1200, height=1600) -> bytes:
    """A phone camera's JPEG: Exif in APP1 with GPS, XMP in another APP1, then the JFIF image."""
    exif = b"Exif\x00\x00GPSLatitude 38.5598 GPSLongitude 68.7870"
    app1 = b"\xff\xe1" + (len(exif) + 2).to_bytes(2, "big") + exif
    xmp = b"http://ns.adobe.com/xap/1.0/\x00<GPS/>"
    app1b = b"\xff\xe1" + (len(xmp) + 2).to_bytes(2, "big") + xmp
    data = jpeg(width, height)
    return data[:2] + app1 + app1b + data[2:]


def test_closing_mid_upload_then_reopening_pays_once(client, admin, guest, clock):
    t = setup(client, admin, clock)
    base = totals(client, guest)
    assert claim(client, guest, t["photo1"], "s1").json()["result"] == "claimed"
    # Nothing counts while only the claim is in
    assert totals(client, guest) == base
    assert client.get(f"/api/tasks/{t['photo1']}", headers=guest).json()["done"] is False
    # The app was closed while the files went out, and the server got them; on reopening the phone sends both again
    assert send_files(client, guest, "s1").json()["result"] == "awarded"
    assert claim(client, guest, t["photo1"], "s1").json()["result"] == "awarded"
    assert send_files(client, guest, "s1").json()["result"] == "awarded"
    assert totals(client, guest) == (base[0] + 15, base[1] + 15)
    assert len(submissions()) == 1 and len(awards()) == 1
    assert [c.state for c in claims()] == ["done"]


def test_the_same_upload_arriving_twice_at_once_pays_once(client, admin, guest, clock):
    t = setup(client, admin, clock)
    base = totals(client, guest)
    claim(client, guest, t["photo1"], "s1")
    gate = Barrier(2)
    answers = []

    def upload():
        gate.wait()
        answers.append(send_files(TestClient(app), guest, "s1").json()["result"])

    threads = [Thread(target=upload) for _ in range(2)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert answers == ["awarded", "awarded"]
    assert totals(client, guest) == (base[0] + 15, base[1] + 15)
    assert len(submissions()) == 1


def test_a_claim_sent_later_counts_at_the_later_server_time(client, admin, guest, clock):
    setup(client, admin, clock)
    # Airplane mode: the phone keeps it; the claim reaches the server at 10:35, in stage 2
    load(client, admin, CLAIM_ROWS + [row("photo2", 2, "Фото этапа 2", method="Фото")])
    t = ids(client, admin)
    clock("10:35")
    assert claim(client, guest, t["photo2"], "late").json()["result"] == "claimed"
    [c] = claims()
    assert c.created_at.astimezone(DUSHANBE).strftime("%H:%M") == "10:35"
    assert c.stage_id == stage_id(2)
    assert c.expires_at - c.created_at == timedelta(minutes=60)
    send_files(client, guest, "late")
    assert [e.stage_id for e in awards()] == [stage_id(2)]


def test_a_claim_after_the_stage_ended_gets_nothing(client, admin, guest, clock):
    t = setup(client, admin, clock)
    base = totals(client, guest)
    clock("10:31")
    r = claim(client, guest, t["photo1"], "s1")
    assert (r.status_code, r.json()["result"], r.json()["task"]["done"]) == (200, "stage_closed", False)
    # A window that has closed is «Время вышло»
    clock("09:45")
    assert claim(client, guest, t["window"], "s2").json()["result"] == "time_up"
    assert totals(client, guest) == base
    assert claims() == [] and submissions() == []


def test_files_after_the_stage_ended_count_for_the_claims_stage(client, admin, guest, clock):
    t = setup(client, admin, clock)
    base = totals(client, guest)
    clock("10:00")
    claim(client, guest, t["photo1"], "s1")
    # Stage 2 runs by the time the photo arrives, within the claim's 60 minutes
    clock("10:50")
    assert send_files(client, guest, "s1").json()["result"] == "awarded"
    assert totals(client, guest) == (base[0] + 15, base[1] + 15)
    assert [e.stage_id for e in awards()] == [stage_id(1)]


def test_a_claim_whose_stage_was_deleted_is_not_paid_to_the_stage_running_now(client, admin, guest, clock):
    t = setup(client, admin, clock)
    clock("10:00")
    claim(client, guest, t["photo1"], "s1")
    # Its stage was deleted since (the claim's stage goes empty); the photo arrives during stage 2
    with SessionLocal() as db:
        db.get(Claim, "s1").stage_id = None
        db.commit()
    clock("10:50")
    assert send_files(client, guest, "s1").json()["result"] == "awarded"
    assert [e.stage_id for e in awards()] == [None]


def test_a_lapsed_claim_pays_nothing_and_its_files_are_refused(client, admin, guest, clock):
    t = setup(client, admin, clock)
    base = totals(client, guest)
    claim(client, guest, t["photo1"], "s1")
    # No job has run yet: the claim is read as lapsed all the same
    clock("10:31")
    r = send_files(client, guest, "s1")
    assert (r.status_code, r.json()["detail"]) == (410, "claim_lapsed")
    assert (claim(client, guest, t["photo1"], "s1").status_code) == 410
    assert totals(client, guest) == base
    assert submissions() == [] and awards() == []
    assert [c.state for c in claims()] == ["lapsed"]


def test_the_job_run_marks_a_claim_past_its_time_lapsed(client, admin, guest, clock):
    t = setup(client, admin, clock)
    claim(client, guest, t["photo1"], "s1")
    clock("10:00")
    claim(client, guest, t["both1"], "s2", "Стих")
    clock("10:31")
    r = client.post("/api/jobs/run", headers={"X-Jobs-Secret": "jobs-secret"})
    assert r.status_code == 200
    assert [(x["job"], x["result"], x["detail"]) for x in r.json()] == [("lapsed_claims", "ok", "истекло заявок: 1")]
    assert {c.id: c.state for c in claims()} == {"s1": "lapsed", "s2": "open"}
    # The next run finds nothing more to lapse, and the log says so
    client.post("/api/jobs/run", headers={"X-Jobs-Secret": "jobs-secret"})
    with SessionLocal() as db:
        assert [(j.job, j.result, j.detail) for j in db.scalars(select(JobRun).order_by(JobRun.id))] == [
            ("lapsed_claims", "ok", "истекло заявок: 1"), ("lapsed_claims", "ok", "истекло заявок: 0")]
    # The lapse freed the place: a new send of the same task counts
    assert send_photo(client, guest, t["photo1"]).json()["result"] == "stage_closed"
    clock("10:29")
    assert send_photo(client, guest, t["photo1"]).json()["result"] == "awarded"


def test_an_open_claim_from_another_phone_holds_the_place(client, admin, guest, clock):
    t = setup(client, admin, clock)
    claim(client, guest, t["photo1"], "phone-a")
    r = claim(client, guest, t["photo1"], "phone-b")
    assert (r.status_code, r.json()["detail"]) == (409, "claim_open")
    assert send_files(client, guest, "phone-a").json()["result"] == "awarded"
    assert claim(client, guest, t["photo1"], "phone-b").json()["result"] == "already"


def test_claim_time_limit_is_the_admins_setting(client, admin, guest, clock):
    t = setup(client, admin, clock)
    s = next(s for s in client.get("/api/admin/settings", headers=admin).json() if s["key"] == "claim_minutes")
    assert (s["value"], s["min"], s["max"]) == (60, 10, 240)
    r = client.put("/api/admin/settings/claim_minutes", json={"value": 9, "version": s["version"]}, headers=admin)
    assert r.status_code == 400
    r = client.put("/api/admin/settings/claim_minutes", json={"value": 10, "version": s["version"]}, headers=admin)
    assert r.status_code == 200, r.text
    claim(client, guest, t["photo1"], "s1")
    clock("09:41")
    assert send_files(client, guest, "s1").status_code == 410


def test_queue_size_per_phone_is_the_admins_setting(client, admin, guest, clock):
    setup(client, admin, clock)
    assert client.get("/api/feed", headers=guest).json()["queue_size"] == 5
    s = next(s for s in client.get("/api/admin/settings", headers=admin).json() if s["key"] == "upload_queue_size")
    assert (s["min"], s["max"]) == (1, 10)
    assert client.put("/api/admin/settings/upload_queue_size", json={"value": 11, "version": s["version"]},
                      headers=admin).status_code == 400
    client.put("/api/admin/settings/upload_queue_size", json={"value": 3, "version": s["version"]}, headers=admin)
    assert client.get("/api/feed", headers=guest).json()["queue_size"] == 3


def test_another_guests_claim_is_unknown(client, admin, guest, clock):
    t = setup(client, admin, clock)
    claim(client, guest, t["photo1"], "s1")
    other = make_guest(client, "R-2", "Анна")
    assert send_files(client, other, "s1").status_code == 404
    assert claim(client, other, t["photo1"], "s1").status_code == 409
    assert submissions() == []


def test_the_stored_photo_has_no_gps(client, admin, guest, clock):
    t = setup(client, admin, clock)
    data = with_gps()
    assert b"GPS" in data
    assert send_photo(client, guest, t["photo1"], data, thumb=with_gps(300, 400)).json()["result"] == "awarded"
    with SessionLocal() as db:
        s = db.scalars(select(Submission)).one()
        for stored in (s.photo, s.thumb):
            assert b"GPS" not in stored and b"Exif" not in stored
        # Still the same JPEG: JFIF header and frame kept
        assert b"JFIF" in s.photo and jpeg_size(s.photo) == (1200, 1600)
        assert jpeg_size(s.thumb) == (300, 400)


def test_strip_metadata_keeps_the_image_data():
    plain = jpeg(10, 20)
    assert strip_metadata(plain) == plain
    sos = b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00" + b"\xe1\xff\x00\x12" + b"\xff\xd9"
    data = with_gps(10, 20)[:-2] + sos
    out = strip_metadata(data)
    # Everything from the image data on is kept as it is, even bytes that look like an APP1 marker
    assert out.endswith(sos) and b"Exif" not in out
    assert jpeg_size(out) == (10, 20)


def test_moderators_list_gets_the_thumbnail_and_the_full_photo_on_request(client, admin, guest, clock):
    t = setup(client, admin, clock)
    photo, thumb = jpeg(pad=300), jpeg(300, 400, pad=10)
    send_photo(client, guest, t["photo1"], photo, thumb=thumb)
    with SessionLocal() as db:
        sid = db.scalar(select(Submission.id))
    mod = moderator_headers(client)
    r = client.get(f"/api/submissions/{sid}/photo", params={"thumb": 1}, headers=mod)
    assert (r.status_code, r.content, r.headers["content-type"]) == (200, thumb, "image/jpeg")
    assert client.get(f"/api/submissions/{sid}/photo", headers=mod).content == photo
    # A photo sent before thumbnails existed: the list shows the photo itself
    with SessionLocal() as db:
        db.get(Submission, sid).thumb = None
        db.commit()
    assert client.get(f"/api/submissions/{sid}/photo", params={"thumb": 1}, headers=mod).content == photo


def test_a_claim_past_its_time_frees_the_place_before_the_job_runs(client, admin, guest, clock):
    t = setup(client, admin, clock)
    s = next(s for s in client.get("/api/admin/settings", headers=admin).json() if s["key"] == "claim_minutes")
    client.put("/api/admin/settings/claim_minutes", json={"value": 10, "version": s["version"]}, headers=admin)
    claim(client, guest, t["photo1"], "s1")
    clock("09:41")
    assert claim(client, guest, t["photo1"], "s2").json()["result"] == "claimed"
    assert {c.id: c.state for c in claims()} == {"s1": "lapsed", "s2": "open"}
    assert send_files(client, guest, "s2").json()["result"] == "awarded"
