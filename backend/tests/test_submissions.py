import io

from openpyxl import load_workbook
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Submission, Task
from app.photos import jpeg_size
from tests.test_qr_tasks import HEAD, load, row, totals
from tests.test_tasks import admin, clock, guest  # noqa: F401 (fixtures)


def jpeg(width=1200, height=1600, pad=0) -> bytes:
    """A JPEG's header as a phone would send it: an APP0 segment, then the frame header with its size."""
    app0 = b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof = b"\xff\xc0\x00\x11\x08" + height.to_bytes(2, "big") + width.to_bytes(2, "big") + b"\x03" + b"\x00" * 9
    return b"\xff\xd8" + app0 + sof + b"\x00" * pad + b"\xff\xd9"


ROWS = [
    row("photo1", 1, "Селфи у входа", method="Фото"),
    row("text1", 1, "Напишите отзыв", points=10, method="Текст"),
    row("both1", 1, "Стих и фото", points=20, method="Фото+текст"),
    row("partner", 1, "Фото с чеком партнёра", method="Фото", partner="Coca-Cola", package="MF Партнёр"),
    row("photo3", 3, "Фото этапа 3", method="Фото"),
    row("qr1", 1, "QR у стенда", method="QR"),
]


def ids(client, admin) -> dict[str, int]:
    with SessionLocal() as db:
        return {t.code: t.id for t in db.scalars(select(Task))}


_ids = iter(range(1, 10**9))


def new_id() -> str:
    """A submission ID as the phone makes one."""
    return f"send-{next(_ids)}"


def claim(client, guest, task_id, claim_id, text=""):
    return client.post(f"/api/tasks/{task_id}/claim", json={"id": claim_id, "text": text}, headers=guest)


def send_files(client, guest, claim_id, data=None, thumb=None):
    files = {"photo": ("photo.jpg", data if data is not None else jpeg(), "image/jpeg"),
             "thumb": ("thumb.jpg", thumb if thumb is not None else jpeg(300, 400), "image/jpeg")}
    return client.post(f"/api/claims/{claim_id}/files", files=files, headers=guest)


def send_photo(client, guest, task_id, data=None, text=None, claim_id=None, thumb=None):
    """Both steps, as the phone sends them: the claim, then the files once the place is held."""
    claim_id = claim_id or new_id()
    r = claim(client, guest, task_id, claim_id, text or "")
    if r.status_code != 200 or r.json()["result"] != "claimed":
        return r
    return send_files(client, guest, claim_id, data, thumb)


def send_text(client, guest, task_id, text, claim_id=None):
    return claim(client, guest, task_id, claim_id or new_id(), text)


def submissions() -> list[Submission]:
    with SessionLocal() as db:
        return list(db.scalars(select(Submission)))


def test_photo_awards_points_and_coins_and_is_kept(client, admin, guest, clock):
    load(client, admin, ROWS)
    clock("09:30")
    base = totals(client, guest)
    r = send_photo(client, guest, ids(client, admin)["photo1"], jpeg(pad=500))
    assert r.status_code == 200, r.text
    assert (r.json()["result"], r.json()["task"]["done"]) == ("awarded", True)
    assert totals(client, guest) == (base[0] + 15, base[1] + 15)
    card = next(t for t in client.get("/api/feed", headers=guest).json()["tasks"] if t["text"] == "Селфи у входа")
    assert card["done"] is True
    with SessionLocal() as db:
        s = db.scalars(select(Submission)).one()
        assert jpeg_size(s.photo) == (1200, 1600)


def test_second_photo_and_a_retry_award_once(client, admin, guest, clock):
    load(client, admin, ROWS)
    clock("09:30")
    task_id = ids(client, admin)["photo1"]
    base = totals(client, guest)
    assert send_photo(client, guest, task_id, claim_id="one").json()["result"] == "awarded"
    # The phone timed out though the server got it, and sends the same claim and files again: the first result
    assert claim(client, guest, task_id, "one").json()["result"] == "awarded"
    assert send_files(client, guest, "one").json()["result"] == "awarded"
    # A second photo for the same task is a new send, and finds the task done
    assert send_photo(client, guest, task_id, jpeg(800, 600)).json()["result"] == "already"
    assert totals(client, guest) == (base[0] + 15, base[1] + 15)
    assert len(submissions()) == 1


def test_photo_must_be_a_shrunk_jpeg(client, admin, guest, clock):
    load(client, admin, ROWS)
    clock("09:30")
    task_id = ids(client, admin)["photo1"]
    assert claim(client, guest, task_id, "one").json()["result"] == "claimed"
    r = send_files(client, guest, "one", jpeg(4032, 3024))
    assert (r.status_code, r.json()["detail"]) == (400, "photo_too_large")
    r = send_files(client, guest, "one", b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    assert (r.status_code, r.json()["detail"]) == (400, "not_a_jpeg")
    # Up to 1 MB: a bigger photo was not redrawn
    r = send_files(client, guest, "one", jpeg(pad=1024 * 1024))
    assert (r.status_code, r.json()["detail"]) == (413, "photo_too_large")
    r = send_files(client, guest, "one", jpeg(pad=5 * 1024 * 1024))
    assert (r.status_code, r.json()["detail"]) == (413, "photo_too_large")
    # The thumbnail: a JPEG up to 400 px and 100 KB
    r = send_files(client, guest, "one", thumb=b"GIF89a" + b"\x00" * 100)
    assert (r.status_code, r.json()["detail"]) == (400, "not_a_jpeg")
    r = send_files(client, guest, "one", thumb=jpeg(1200, 1600))
    assert (r.status_code, r.json()["detail"]) == (400, "thumb_too_large")
    r = send_files(client, guest, "one", thumb=jpeg(300, 400, pad=100 * 1024))
    assert (r.status_code, r.json()["detail"]) == (413, "thumb_too_large")
    assert submissions() == []
    assert send_files(client, guest, "one", jpeg(1600, 1200)).json()["result"] == "awarded"


def test_text_up_to_500_characters(client, admin, guest, clock):
    load(client, admin, ROWS)
    clock("09:30")
    task_id = ids(client, admin)["text1"]
    r = send_text(client, guest, task_id, "я" * 501)
    assert (r.status_code, r.json()["detail"]) == (400, "text_too_long")
    r = send_text(client, guest, task_id, "   ")
    assert (r.status_code, r.json()["detail"]) == (400, "text_required")
    assert submissions() == []
    # A text-only task counts at the claim: there is no files step
    r = send_text(client, guest, task_id, "я" * 500)
    assert r.json()["result"] == "awarded"
    assert send_text(client, guest, task_id, "ещё раз").json()["result"] == "already"
    assert [s.text for s in submissions()] == ["я" * 500]


def test_photo_and_text_needs_both(client, admin, guest, clock):
    load(client, admin, ROWS)
    clock("09:30")
    task_id = ids(client, admin)["both1"]
    r = claim(client, guest, task_id, "one")
    assert (r.status_code, r.json()["detail"]) == (400, "text_required")
    r = claim(client, guest, task_id, "one", "я" * 501)
    assert (r.status_code, r.json()["detail"]) == (400, "text_too_long")
    # 500 characters on the guest's counter, line breaks included, though a form may send each as \r\n
    poem = "\r\n".join(["я" * 49] * 10) + "я"
    assert claim(client, guest, task_id, "one", poem).json()["result"] == "claimed"
    # The text rides in the claim; nothing counts until the photo comes
    assert submissions() == []
    r = send_files(client, guest, "one")
    assert (r.json()["result"], r.json()["task"]["points"]) == ("awarded", 20)


def test_endpoint_must_match_the_task(client, admin, guest, clock):
    load(client, admin, ROWS)
    clock("09:30")
    t = ids(client, admin)
    assert claim(client, guest, t["qr1"], "one").json()["detail"] == "wrong_method"
    assert claim(client, guest, 999999, "one").status_code == 404
    # A text task has no files step
    assert send_text(client, guest, t["text1"], "текст", claim_id="text").json()["result"] == "awarded"
    assert send_files(client, guest, "text").json()["detail"] == "wrong_method"
    assert send_files(client, guest, "nobody").status_code == 404
    assert client.post(f"/api/tasks/{t['photo1']}/complete", headers=guest).json()["detail"] == "not_a_link_task"
    # The ID becomes a path segment: letters, digits, - and _ only
    assert claim(client, guest, t["photo1"], "../x").status_code == 422
    # The old one-step endpoints are gone
    assert client.post(f"/api/tasks/{t['text1']}/text", json={"text": "x"}, headers=guest).status_code in (404, 405)


def test_partner_photo_gives_coins_by_the_rule(client, admin, guest, clock):
    load(client, admin, ROWS)
    clock("09:30")
    r = send_photo(client, guest, ids(client, admin)["partner"]).json()
    assert (r["result"], r["task"]["points"], r["task"]["coins"]) == ("awarded", 15, 23)


def test_photo_outside_its_stage_gets_nothing(client, admin, guest, clock):
    load(client, admin, ROWS)
    clock("09:30")
    base = totals(client, guest)
    r = send_photo(client, guest, ids(client, admin)["photo3"])
    assert (r.status_code, r.json()["result"], r.json()["task"]["done"]) == (200, "stage_closed", False)
    assert totals(client, guest) == base
    assert submissions() == []


def test_sending_needs_a_logged_in_guest(client, admin, clock):
    load(client, admin, ROWS)
    clock("09:30")
    t = ids(client, admin)
    assert send_photo(client, {}, t["photo1"]).status_code == 401
    assert send_text(client, {}, t["text1"], "текст").status_code == 401


def test_excel_takes_the_new_methods_and_gives_them_back(client, admin):
    result = load(client, admin, ROWS + [row("spaced", 2, "Фото и текст", method="фото + текст")])
    assert (result["added"], result["failed"]) == (7, [])
    r = client.get("/api/admin/tasks/export", headers=admin)
    sheet = load_workbook(io.BytesIO(r.content))["Задания"]
    head = [c.value for c in sheet[1]]
    method = {r[0]: r[head.index("Выполнение")] for r in sheet.iter_rows(min_row=2, values_only=True)}
    assert method == {"photo1": "Фото", "text1": "Текст", "both1": "Фото+текст", "partner": "Фото",
                      "photo3": "Фото", "qr1": "QR", "spaced": "Фото+текст"}
    # Uploading the downloaded file changes nothing
    again = client.post("/api/admin/tasks/import", files={"file": ("t.xlsx", r.content, "application/octet-stream")},
                        headers=admin).json()
    assert (again["added"], again["changed"], again["hidden"], again["failed"]) == (0, 0, 0, [])


def test_jpeg_size_reads_progressive_and_skips_fill_bytes():
    progressive = jpeg(1600, 900).replace(b"\xff\xc0", b"\xff\xc2", 1)
    assert jpeg_size(progressive) == (1600, 900)
    assert jpeg_size(b"\xff\xd8\xff\xff" + jpeg(10, 20)[2:]) == (10, 20)
    assert jpeg_size(b"\xff\xd8\xff\xda\x00\x02") is None
    assert jpeg_size(b"\xff\xd8") is None


def test_big_body_is_refused_before_it_is_read(client, admin, guest, clock):
    load(client, admin, ROWS)
    clock("09:30")
    task_id = ids(client, admin)["photo1"]
    big = {"Content-Length": str(10 * 1024 * 1024), "Content-Type": "multipart/form-data; boundary=x", **guest}
    assert claim(client, guest, task_id, "one").json()["result"] == "claimed"
    r = client.post("/api/claims/one/files", content=b"--x--", headers=big)
    assert (r.status_code, r.json()["detail"]) == (413, "photo_too_large")
    assert submissions() == []
