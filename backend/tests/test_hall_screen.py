"""Piece 18: the hall screen's slides, «Эфир», the staff's four switches and the logo log."""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from app import hall as screen
from app.db import SessionLocal
from app.models import HallState, LogoShow, Partner, Stage, Task
from tests.conftest import moderator_headers, staff_headers
from tests.test_admin_settings import PNG
from tests.test_rating import freeze, guests, hall, score
from tests.test_tasks import DUSHANBE, admin, clock, guest  # noqa: F401 (fixtures)

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"
RU = json.loads((FRONTEND / "locales" / "ru.json").read_text("utf-8"))


def at(hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime(2026, 12, 13, h, m, tzinfo=DUSHANBE)


def day(market: int | None = 3) -> dict[int, int]:
    """TAG's four stages, the last ending at 18:00; returns the stage ids by number."""
    times = [("09:00", "10:30"), ("10:30", "14:00"), ("14:00", "16:30"), ("16:30", "18:00")]
    with SessionLocal() as db:
        rows = [Stage(number=n, name=f"Этап {n}", starts_at=at(a), ends_at=at(b), market=n == market)
                for n, (a, b) in enumerate(times, start=1)]
        db.add_all(rows)
        db.commit()
        return {s.number: s.id for s in rows}


def quiz_at(stage_id: int, hhmm: str, text: str = "Квиз про форум") -> None:
    with SessionLocal() as db:
        db.add(Task(code=f"Q{hhmm}", stage_id=stage_id, type="Квиз", text=text, points=50, coins=10, method="quiz",
                    window_start=at(hhmm), window_end=at(hhmm) + timedelta(minutes=30)))
        db.commit()


def partner(name: str, package: str, logo: bool = True, active: bool = True) -> int:
    with SessionLocal() as db:
        p = Partner(name=name, package=package, logo=PNG if logo else None, active=active)
        db.add(p)
        db.commit()
        return p.id


def switch(client, h, mode: str):
    return client.post("/api/hall/mode", json={"mode": mode}, headers=h)


def changed_by() -> str:
    with SessionLocal() as db:
        return db.scalar(select(HallState.staff_name))


def on_air(body: dict, now: datetime) -> bool:
    """What the screen shows «Эфир» by: the switch, or «Авто» past its time."""
    live_from = body["live_from"] and datetime.fromisoformat(body["live_from"])
    return body["mode"] == "live" or (body["mode"] == "auto" and bool(live_from) and now >= live_from)


# «Эфир» by itself

def test_with_30_minutes_left_in_the_last_stage_the_hall_goes_on_air_by_itself(client, clock):  # noqa: F811
    day()
    clock("17:29")
    body = hall(client)
    assert body["mode"] == "auto"
    assert datetime.fromisoformat(body["live_from"]) == at("17:30")
    assert not on_air(body, datetime.fromisoformat(body["now"]))
    clock("17:30")
    body = hall(client)
    assert on_air(body, datetime.fromisoformat(body["now"]))
    # After the last stage ends it stays on until someone switches
    clock("18:40")
    body = hall(client)
    assert on_air(body, datetime.fromisoformat(body["now"]))


def test_moving_the_last_stage_or_the_setting_moves_on_air(client, admin, clock):  # noqa: F811
    ids = day()
    clock("12:00")
    with SessionLocal() as db:
        db.get(Stage, ids[4]).ends_at = at("19:00")
        db.commit()
    assert datetime.fromisoformat(hall(client)["live_from"]) == at("18:30")
    s = next(s for s in client.get("/api/admin/settings", headers=admin).json() if s["key"] == "hall_live_minutes")
    assert s["value"] == 30
    r = client.put("/api/admin/settings/hall_live_minutes", json={"value": 45, "version": s["version"]}, headers=admin)
    assert r.status_code == 200, r.text
    assert datetime.fromisoformat(hall(client)["live_from"]) == at("18:15")


def test_without_a_schedule_there_is_no_on_air_time(client):
    assert hall(client)["live_from"] is None


# The four switches

def test_a_moderator_switches_to_logos_only_and_back_to_auto(client, clock):  # noqa: F811
    clock("12:00")
    h = moderator_headers(client)
    r = switch(client, h, "logos")
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "logos"
    assert changed_by() == "Модератор 1"
    assert hall(client)["mode"] == "logos"
    assert switch(client, h, "auto").json()["mode"] == "auto"
    assert hall(client)["mode"] == "auto"


def test_on_air_now_shows_at_any_time_and_auto_returns_the_cycle(client, clock):  # noqa: F811
    day()
    clock("10:00")
    h = moderator_headers(client, "2222")
    switch(client, h, "live")
    body = hall(client)
    assert on_air(body, datetime.fromisoformat(body["now"]))
    switch(client, h, "auto")
    body = hall(client)
    assert not on_air(body, datetime.fromisoformat(body["now"]))


def test_pause_holds_until_another_switch(client, admin, clock):  # noqa: F811
    day()
    clock("17:45")
    switch(client, moderator_headers(client), "pause")
    body = hall(client)
    # Paused in «Эфир» time: the screen holds what it shows, it doesn't switch on its own
    assert body["mode"] == "pause" and not on_air(body, datetime.fromisoformat(body["now"]))
    assert switch(client, admin, "logos").json()["mode"] == "logos"


def test_an_admin_switches_from_admin_live_and_the_hall_reads_it(client, admin):  # noqa: F811
    assert hall(client)["mode"] == "auto"
    r = switch(client, admin, "live")
    assert (r.status_code, changed_by()) == (200, "Администратор")
    assert hall(client)["mode"] == "live"
    # The panel's four switches and its title
    assert RU["hallScreen"]["title"] == "Экран в зале"
    assert [RU["hallScreen"]["modes"][m] for m in ("auto", "live", "logos", "pause")] == [
        "Авто", "Эфир сейчас", "Только логотипы", "Пауза"]
    for page in ("Moderate.tsx", "AdminLive.tsx"):
        assert "<HallSwitch" in (FRONTEND / "pages" / page).read_text("utf-8")


def test_a_guest_or_a_logged_out_browser_cannot_switch(client, guest):  # noqa: F811
    assert switch(client, {}, "live").status_code == 401
    assert switch(client, guest, "live").status_code == 401
    for role in ("desk", "stand"):
        assert switch(client, staff_headers(client, role), "live").status_code == 401
    assert switch(client, admin_headers(client), "loud").status_code == 422
    assert hall(client)["mode"] == "auto"


def admin_headers(client):
    return staff_headers(client, "admin")


# Push

def test_a_push_in_the_hall_body_carries_its_id_and_text(client, monkeypatch):
    assert hall(client)["push"] is None
    monkeypatch.setattr(screen, "latest_push", lambda _db: screen.Push(7, "Квиз начинается!"))
    assert hall(client)["push"] == {"id": 7, "text": "Квиз начинается!"}
    # The screen shows it 15 seconds, once per id, only in «Авто» and «Только логотипы»
    page = (FRONTEND / "pages" / "Hall.tsx").read_text("utf-8")
    assert "PUSH_MS = 15_000" in page
    assert re.search(r"PUSH_MODES: HallMode\[\] = \['auto', 'logos'\]", page)


# Freeze

def test_every_mode_shows_the_frozen_places(client, admin):  # noqa: F811
    g = guests("ID;Имя\nR-1;Анна\nR-2;Борис\n")
    score(g["Анна"], 10, 1)
    assert freeze(client, admin).status_code == 200
    score(g["Борис"], 100, 2)
    for mode in ("auto", "live", "logos", "pause"):
        switch(client, admin, mode)
        body = hall(client)
        assert body["frozen"] is True
        assert [r["name"] for r in body["top"]] == ["Анна"]


# Logos

def test_a_general_partner_shows_larger_and_more_often_than_a_supporter_and_both_are_logged(client, clock):  # noqa: F811
    clock("12:00")
    general = partner("Alif", "general")
    supporter = partner("Чайхона", "supporters")
    partner("Без логотипа", "headliner", logo=False)
    partner("Выключен", "general", active=False)
    logos = hall(client)["logos"]
    assert [(lg["name"], lg["size"], lg["every"]) for lg in logos] == [("Alif", 3, 1), ("Чайхона", 1, 3)]
    assert logos[0]["url"].startswith(f"/api/partners/{general}/logo?v=")
    assert client.get(logos[0]["url"]).content == PNG
    start = at("11:59").isoformat()
    r = client.post("/api/hall/logo-shows", json={"shows": [
        {"partner_id": general, "started_at": start, "seconds": 8},
        {"partner_id": supporter, "started_at": start, "seconds": 8},
    ]})
    assert (r.status_code, r.json()) == (200, {"kept": 2})
    with SessionLocal() as db:
        assert sorted((s.partner_id, s.seconds) for s in db.scalars(select(LogoShow))) == [
            (general, 8), (supporter, 8)]


def test_package_defaults_and_a_partner_without_a_package(client):
    partner("Без пакета", "")
    partner("Хедлайнер", "headliner")
    partner("МФ", "mf_partner")
    logos = hall(client)["logos"]
    assert [(lg["name"], lg["size"], lg["every"]) for lg in logos] == [
        ("Хедлайнер", 2, 1), ("МФ", 2, 2), ("Без пакета", 1, 3)]


def test_the_server_drops_logo_logs_that_fail_its_checks(client, clock):  # noqa: F811
    clock("12:00")
    good = partner("Alif", "general")
    off = partner("Выключен", "general", active=False)
    show = {"partner_id": good, "started_at": at("11:50").isoformat(), "seconds": 8}
    r = client.post("/api/hall/logo-shows", json={"shows": [
        show,
        {**show, "partner_id": off},
        {**show, "partner_id": 9999},
        {**show, "seconds": 0, "started_at": at("11:51").isoformat()},
        {**show, "seconds": 31, "started_at": at("11:52").isoformat()},
        {**show, "started_at": at("09:59").isoformat()},
        {**show, "started_at": at("12:10").isoformat()},
    ]})
    assert r.json() == {"kept": 1}
    # The same show sent again after a timeout is kept once
    assert client.post("/api/hall/logo-shows", json={"shows": [show]}).json() == {"kept": 0}
    with SessionLocal() as db:
        assert db.scalar(select(LogoShow.seconds)) == 8


# Countdown

def test_with_the_next_quiz_at_14_00_at_13_50_the_countdown_is_10_minutes_to_it(client, clock):  # noqa: F811
    ids = day()
    quiz_at(ids[2], "14:00")
    clock("13:50")
    body = hall(client)
    assert body["next"]["kind"] == "quiz" and body["next"]["name"] == "Квиз про форум"
    left = datetime.fromisoformat(body["next"]["at"]) - datetime.fromisoformat(body["now"])
    assert left == timedelta(minutes=10)


def test_the_countdown_takes_the_market_or_the_next_stage_whichever_comes_first(client, clock):  # noqa: F811
    day(market=3)
    clock("12:00")
    # Stage 3 starts at 14:00 and opens the market: the market wins the tie
    assert hall(client)["next"]["kind"] == "market"
    clock("15:00")
    assert hall(client)["next"] == {"kind": "stage", "name": "Этап 4", "at": hall(client)["next"]["at"]}
    clock("17:00")
    assert hall(client)["next"] is None


# Settings and layout

def test_the_hall_settings_have_their_defaults_and_limits(client, admin):  # noqa: F811
    rows = {s["key"]: s for s in client.get("/api/admin/settings", headers=admin).json()}
    assert (rows["hall_slide_seconds"]["value"], rows["hall_slide_seconds"]["min"],
            rows["hall_slide_seconds"]["max"]) == (8, 4, 30)
    assert rows["hall_live_minutes"]["value"] == 30
    assert rows["hall_min_font_px"]["value"] == 40
    assert {k: rows[f"hall_{k}_size"]["value"] for k in screen.PACKAGES} == {
        "general": 3, "headliner": 2, "mf_partner": 2, "supporters": 1}
    assert {k: rows[f"hall_{k}_every"]["value"] for k in screen.PACKAGES} == {
        "general": 1, "headliner": 1, "mf_partner": 2, "supporters": 3}
    for key in rows:
        assert RU["settingsAdmin"]["fields"]["settings"][key]
    body = hall(client)
    assert (body["slide_seconds"], body["min_font_px"]) == (8, 40)


def test_no_hall_text_is_smaller_than_the_minimum_font_setting():
    css = (FRONTEND / "components" / "console" / "console.css").read_text("utf-8")
    hall_css = "\n".join(line for line in css.splitlines() if ".gc-hall" in line)
    sizes = re.findall(r"font-size: ([^;]+);", hall_css)
    assert sizes and all(s.startswith("max(var(--hall-min-font)") for s in sizes), sizes
    page = (FRONTEND / "pages" / "Hall.tsx").read_text("utf-8")
    assert "--hall-min-font" in page
    # A shared class that sets its own font size (.gc-score-l and the like) is only used on /hall together with a
    # hall class whose rule raises it to the minimum
    sized = {m for m in re.findall(r"^\.(gc-[\w-]+) \{[^}]*font-size", css, re.M) if not m.startswith("gc-hall")}
    raised = set(re.findall(r"\.(gc-hall-board__[\w-]+)[^{]*\{[^}]*font-size: max\(var\(--hall-min-font\)", css))
    lines = [line for line in page.splitlines() if "className=" in line]
    assert any(set(re.findall(r"gc-[\w-]+", line)) & sized for line in lines)
    for line in lines:
        names = set(re.findall(r"gc-[\w-]+", line))
        if names & sized:
            assert names & raised, line
