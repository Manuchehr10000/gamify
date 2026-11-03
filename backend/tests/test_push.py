"""Piece 19: push notifications — the schedule kept in step with stages, quiz windows and the market, the job that sends
what is due, the prompt after the first task points, the banner in open apps and on /hall, and the counts."""
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app import config, push, stages
from app.db import SessionLocal
from app.models import PushMessage, PushSubscription, Stage, Task
from tests.test_admin_settings import find, log, rows, save
from tests.test_hall_screen import RU, at, day, quiz_at
from tests.test_rating import hall
from tests.test_tasks import DUSHANBE, admin, clock, guest  # noqa: F401 (fixtures)

PUBLIC = Path(__file__).resolve().parents[2] / "frontend" / "public"
INDEX = Path(__file__).resolve().parents[2] / "frontend" / "index.html"
JOBS = {"X-Jobs-Secret": "jobs-secret"}


@pytest.fixture
def vapid(monkeypatch):
    """Test keys, so the app asks and the job sends; nothing reaches a real push service (see `phones`)."""
    monkeypatch.setattr(config, "VAPID_PUBLIC_KEY", "test-public-key")
    monkeypatch.setattr(config, "VAPID_PRIVATE_KEY", "test-private-key")
    monkeypatch.setattr(config, "VAPID_SUBJECT", "mailto:push@example.test")


@pytest.fixture
def phones(monkeypatch, vapid):
    """Stands in for the push services: records every push per endpoint and answers ok, or what `answers` says."""
    got: dict[str, list[dict]] = {}
    answers: dict[str, str] = {}

    def deliver(subscription: dict, data: str) -> str:
        endpoint = subscription["endpoint"]
        answer = answers.get(endpoint, "ok")
        if answer == "ok":
            got.setdefault(endpoint, []).append(json.loads(data))
        return answer

    monkeypatch.setattr(push, "deliver", deliver)
    return got, answers


def second(monkeypatch, hhmmss: str) -> datetime:
    h, m, s = map(int, hhmmss.split(":"))
    t = datetime(2026, 12, 13, h, m, s, tzinfo=DUSHANBE)
    monkeypatch.setattr(stages, "now", lambda: t)
    return t


def subscribe(client, guest, endpoint="https://push.example.test/phone-1"):
    return client.post("/api/push/subscribe", json={"endpoint": endpoint, "keys": {"p256dh": "BPkey", "auth": "auth"}},
                       headers=guest)


def run(client) -> str:
    r = client.post("/api/jobs/run", headers=JOBS)
    assert r.status_code == 200, r.text
    job = next(x for x in r.json() if x["job"] == "push")
    assert job["result"] == "ok", job
    return job["detail"]


def schedule() -> list[PushMessage]:
    with SessionLocal() as db:
        return list(db.scalars(select(PushMessage).order_by(PushMessage.at, PushMessage.id)))


def message(source: str) -> PushMessage:
    return next(m for m in schedule() if m.source == source)


def quiz_id(hhmm: str) -> int:
    with SessionLocal() as db:
        return db.scalar(select(Task.id).where(Task.code == f"Q{hhmm}"))


def link_task(stage_id: int) -> int:
    with SessionLocal() as db:
        t = Task(code="L1", stage_id=stage_id, type="Действие", text="Открыть сайт партнёра", points=10, coins=5,
                 method="link", link="https://example.test")
        db.add(t)
        db.commit()
        return t.id


def received(client, push_id: int, key: str):
    return client.post(f"/api/push/{push_id}/received", json={"subscription": key})


def sub_key(endpoint="https://push.example.test/phone-1") -> str:
    with SessionLocal() as db:
        return db.scalar(select(PushSubscription.key).where(PushSubscription.endpoint == endpoint))


def setting(client, admin, key: str, value):  # noqa: F811
    s = next(x for x in client.get("/api/admin/settings", headers=admin).json() if x["key"] == key)
    return client.put(f"/api/admin/settings/{key}", json={"value": value, "version": s["version"]}, headers=admin)


# The prompt

def test_the_app_asks_after_the_first_task_points_not_before(client, guest, clock, vapid):  # noqa: F811
    ids = day()
    task = link_task(ids[1])
    clock("09:10")
    me = client.post("/api/consent", headers=guest).json()
    assert me["arrival_points"] == 10
    assert me["vapid_public_key"] == "test-public-key"
    # The +10 for arriving doesn't count
    assert client.get("/api/feed", headers=guest).json()["ask_push"] is False
    assert client.post(f"/api/tasks/{task}/complete", headers=guest).json()["result"] == "awarded"
    assert client.get("/api/feed", headers=guest).json()["ask_push"] is True
    # Once per phone is the phone's own memory: a second phone of this guest is still asked
    assert subscribe(client, guest).status_code == 200
    assert client.get("/api/feed", headers=guest).json()["ask_push"] is True


def test_without_vapid_keys_the_app_never_asks_and_nothing_subscribes(client, guest, clock):  # noqa: F811
    ids = day()
    task = link_task(ids[1])
    clock("09:10")
    client.post(f"/api/tasks/{task}/complete", headers=guest)
    assert client.get("/api/me", headers=guest).json()["vapid_public_key"] == ""
    assert client.get("/api/feed", headers=guest).json()["ask_push"] is False
    assert subscribe(client, guest).status_code == 503


def test_subscribing_needs_a_guest_login_and_a_push_address(client, guest, vapid):  # noqa: F811
    assert subscribe(client, {}).status_code == 401
    assert subscribe(client, guest, "http://push.example.test/x").status_code == 400
    assert subscribe(client, guest).status_code == 200
    # The same browser again (a new login on it) is the same subscription
    assert subscribe(client, guest).status_code == 200
    with SessionLocal() as db:
        assert len(db.scalars(select(PushSubscription)).all()) == 1


# Quiz pushes

def test_a_quiz_opening_at_14_pushes_at_13_55_and_at_14(client, guest, clock, phones):  # noqa: F811
    got, _ = phones
    ids = day()
    quiz_at(ids[3], "14:00", "Квиз про партнёров")
    subscribe(client, guest)
    phone = "https://push.example.test/phone-1"
    clock("13:54")
    run(client)
    assert not any(p["body"] == "Квиз про партнёров" for p in got.get(phone, []))
    clock("13:55")
    run(client)
    before = [p for p in got[phone] if p["body"] == "Квиз про партнёров"]
    assert [p["title"] for p in before] == ["Через 5 минут — квиз"]
    # Tapping it opens the quiz's task page
    assert before[0]["url"] == f"/app/tasks/{quiz_id('14:00')}"
    clock("14:00")
    run(client)
    titles = [p["title"] for p in got[phone] if p["body"] == "Квиз про партнёров"]
    assert titles == ["Через 5 минут — квиз", "Квиз открыт: 5 минут"]
    # Each push is sent once
    clock("14:01")
    run(client)
    assert len([p for p in got[phone] if p["body"] == "Квиз про партнёров"]) == 2


def test_moving_the_quiz_15_minutes_moves_both_pushes(client, admin, clock):  # noqa: F811
    ids = day()
    quiz_at(ids[3], "14:00")
    clock("12:00")
    pushes = {r["values"]["kind"]: r["values"]["at"] for r in rows(client, admin, "push")["rows"]}
    assert pushes["quiz_before"] == "2026-12-13T13:55" and pushes["quiz_open"] == "2026-12-13T14:00"
    task = find(client, admin, "tasks", "code", "Q14:00")
    assert save(client, admin, "tasks", task, window_start="2026-12-13T14:15", window_end="2026-12-13T14:45",
                confirm=True).status_code == 200
    pushes = {r["values"]["kind"]: r["values"]["at"] for r in rows(client, admin, "push")["rows"]}
    assert pushes["quiz_before"] == "2026-12-13T14:10" and pushes["quiz_open"] == "2026-12-13T14:15"


def test_an_admins_move_survives_the_quiz_moving(client, admin, clock):  # noqa: F811
    ids = day()
    quiz_at(ids[3], "14:00")
    clock("12:00")
    before = find(client, admin, "push", "kind", "quiz_before")
    assert save(client, admin, "push", before, at="2026-12-13T13:50").status_code == 200
    task = find(client, admin, "tasks", "code", "Q14:00")
    save(client, admin, "tasks", task, window_start="2026-12-13T14:30", window_end="2026-12-13T15:00", confirm=True)
    # 10 minutes before the quiz, as the admin set it, now before the new time
    assert find(client, admin, "push", "kind", "quiz_before")["values"]["at"] == "2026-12-13T14:20"


def test_a_switched_off_quiz_drops_its_pushes(client, admin, clock):  # noqa: F811
    ids = day()
    quiz_at(ids[3], "14:00")
    clock("12:00")
    assert {r["values"]["kind"] for r in rows(client, admin, "push")["rows"]} >= {"quiz_before", "quiz_open"}
    task = find(client, admin, "tasks", "code", "Q14:00")
    save(client, admin, "tasks", task, active=False, confirm=True)
    assert not {r["values"]["kind"] for r in rows(client, admin, "push")["rows"]} & {"quiz_before", "quiz_open"}


def test_a_phone_off_for_15_minutes_does_not_get_the_push_late(client, guest, clock, phones):  # noqa: F811
    got, _ = phones
    ids = day()
    quiz_at(ids[3], "14:00")
    subscribe(client, guest)
    clock("13:50")
    run(client)
    # No job ran from 13:52 to 14:11: both quiz pushes are past their 10-minute life
    clock("14:11")
    run(client)
    assert {m.kind: m.state for m in schedule() if m.kind.startswith("quiz")} == {
        "quiz_before": "expired", "quiz_open": "expired"}
    assert not got


def test_the_push_service_is_told_the_10_minute_life(monkeypatch, vapid):
    calls = []
    monkeypatch.setattr(push, "webpush", lambda *a, **kw: calls.append(kw))
    assert push.deliver({"endpoint": "https://push.example.test/x", "keys": {}}, "{}") == "ok"
    assert calls[0]["ttl"] == 600
    assert calls[0]["vapid_claims"] == {"sub": "mailto:push@example.test"}


# Stage and market pushes

def test_stage_2_at_x2_pushes_its_banner_title_and_its_line(client, guest, clock, phones):  # noqa: F811
    got, _ = phones
    ids = day()
    with SessionLocal() as db:
        s = db.get(Stage, ids[2])
        s.multiplier, s.message = 2, "Время побеждать"
        db.commit()
    subscribe(client, guest)
    clock("10:30")
    run(client)
    stage = [p for p in got["https://push.example.test/phone-1"] if p["title"].startswith("Новый этап: Этап 2")]
    assert [(p["title"], p["body"], p["url"]) for p in stage] == [("Новый этап: Этап 2 — очки ×2", "Время побеждать", "/app")]
    # The same title as the app's stage banner (feed.newStageMultiplier)
    assert RU["feed"]["newStageMultiplier"].replace("{{name}}", "Этап 2").replace("{{mark}}", "×2") == stage[0]["title"]
    assert RU["feed"]["newStage"].replace("{{name}}", "Этап 1") == message(f"stage:{ids[1]}").title


def test_a_half_multiplier_is_written_with_a_comma():
    assert push.stage_title(Stage(name="Финал", multiplier=1.5)) == "Новый этап: Финал — очки ×1,5"


def test_the_first_market_stage_pushes_the_stage_then_the_market(client, guest, clock, phones):  # noqa: F811
    got, _ = phones
    day(market=3)
    subscribe(client, guest)
    clock("14:00")
    run(client)
    titles = [p["title"] for p in got["https://push.example.test/phone-1"]]
    assert titles[-2:] == ["Новый этап: Этап 3", "Маркет открыт — обменяйте монеты на призы"]


def test_starting_the_next_stage_now_moves_its_push(client, admin, guest, clock, phones):  # noqa: F811
    got, _ = phones
    day()
    subscribe(client, guest)
    clock("09:30")
    run(client)
    r = client.post("/api/admin/stages/advance?confirm=true", headers=admin)
    assert r.status_code == 200, r.text
    run(client)
    assert got["https://push.example.test/phone-1"][-1]["title"] == "Новый этап: Этап 2"


# The banner in open apps and on /hall

def test_a_sent_push_shows_in_open_apps_and_on_the_hall_for_15_seconds(client, guest, monkeypatch, phones):  # noqa: F811
    ids = day()
    quiz_at(ids[3], "14:00", "Квиз про форум")
    second(monkeypatch, "14:00:00")
    run(client)
    banner = client.get("/api/feed", headers=guest).json()["push"]
    assert (banner["kind"], banner["title"], banner["text"]) == ("quiz_open", "Квиз открыт: 5 минут", "Квиз про форум")
    assert hall(client)["push"] == {"id": banner["id"], "text": "Квиз открыт: 5 минут\nКвиз про форум"}
    second(monkeypatch, "14:00:16")
    assert hall(client)["push"] is None
    # The app's banner lasts the push's 10-minute life
    second(monkeypatch, "14:09:59")
    assert client.get("/api/feed", headers=guest).json()["push"]["id"] == banner["id"]
    second(monkeypatch, "14:10:01")
    assert client.get("/api/feed", headers=guest).json()["push"] is None


# The admin's controls

def test_a_cancelled_push_never_goes_and_send_now_goes_at_once(client, admin, guest, clock, phones):  # noqa: F811
    got, _ = phones
    ids = day()
    quiz_at(ids[3], "14:00", "Квиз про форум")
    subscribe(client, guest)
    clock("12:00")
    before = find(client, admin, "push", "kind", "quiz_before")
    assert save(client, admin, "push", before, state="cancelled").status_code == 200
    clock("13:55")
    run(client)
    assert not any(p["title"] == "Через 5 минут — квиз" for p in got.get("https://push.example.test/phone-1", []))
    assert message(f"quiz_before:{quiz_id('14:00')}").state == "cancelled"
    # «Отправить сейчас» sends the planned open push straight away
    opening = find(client, admin, "push", "kind", "quiz_open")
    r = client.post(f"/api/admin/push/{opening['id']}/send", headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "sent" and r.json()["sends"] == 1
    assert got["https://push.example.test/phone-1"][-1]["title"] == "Квиз открыт: 5 минут"
    # The job doesn't send it a second time at 14:00
    clock("14:00")
    run(client)
    assert sum(p["title"] == "Квиз открыт: 5 минут" for p in got["https://push.example.test/phone-1"]) == 1
    assert any(e["kind"] == "push" and e["new_value"] == "sent" for e in log(client, admin))
    # Sent again, it goes as a copy with its own id, so open apps and /hall show its banner again
    clock("14:01")
    r = client.post(f"/api/admin/push/{opening['id']}/send", headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["id"] != opening["id"] and r.json()["sends"] == 1
    assert sum(p["title"] == "Квиз открыт: 5 минут" for p in got["https://push.example.test/phone-1"]) == 2
    assert client.get("/api/feed", headers=guest).json()["push"]["id"] == r.json()["id"]


def test_send_now_is_for_admins_only(client, guest, vapid):  # noqa: F811
    assert client.post("/api/admin/push/1/send", headers=guest).status_code == 401


def test_an_edited_text_is_the_one_that_arrives_and_stays(client, admin, guest, clock, phones):  # noqa: F811
    got, _ = phones
    ids = day()
    quiz_at(ids[3], "14:00", "Квиз про форум")
    subscribe(client, guest)
    clock("12:00")
    opening = find(client, admin, "push", "kind", "quiz_open")
    assert save(client, admin, "push", opening, title="Квиз в зале А!", text="Бегите к сцене").status_code == 200
    # The quiz's own text changing later doesn't overwrite the admin's
    task = find(client, admin, "tasks", "code", "Q14:00")
    save(client, admin, "tasks", task, text="Новый текст квиза", confirm=True)
    clock("14:00")
    run(client)
    last = got["https://push.example.test/phone-1"][-1]
    assert (last["title"], last["body"]) == ("Квиз в зале А!", "Бегите к сцене")


def test_a_one_off_message_for_15_30_goes_at_15_30(client, admin, guest, clock, phones):  # noqa: F811
    got, _ = phones
    day(market=None)
    subscribe(client, guest)
    clock("12:00")
    r = client.post("/api/admin/lists/push", json={"values": {"kind": "one_off", "at": "2026-12-13T15:30",
                                                              "text": "Кофе-брейк в фойе"}}, headers=admin)
    assert r.status_code == 200, r.text
    # A blank title is the «one-off» text from the settings
    assert r.json()["values"]["title"] == "Сообщение организаторов"
    clock("15:29")
    run(client)
    assert not any(p["body"] == "Кофе-брейк в фойе" for p in got.get("https://push.example.test/phone-1", []))
    clock("15:30")
    run(client)
    assert got["https://push.example.test/phone-1"][-1]["body"] == "Кофе-брейк в фойе"
    assert got["https://push.example.test/phone-1"][-1]["url"] == "/app"


def test_only_one_off_messages_are_added_and_source_pushes_are_cancelled_not_deleted(client, admin, clock):  # noqa: F811
    ids = day()
    quiz_at(ids[3], "14:00")
    clock("12:00")
    r = client.post("/api/admin/lists/push", json={"values": {"kind": "market", "at": "2026-12-13T15:30",
                                                              "title": "x"}}, headers=admin)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "one_off_only"
    opening = find(client, admin, "push", "kind", "quiz_open")
    r = client.delete(f"/api/admin/lists/push/{opening['id']}", headers=admin)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "source_push"
    # Sent and expired are the job's to set
    assert save(client, admin, "push", opening, state="sent").status_code == 400


def test_switched_off_nothing_is_sent_but_the_banner_still_shows(client, admin, guest, clock, phones):  # noqa: F811
    got, _ = phones
    ids = day()
    quiz_at(ids[3], "14:00", "Квиз про форум")
    subscribe(client, guest)
    assert setting(client, admin, "push_enabled", 0).status_code == 200
    clock("14:00")
    run(client)
    assert not got
    banner = client.get("/api/feed", headers=guest).json()["push"]
    assert banner["title"] == "Квиз открыт: 5 минут"
    assert message(f"quiz_open:{quiz_id('14:00')}").state == "expired"
    opening = find(client, admin, "push", "kind", "quiz_open")
    assert client.post(f"/api/admin/push/{opening['id']}/send", headers=admin).status_code == 409
    # Switched on again: the next push goes
    assert setting(client, admin, "push_enabled", 1).status_code == 200
    clock("16:30")
    run(client)
    assert got["https://push.example.test/phone-1"][-1]["title"] == "Новый этап: Этап 4"


def test_the_push_texts_are_settings_applying_from_now_on(client, admin, clock):  # noqa: F811
    ids = day()
    quiz_at(ids[3], "14:00")
    clock("12:00")
    r = setting(client, admin, "push_text_quiz_open", "Квиз! Пять минут на ответы")
    assert r.status_code == 200, r.text
    assert r.json()["text"] == "Квиз! Пять минут на ответы"
    assert find(client, admin, "push", "kind", "quiz_open")["values"]["title"] == "Квиз! Пять минут на ответы"
    r = setting(client, admin, "push_text_quiz_open", "")
    assert r.status_code == 400 and r.json()["detail"] == {"code": "length", "field": "push_text_quiz_open",
                                                          "min": 1, "max": 200}
    assert any(e["item"] == "push_text_quiz_open" and e["new_value"] == "Квиз! Пять минут на ответы"
               for e in log(client, admin))


# Subscriptions and counts

def test_a_dropped_subscription_is_switched_off_and_skipped_after(client, guest, clock, phones):  # noqa: F811
    got, answers = phones
    ids = day()
    quiz_at(ids[3], "14:00")
    subscribe(client, guest, "https://push.example.test/gone")
    answers["https://push.example.test/gone"] = "gone"
    calls = []
    real = push.deliver
    push.deliver = lambda s, d: calls.append(s["endpoint"]) or real(s, d)
    try:
        clock("13:55")
        run(client)
        with SessionLocal() as db:
            assert db.scalar(select(PushSubscription.active)) is False
        clock("14:00")
        run(client)
    finally:
        push.deliver = real
    # Tried once, never again
    assert calls.count("https://push.example.test/gone") == 1
    assert message(f"quiz_before:{quiz_id('14:00')}").failures == 1


def test_live_shows_opt_ins_sends_deliveries_and_failures(client, admin, guest, clock, phones):  # noqa: F811
    _, answers = phones
    ids = day()
    quiz_at(ids[3], "14:00")
    subscribe(client, guest, "https://push.example.test/phone-1")
    subscribe(client, guest, "https://push.example.test/phone-2")
    subscribe(client, guest, "https://push.example.test/broken")
    answers["https://push.example.test/broken"] = "failed"
    clock("13:55")
    run(client)
    sent = message(f"quiz_before:{quiz_id('14:00')}")
    # The phone's service worker reports the arrival, without a login, once per subscription
    key = sub_key()
    assert received(client, sent.id, key).json() == {"counted": True}
    assert received(client, sent.id, key).json() == {"counted": False}
    assert received(client, sent.id, "not-a-key").json() == {"counted": False}
    live = client.get("/api/admin/live", headers=admin).json()
    assert (live["push_opt_ins"], live["push_sends"], live["push_deliveries"], live["push_failures"]) == (3, 2, 1, 1)
    # A plain failure keeps the subscription; only «gone» switches it off
    assert live["push_opt_ins"] == 3


def test_an_arrival_for_a_push_not_sent_is_not_counted(client, guest, clock, vapid):  # noqa: F811
    ids = day()
    quiz_at(ids[3], "14:00")
    subscribe(client, guest)
    clock("12:00")
    run(client)
    planned = message(f"quiz_open:{quiz_id('14:00')}")
    assert received(client, planned.id, sub_key()).json() == {"counted": False}


# The Home Screen app

def test_the_app_has_a_manifest_and_an_apple_touch_icon():
    manifest = json.loads((PUBLIC / "manifest.webmanifest").read_text("utf-8"))
    assert manifest["display"] == "standalone" and manifest["name"]
    # No fixed start address: the Home Screen link is the page it was added from, signed in
    assert "start_url" not in manifest
    assert all((PUBLIC / icon["src"].lstrip("/")).read_bytes().startswith(b"\x89PNG") for icon in manifest["icons"])
    assert (PUBLIC / "apple-touch-icon.png").read_bytes().startswith(b"\x89PNG")
    page = INDEX.read_text("utf-8")
    assert 'rel="manifest"' in page and 'rel="apple-touch-icon"' in page


def test_the_service_worker_shows_pushes_and_reports_their_arrival():
    worker = (PUBLIC / "sw.js").read_text("utf-8")
    assert "addEventListener('push'" in worker and "addEventListener('notificationclick'" in worker
    assert "/received" in worker


def test_the_prompt_and_the_guide_texts_are_in_the_language_file():
    assert RU["push"]["ask"] == "Узнайте первым о квизе и открытии маркета"
    assert RU["push"]["later"] == "Не сейчас"
    assert RU["profile"]["pushGuide"]


# The app's side (read from the sources, as test_console_admin does)

SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"
PUSH_TS = (SRC / "push.ts").read_text("utf-8")
FEED_TSX = (SRC / "pages" / "Feed.tsx").read_text("utf-8")
PROFILE_TSX = (SRC / "pages" / "Profile.tsx").read_text("utf-8")


def test_in_iphone_safari_the_guide_shows_on_opening_and_the_prompt_never_does():
    assert "useState(() => needsHomeScreen() && !guideClosed())" in FEED_TSX
    may_ask = PUSH_TS[PUSH_TS.index("export const mayAsk"):PUSH_TS.index("export const markAsked")]
    assert "!needsHomeScreen()" in may_ask


def test_the_app_asks_once_per_phone_after_not_now_or_block():
    may_ask = PUSH_TS[PUSH_TS.index("export const mayAsk"):PUSH_TS.index("export const markAsked")]
    assert "Notification.permission !== 'denied'" in may_ask and "read(ASKED_KEY) === null" in may_ask
    ask = FEED_TSX[FEED_TSX.index("<PushAsk"):]
    assert "markAsked()" in ask[:ask.index("/>")]
    enable = PUSH_TS[PUSH_TS.index("export async function enablePush"):]
    assert enable.index("markAsked()") < enable.index("await ")


def test_the_browser_prompt_comes_first_while_the_tap_still_counts():
    # Safari and Firefox show the prompt only inside the tap: nothing is awaited before it
    enable = PUSH_TS[PUSH_TS.index("export async function enablePush"):]
    assert enable.index("Notification.requestPermission()") < enable.index("await ")
    assert "'/api/me'" in FEED_TSX


def test_the_closed_guide_opens_again_from_the_profile():
    assert "needsHomeScreen() && (guide" in PROFILE_TSX and "setGuide(true)" in PROFILE_TSX


def test_a_stage_push_is_the_stage_banner_not_a_second_one():
    assert "feed.push.kind !== 'stage'" in FEED_TSX


def test_the_login_rides_in_the_fragment_of_the_same_page_so_back_still_works():
    login = PUSH_TS[PUSH_TS.index("export function useLoginInAddress"):]
    login = login[:login.index("\n}\n")]
    assert "/app/welcome" not in login and "#token=" in login
    main = (SRC / "main.tsx").read_text("utf-8")
    assert "takeLoginFromAddress()" in main
