from datetime import timedelta
from threading import Barrier, Thread

import pytest
from sqlalchemy import select, update

from app import config, stages
from app.db import SessionLocal
from app.guest_list import import_csv
from app.models import Guest, ScoreEvent, Submission
from tests.conftest import moderator_headers, open_link, staff_headers
from tests.test_market import buy, market
from tests.test_market import load as load_market
from tests.test_qr_tasks import load, row, totals
from tests.test_submissions import ROWS, ids, jpeg, send_photo, send_text
from tests.test_tasks import admin, clock, guest  # noqa: F401 (fixtures)

MOD_ROWS = ROWS + [row("photo35", 1, "Фото на 35", points=35, method="Фото")]


def queue(client, h, **params):
    r = client.get("/api/moderation/queue", params=params, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def decide(client, h, submission_id, action):
    return client.post(f"/api/submissions/{submission_id}/decision", json={"action": action}, headers=h)


def task_card(client, guest, task_id):
    return client.get(f"/api/tasks/{task_id}", headers=guest).json()


def setup(client, admin, clock):
    load(client, admin, MOD_ROWS)
    clock("09:30")
    return ids(client, admin)


def test_login_needs_a_moderators_own_pin(client):
    assert client.post("/api/moderator/login", json={"secret": ""}).status_code == 401
    assert client.post("/api/moderator/login", json={"secret": "9999"}).status_code == 401
    # The desk's PIN doesn't open moderation
    assert client.post("/api/moderator/login", json={"secret": "1234"}).status_code == 401
    r = client.post("/api/moderator/login", json={"secret": "2222"})
    assert r.status_code == 200
    assert r.json()["name"] == "Модератор 2"


def test_queue_photo_and_decisions_need_a_moderator(client, admin, guest, clock):
    t = setup(client, admin, clock)
    send_photo(client, guest, t["photo1"])
    sid = submissions()[0].id
    for h in ({}, guest, admin, staff_headers(client, "desk")):
        assert client.get("/api/moderation/queue", headers=h).status_code == 401
        assert client.get(f"/api/submissions/{sid}/photo", headers=h).status_code == 401
        assert decide(client, h, sid, "accept").status_code == 401


def test_decisions_are_logged_under_the_moderators_name(client, admin, guest, clock):
    t = setup(client, admin, clock)
    send_photo(client, guest, t["photo1"])
    mod2 = moderator_headers(client, "2222")
    assert queue(client, mod2)["moderator"] == "Модератор 2"
    item = queue(client, mod2)["items"][0]
    r = decide(client, mod2, item["id"], "accept")
    assert r.status_code == 200, r.text
    assert (r.json()["result"], r.json()["moderator"]) == ("decided", "Модератор 2")
    s = submissions()[0]
    assert (s.status, s.moderator) == ("accepted", "Модератор 2")
    assert s.decided_at == stages.now()


def test_queue_shows_unchecked_submissions_newest_first(client, admin, guest, clock):
    t = setup(client, admin, clock)
    with SessionLocal() as db:
        db.execute(update(Guest).values(last_name="Петров"))
        db.commit()
    mod = moderator_headers(client)
    assert queue(client, mod) == {"moderator": "Модератор 1", "waiting": 0, "oldest_seconds": None, "items": []}
    send_photo(client, guest, t["photo1"])
    send_text(client, guest, t["text1"], "Отличный форум")
    send_photo(client, guest, t["both1"], text="Стих")
    q = queue(client, mod)
    assert q["waiting"] == 3
    assert [i["task"] for i in q["items"]] == ["Стих и фото", "Напишите отзыв", "Селфи у входа"]
    both, text, photo = q["items"]
    assert (both["photo"], both["text"], both["points"], both["guest"]) == (True, "Стих", 20, "Иван П.")
    assert (text["photo"], text["text"]) == (False, "Отличный форум")
    assert photo["photo"] is True
    # Decided ones leave the queue
    decide(client, mod, photo["id"], "accept")
    assert [i["task"] for i in queue(client, mod)["items"]] == ["Стих и фото", "Напишите отзыв"]


def test_queue_header_shows_the_oldest_waits_age(client, admin, guest, clock):
    t = setup(client, admin, clock)
    send_photo(client, guest, t["photo1"])
    send_text(client, guest, t["text1"], "Отзыв")
    with SessionLocal() as db:
        first, second = db.scalars(select(Submission).order_by(Submission.id))
        first.created_at = stages.now() - timedelta(minutes=7)
        second.created_at = stages.now() - timedelta(minutes=2)
        db.commit()
    q = queue(client, moderator_headers(client))
    assert (q["waiting"], q["oldest_seconds"]) == (2, 420)


def test_photo_is_served_to_the_moderator(client, admin, guest, clock):
    t = setup(client, admin, clock)
    data = jpeg(pad=300)
    send_photo(client, guest, t["photo1"], data)
    send_text(client, guest, t["text1"], "Отзыв")
    mod = moderator_headers(client)
    photo_id, text_id = sorted(s.id for s in submissions())
    r = client.get(f"/api/submissions/{photo_id}/photo", headers=mod)
    assert r.status_code == 200
    assert (r.headers["content-type"], r.content) == ("image/jpeg", data)
    assert client.get(f"/api/submissions/{text_id}/photo", headers=mod).status_code == 404
    assert client.get("/api/submissions/999/photo", headers=mod).status_code == 404


def test_accept_changes_nothing_for_the_guest(client, admin, guest, clock):
    t = setup(client, admin, clock)
    send_photo(client, guest, t["photo1"])
    before = totals(client, guest)
    mod = moderator_headers(client)
    decide(client, mod, queue(client, mod)["items"][0]["id"], "accept")
    assert totals(client, guest) == before
    card = task_card(client, guest, t["photo1"])
    assert (card["done"], card["review"]) == (True, "")
    assert queue(client, mod)["items"] == []


def test_bonus_adds_half_the_base_points_rounded_up_and_no_coins(client, admin, guest, clock):
    t = setup(client, admin, clock)
    send_photo(client, guest, t["photo35"])
    before = totals(client, guest)
    mod = moderator_headers(client)
    decide(client, mod, queue(client, mod)["items"][0]["id"], "bonus")
    assert totals(client, guest) == (before[0] + 18, before[1])
    assert task_card(client, guest, t["photo35"])["review"] == ""


def test_bonus_counts_the_points_awarded_not_a_later_upload(client, admin, guest, clock):
    t = setup(client, admin, clock)
    send_photo(client, guest, t["photo35"])
    # The admin raises the task's points after the guest sent it
    load(client, admin, ROWS + [row("photo35", 1, "Фото на 35", points=100, method="Фото")])
    before = totals(client, guest)
    mod = moderator_headers(client)
    item = queue(client, mod)["items"][0]
    # The card shows what the guest earned, the same base the bonus uses
    assert item["points"] == 35
    decide(client, mod, item["id"], "bonus")
    assert totals(client, guest) == (before[0] + 18, before[1])


def test_moderators_need_their_own_names_and_pins():
    assert config._moderators("Модератор 1:1111;Модератор 2:") == [("Модератор 1", "1111")]
    with pytest.raises(ValueError):
        config._moderators("Анна:1111;Борис:1111")
    with pytest.raises(ValueError):
        config._moderators("Анна:1111;Анна:2222")


def test_retake_takes_the_award_back_and_reopens_the_task(client, admin, guest, clock):
    t = setup(client, admin, clock)
    base = totals(client, guest)
    send_photo(client, guest, t["photo1"])
    mod = moderator_headers(client)
    decide(client, mod, queue(client, mod)["items"][0]["id"], "retake")
    assert totals(client, guest) == base
    card = task_card(client, guest, t["photo1"])
    assert (card["done"], card["review"]) == (False, "retake")
    feed_card = next(x for x in client.get("/api/feed", headers=guest).json()["tasks"] if x["id"] == t["photo1"])
    assert (feed_card["done"], feed_card["review"]) == (False, "retake")
    # The new photo counts, and goes to the queue
    r = send_photo(client, guest, t["photo1"], jpeg(800, 600))
    assert (r.json()["result"], r.json()["task"]["review"]) == ("awarded", "")
    assert totals(client, guest) == (base[0] + 15, base[1] + 15)
    card = task_card(client, guest, t["photo1"])
    assert (card["done"], card["review"]) == (True, "")
    assert len(queue(client, mod)["items"]) == 1
    # The rejected one stays as the log
    assert sorted(s.status for s in submissions()) == ["", "retake"]


def keyed_photo(client, guest, task_id, data, upload):
    files = {"photo": ("photo.jpg", data, "image/jpeg")}
    return client.post(f"/api/tasks/{task_id}/photo", files=files, data={"upload": upload}, headers=guest)


def test_a_late_retry_of_the_rejected_upload_is_not_awarded_again(client, admin, guest, clock):
    t = setup(client, admin, clock)
    base = totals(client, guest)
    data = jpeg(pad=100)
    keyed_photo(client, guest, t["photo1"], data, "send-1")
    mod = moderator_headers(client)
    decide(client, mod, queue(client, mod)["items"][0]["id"], "retake")
    # The phone never got the first answer and retries the same send after the retake
    r = keyed_photo(client, guest, t["photo1"], data, "send-1")
    assert (r.status_code, r.json()["detail"]) == (409, "sent_back")
    assert totals(client, guest) == base
    assert queue(client, mod)["items"] == []
    # The guest sending the very same photo again is a new send, and counts
    assert keyed_photo(client, guest, t["photo1"], data, "send-2").json()["result"] == "awarded"
    assert totals(client, guest) == (base[0] + 15, base[1] + 15)


def test_retake_of_a_text_task_lets_the_guest_write_again(client, admin, guest, clock):
    t = setup(client, admin, clock)
    base = totals(client, guest)
    send_text(client, guest, t["text1"], "Первый")
    mod = moderator_headers(client)
    decide(client, mod, queue(client, mod)["items"][0]["id"], "retake")
    # The same words again, typed anew, count
    r = client.post(f"/api/tasks/{t['text1']}/text", json={"text": "Первый", "upload": "send-2"}, headers=guest)
    assert r.json()["result"] == "awarded"
    assert totals(client, guest)[0] > base[0]
    assert send_text(client, guest, t["text1"], "Третий").json()["result"] == "already"


def test_a_retake_after_the_stage_closed_still_takes_the_award_back(client, admin, guest, clock):
    t = setup(client, admin, clock)
    base = totals(client, guest)
    send_photo(client, guest, t["photo1"])
    clock("11:00")
    mod = moderator_headers(client)
    assert decide(client, mod, queue(client, mod)["items"][0]["id"], "retake").json()["result"] == "decided"
    assert totals(client, guest) == base


def test_penalty_takes_the_award_back_and_keeps_the_task_closed(client, admin, guest, clock):
    t = setup(client, admin, clock)
    base = totals(client, guest)
    send_photo(client, guest, t["partner"])
    assert totals(client, guest) == (base[0] + 15, base[1] + 23)
    mod = moderator_headers(client)
    decide(client, mod, queue(client, mod)["items"][0]["id"], "penalty")
    assert totals(client, guest) == base
    card = task_card(client, guest, t["partner"])
    assert (card["done"], card["review"]) == (True, "penalty")
    r = send_photo(client, guest, t["partner"], jpeg(800, 600))
    assert (r.json()["result"], r.json()["task"]["review"]) == ("already", "penalty")
    assert totals(client, guest) == base
    assert len(submissions()) == 1


def test_rejection_after_spending_leaves_coins_negative_and_the_market_locked(client, admin, guest, clock):
    load_market(client, admin, tasks=MOD_ROWS)
    clock("09:30")
    c0 = totals(client, guest)[1]
    send_photo(client, guest, ids(client, admin)["photo35"])
    clock("14:30")
    m = market(client, guest)
    assert buy(client, guest, m, "Термокружка").status_code == 200
    mod = moderator_headers(client)
    decide(client, mod, queue(client, mod)["items"][0]["id"], "penalty")
    m = market(client, guest)
    assert m["coins"] == c0 + 35 - 30 - 35 < 0
    assert buy(client, guest, m, "Блокнот").json()["detail"] == "not_enough_coins"
    # Earned back up to the price: the market opens to them again
    with SessionLocal() as db:
        g = db.scalars(select(Guest)).one()
        db.add(ScoreEvent(guest_id=g.id, reason="earned_back", points=0, coins=10 - m["coins"]))
        db.commit()
    assert buy(client, guest, market(client, guest), "Блокнот").status_code == 200


def test_a_submission_is_decided_once(client, admin, guest, clock):
    t = setup(client, admin, clock)
    send_photo(client, guest, t["photo35"])
    sid = submissions()[0].id
    mod1, mod2 = moderator_headers(client, "1111"), moderator_headers(client, "2222")
    base = totals(client, guest)
    assert decide(client, mod1, sid, "bonus").json()["result"] == "decided"
    r = decide(client, mod2, sid, "penalty").json()
    assert (r["result"], r["status"], r["moderator"]) == ("already", "bonus", "Модератор 1")
    assert totals(client, guest) == (base[0] + 18, base[1])
    assert decide(client, mod2, 999, "accept").status_code == 404
    assert decide(client, mod2, sid, "delete").status_code == 422


def test_two_moderators_at_the_same_moment_only_the_first_counts(client, admin, guest, clock):
    t = setup(client, admin, clock)
    send_photo(client, guest, t["photo35"])
    sid = submissions()[0].id
    heads = [moderator_headers(client, "1111"), moderator_headers(client, "2222")]
    base = totals(client, guest)
    start = Barrier(2)
    results = []

    def go(h, action):
        start.wait()
        results.append(decide(client, h, sid, action).json()["result"])

    threads = [Thread(target=go, args=(heads[0], "bonus")), Thread(target=go, args=(heads[1], "penalty"))]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert sorted(results) == ["already", "decided"]
    status = submissions()[0].status
    assert status in ("bonus", "penalty")
    expected = (base[0] + 18, base[1]) if status == "bonus" else (base[0] - 35, base[1] - 35)
    assert totals(client, guest) == expected


def test_top20_shows_only_submissions_from_the_top_by_points(client, admin, guest, clock):
    t = setup(client, admin, clock)
    send_photo(client, guest, t["photo1"])
    with SessionLocal() as db:
        import_csv(db, ("ID;Имя\n" + "".join(f"R-{i};Гость{i}\n" for i in range(2, 24))).encode())
        others = list(db.scalars(select(Guest).where(Guest.first_name != "Иван").order_by(Guest.id)))
    # 21 guests well ahead of Иван, and one more behind him who also sent a photo
    heads = [open_link(client, f"http://api.test/b/{g.code}") for g in others]
    with SessionLocal() as db:
        for g in others[:21]:
            db.add(ScoreEvent(guest_id=g.id, reason="seed", points=1000, coins=0))
        db.commit()
    send_photo(client, heads[0], t["photo1"])
    send_photo(client, heads[21], t["photo1"])
    mod = moderator_headers(client)
    assert queue(client, mod)["waiting"] == 3
    q = queue(client, mod, top20="true")
    assert q["waiting"] == 1
    assert [i["guest"] for i in q["items"]] == ["Гость2"]
    # Decided ones leave the filter too
    decide(client, mod, q["items"][0]["id"], "accept")
    assert queue(client, mod, top20="true")["items"] == []


def submissions() -> list[Submission]:
    with SessionLocal() as db:
        return list(db.scalars(select(Submission).order_by(Submission.id)))
