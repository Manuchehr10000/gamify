import io
import os
from threading import Barrier, Thread

import pytest
from alembic import command
from alembic.config import Config
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import func, select, text, update

from app import accounts, config, jobs
from app.auth import require_role
from app.db import SessionLocal, engine
from app.models import Guest, JobRun, Partner, Prize, ScoreEvent, Session, Stage, Staff, Task
from tests.conftest import moderator_headers, staff_headers
from tests.test_market import buy, make_guest, market
from tests.test_market import load as load_market
from tests.test_moderation import decide, queue, setup
from tests.test_qr_tasks import load, qr_codes, row, scan, totals
from tests.test_submissions import send_photo, send_text
from tests.test_tasks import admin, clock, guest  # noqa: F401 (fixtures)

ALEMBIC = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))


def events() -> list[ScoreEvent]:
    with SessionLocal() as db:
        return list(db.scalars(select(ScoreEvent).order_by(ScoreEvent.id)))


def balance(client, admin) -> list[dict]:
    r = client.get("/api/admin/balance-check", headers=admin)
    assert r.status_code == 200, r.text
    return r.json()


def stored(guest_id: int = 1) -> tuple[int, int]:
    with SessionLocal() as db:
        g = db.get(Guest, guest_id)
        return g.points, g.coins


# ---------------------------------------------------------------- the points and coins record

def test_bonus_rejections_and_a_purchase_each_write_one_row_and_totals_match(client, admin, guest, clock):
    t = setup(client, admin, clock)
    send_photo(client, guest, t["photo1"])
    send_text(client, guest, t["text1"], "Отзыв")
    send_photo(client, guest, t["both1"], text="Стих")
    mod = moderator_headers(client)
    items = {i["task"]: i["id"] for i in queue(client, mod)["items"]}
    for task, action in (("Селфи у входа", "bonus"), ("Напишите отзыв", "retake"), ("Стих и фото", "penalty")):
        before = len(events())
        assert decide(client, mod, items[task], action).status_code == 200
        added = events()[before:]
        assert [e.action for e in added] == [action]
        assert stored() == totals(client, guest)
        assert balance(client, admin) == []
    bonus, retake, penalty = events()[-3:]
    assert (bonus.points, bonus.base_points, bonus.multiplier) == (8, 8, 1)
    # A penalty takes back without reversing: the award still counts as done
    assert (penalty.points, penalty.reverses_id) == (-20, None)
    assert retake.reverses_id is not None


def test_a_purchase_writes_one_row_and_reads_the_stored_total(client, admin, clock):
    load_market(client, admin, tasks=[])
    g = make_guest(client, "R-1", "Иван", coins=40)
    clock("14:30")
    before = len(events())
    assert buy(client, g, market(client, g), "Термокружка").status_code == 200
    (row_,) = events()[before:]
    assert (row_.action, row_.reason, row_.points, row_.coins) == ("buy", f"buy:{row_.reason[4:]}", 0, -30)
    assert stored() == (0, 10) and market(client, g)["coins"] == 10
    # The coin check reads the stored total: a total lowered by hand blocks the next buy
    with SessionLocal() as db:
        db.execute(update(Guest).values(coins=5))
        db.commit()
    assert buy(client, g, market(client, g), "Блокнот").json()["detail"] == "not_enough_coins"


def test_rows_carry_base_points_multiplier_stage_and_action(client, admin, guest, clock):
    load(client, admin, [row("qr1", 1, "QR у стенда", method="QR")])
    clock("09:30")
    scan(client, guest, qr_codes(client, admin)["qr1"])
    award = events()[-1]
    with SessionLocal() as db:
        stage1 = db.scalar(select(Stage.id).where(Stage.number == 1))
    assert (award.action, award.base_points, award.multiplier, award.points, award.stage_id) == \
        ("task", 15, 1, 15, stage1)


def test_points_are_base_times_multiplier_rounded_half_up():
    from decimal import Decimal

    from app.ledger import points_of
    assert points_of(15, Decimal(1)) == 15
    assert points_of(15, Decimal("1.5")) == 23
    assert points_of(5, Decimal("1.3")) == 7


def test_retake_keeps_the_award_reverses_it_and_pays_the_new_submission(client, admin, guest, clock):
    t = setup(client, admin, clock)
    base = totals(client, guest)
    send_photo(client, guest, t["photo1"])
    award = events()[-1]
    mod = moderator_headers(client)
    decide(client, mod, queue(client, mod)["items"][0]["id"], "retake")
    reversal = events()[-1]
    assert award.id in [e.id for e in events()]
    assert (reversal.reverses_id, reversal.action, reversal.points, reversal.coins) == \
        (award.id, "retake", -award.points, -award.coins)
    assert totals(client, guest) == base
    card = client.get(f"/api/tasks/{t['photo1']}", headers=guest).json()
    assert card["done"] is False
    # Sent again: paid once more, and the queue shows it once with the new award's points
    assert send_photo(client, guest, t["photo1"]).json()["result"] == "awarded"
    assert totals(client, guest) == (base[0] + 15, base[1] + 15)
    assert send_photo(client, guest, t["photo1"]).json()["result"] == "already"
    assert [(i["task"], i["points"]) for i in queue(client, mod)["items"]] == [("Селфи у входа", 15)]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).where(ScoreEvent.reason == f"task:{t['photo1']}")) == 2
    assert balance(client, admin) == []
    # The profile shows the task once, as before
    history = client.get("/api/profile", headers=guest).json()["history"]
    assert [e["text"] for e in history if e["kind"] == "task"] == ["Селфи у входа"]


def test_a_double_scan_writes_one_award(client, admin, guest, clock):
    load(client, admin, [row("qr1", 1, "QR у стенда", method="QR")])
    code = qr_codes(client, admin)["qr1"]
    clock("09:30")
    barrier = Barrier(2)
    results = []

    def go():
        barrier.wait()
        results.append(scan(client, guest, code).json()["result"])

    threads = [Thread(target=go) for _ in range(2)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert sorted(results) == ["already", "awarded"]
    assert scan(client, guest, code).json()["result"] == "already"
    assert len([e for e in events() if e.reason.startswith("task:")]) == 1


def test_a_penalty_drops_live_completions_by_one(client, admin, guest, clock):
    t = setup(client, admin, clock)
    send_photo(client, guest, t["photo1"])
    send_photo(client, guest, t["partner"])
    by_type = lambda: sum(c["completions"] for c in client.get("/api/admin/live", headers=admin).json()["by_type"])  # noqa: E731
    assert by_type() == 2
    mod = moderator_headers(client)
    sid = next(i["id"] for i in queue(client, mod)["items"] if i["task"] == "Селфи у входа")
    decide(client, mod, sid, "penalty")
    assert by_type() == 1
    # The task stays closed for the guest
    assert client.get(f"/api/tasks/{t['photo1']}", headers=guest).json()["done"] is True


def test_balance_check_lists_only_guests_whose_totals_differ(client, admin, guest, clock):
    load(client, admin, [row("qr1", 1, "QR у стенда", method="QR")])
    clock("09:30")
    scan(client, guest, qr_codes(client, admin)["qr1"])
    assert balance(client, admin) == []
    with SessionLocal() as db:
        db.execute(update(Guest).values(points=Guest.points + 7, last_name="Петров"))
        db.commit()
    points, coins = stored()
    assert balance(client, admin) == [{"name": "Иван Петров", "points": points, "points_sum": points - 7,
                                       "coins": coins, "coins_sum": coins}]
    # It only reports
    assert stored() == (points, coins)


def test_balance_check_is_for_the_admin(client, admin, guest):
    for h in ({}, guest, moderator_headers(client), staff_headers(client, "desk")):
        assert client.get("/api/admin/balance-check", headers=h).status_code == 401


# ---------------------------------------------------------------- partners

def test_a_new_partner_name_in_the_tasks_file_adds_a_partner(client, admin):
    load(client, admin, [row("a", 1, "Задание Альфы", partner="Альфа", package="Хедлайнер"),
                         row("b", 1, "Ещё Альфы", partner="Альфа"),
                         row("c", 1, "Без партнёра")])
    with SessionLocal() as db:
        (alfa,) = db.scalars(select(Partner))
        assert (alfa.name, alfa.package, alfa.logo, alfa.active) == ("Альфа", "headliner", None, True)
        links = dict(db.execute(select(Task.code, Task.partner_id)).all())
    assert links == {"a": alfa.id, "b": alfa.id, "c": None}
    # Uploading again matches by name: no second partner
    load(client, admin, [row("a", 1, "Задание Альфы", partner="Альфа", package="Хедлайнер")])
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Partner)) == 1


def test_two_packages_for_one_partner_refuse_the_file(client, admin):
    r = load(client, admin, [row("a", 1, "Первое", partner="Альфа", package="Хедлайнер"),
                             row("b", 1, "Второе", partner="Альфа", package="MF Партнёр")])
    assert r["failed"] == [{"sheet": "Задания", "row": 3, "reason": "package_conflict"}]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Partner)) == 0


def test_prizes_match_or_add_partners_by_name_without_a_package(client, admin):
    load_market(client, admin, tasks=[["t", 1, "Действие", "Задание Coca-Cola", 10, None, "Coca-Cola",
                                       "MF Партнёр", None, None, None, None]])
    with SessionLocal() as db:
        partners = {p.name: p for p in db.scalars(select(Partner))}
        assert {n: p.package for n, p in partners.items()} == {"Coca-Cola": "mf_partner", "Alif": "", "TAG": ""}
        prize = db.scalar(select(Prize).where(Prize.code == "P1"))
        assert prize.partner_id == partners["Coca-Cola"].id


def test_download_writes_partner_and_package_from_the_partner(client, admin):
    load(client, admin, [row("a", 1, "Задание Альфы", partner="Альфа", package="Хедлайнер"),
                         row("c", 1, "Без партнёра")])
    ws = load_workbook(io.BytesIO(client.get("/api/admin/tasks/export", headers=admin).content))["Задания"]
    rows = {r[0]: (r[6], r[7]) for r in ws.iter_rows(min_row=2, values_only=True)}
    assert rows["a"] == ("Альфа", "Хедлайнер")
    assert rows["c"][1] is None and not rows["c"][0]


def test_migration_builds_partners_totals_and_staff_from_what_was_there(client):
    """Down to the schema before this piece, data in the old shape, then up again."""
    command.downgrade(ALEMBIC, "0010")
    try:
        with engine.begin() as c:
            c.execute(text("INSERT INTO stages (id, number, name, starts_at, ends_at, message, market) VALUES "
                           "(1, 1, 'Начало', now(), now() + interval '1 hour', '', false)"))
            c.execute(text(
                "INSERT INTO tasks (id, code, stage_id, type, text, points, coins, coins_from_rule, partner_name, "
                "partner_package, method, link, position, active) VALUES "
                "(1, 'a', 1, 'action', 'Альфа 1', 10, 15, true, 'Альфа', 'headliner', '', '', 0, true), "
                "(2, 'b', 1, 'action', 'Альфа 2', 10, 15, true, 'Альфа', 'headliner', '', '', 1, true), "
                "(3, 'c', 1, 'action', 'Сама', 10, 10, true, '', '', '', '', 2, true)"))
            c.execute(text("INSERT INTO prizes (id, code, name, partner, price, quantity, position, active) VALUES "
                           "(1, 'P1', 'Кружка', 'Бета', 30, 5, 0, true)"))
            c.execute(text("INSERT INTO guests (id, code, first_name, last_name, phone, company) VALUES (1, 'abc', 'Иван', '', '', '')"))
            c.execute(text("INSERT INTO score_events (guest_id, reason, points, coins) VALUES "
                           "(1, 'forum_arrival', 10, 0), (1, 'task:1', 10, 15), (1, 'buy:1', 0, -30)"))
    finally:
        command.upgrade(ALEMBIC, "head")
        with SessionLocal() as db:
            accounts.seed_if_empty(db)
    with SessionLocal() as db:
        partners = {p.name: p.package for p in db.scalars(select(Partner))}
        assert partners == {"Альфа": "headliner", "Бета": ""}
        assert stored() == (20, -15)
        assert [(e.action, e.base_points, e.multiplier) for e in db.scalars(select(ScoreEvent).order_by(ScoreEvent.id))] \
            == [("arrival", 10, 1), ("task", 10, 1), ("buy", 0, 1)]
    admin = staff_headers(client, "admin")
    assert balance(client, admin) == []
    ws = load_workbook(io.BytesIO(client.get("/api/admin/tasks/export", headers=admin).content))["Задания"]
    rows = {r[0]: (r[6] or "", r[7]) for r in ws.iter_rows(min_row=2, values_only=True)}
    assert rows == {"a": ("Альфа", "Хедлайнер"), "b": ("Альфа", "Хедлайнер"), "c": ("", None)}


def test_migration_stops_on_a_partner_with_two_packages_and_names_it(client):
    command.downgrade(ALEMBIC, "0010")
    try:
        with engine.begin() as c:
            c.execute(text("INSERT INTO stages (id, number, name, starts_at, ends_at, message, market) VALUES "
                           "(1, 1, 'Начало', now(), now() + interval '1 hour', '', false)"))
            c.execute(text(
                "INSERT INTO tasks (id, code, stage_id, type, text, points, coins, coins_from_rule, partner_name, "
                "partner_package, method, link, position, active) VALUES "
                "(1, 'a', 1, 'action', 'Альфа 1', 10, 15, true, 'Альфа', 'headliner', '', '', 0, true), "
                "(2, 'b', 1, 'action', 'Альфа 2', 10, 15, true, 'Альфа', 'general', '', '', 1, true)"))
        with pytest.raises(RuntimeError, match="Альфа"):
            command.upgrade(ALEMBIC, "head")
        with engine.begin() as c:
            assert c.scalar(text("SELECT version_num FROM alembic_version")) == "0010"
            c.execute(text("UPDATE tasks SET partner_package = 'headliner'"))
    finally:
        command.upgrade(ALEMBIC, "head")
        with SessionLocal() as db:
            accounts.seed_if_empty(db)
    with SessionLocal() as db:
        assert {p.name: p.package for p in db.scalars(select(Partner))} == {"Альфа": "headliner"}


# ---------------------------------------------------------------- staff access

def test_the_old_admin_password_logs_in_as_the_first_named_admin(client):
    r = client.post("/api/staff/login", json={"role": "admin", "secret": "admin-pass"})
    assert r.status_code == 200
    with SessionLocal() as db:
        s = db.scalar(select(Session).where(Session.role == "admin"))
        account = db.get(Staff, s.staff_id)
    assert (account.name, account.role) == ("Администратор", "admin")


def test_old_pins_log_in_and_only_their_hashes_are_stored(client):
    for role, pin in (("desk", "1234"), ("stand", "5678")):
        assert client.post("/api/staff/login", json={"role": role, "secret": pin}).status_code == 200
        assert client.post("/api/staff/login", json={"role": role, "secret": pin + "0"}).status_code == 401
    for pin, name in (("1111", "Модератор 1"), ("2222", "Модератор 2"), ("3333", "Модератор 3")):
        assert client.post("/api/moderator/login", json={"secret": pin}).json()["name"] == name
    secrets_ = ["admin-pass", "1234", "5678", "1111", "2222", "3333"]
    with SessionLocal() as db:
        accounts = list(db.scalars(select(Staff)))
        sessions = list(db.scalars(select(Session).where(Session.role != "guest")))
    assert sorted(a.role for a in accounts) == ["admin", "desk", "moderator", "moderator", "moderator", "stand"]
    for a in accounts:
        assert a.secret_hash.startswith("$2b$")
        assert not any(s in a.secret_hash for s in secrets_)
    # Each session names the account acting
    assert all(s.staff_id is not None for s in sessions)


def test_staff_secrets_are_seeded_once_then_the_environment_is_ignored(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "new-pass")
    with SessionLocal() as db:
        accounts.seed_if_empty(db)
        assert db.scalar(select(func.count()).select_from(Staff)) == 6
    assert client.post("/api/staff/login", json={"role": "admin", "secret": "new-pass"}).status_code == 401
    assert client.post("/api/staff/login", json={"role": "admin", "secret": "admin-pass"}).status_code == 200


def test_an_empty_staff_table_is_seeded_at_start_and_warns_when_nothing_is_set(client, monkeypatch, caplog):
    with engine.begin() as c:
        c.execute(text("TRUNCATE staff RESTART IDENTITY CASCADE"))
    # alembic's fileConfig in the migration tests turns off loggers made before it; the app's start runs after it
    monkeypatch.setattr(accounts.log, "disabled", False)
    try:
        for name, value in (("ADMIN_PASSWORD", ""), ("DESK_PIN", ""), ("STAND_PIN", ""), ("MODERATORS", [])):
            monkeypatch.setattr(config, name, value)
        with SessionLocal() as db:
            accounts.seed_if_empty(db)
            assert db.scalar(select(func.count()).select_from(Staff)) == 0
        assert "не заданы" in caplog.text
        # A later start with the values set fills the table
        monkeypatch.undo()
        with TestClient(client.app):
            pass
        assert client.post("/api/staff/login", json={"role": "admin", "secret": "admin-pass"}).status_code == 200
    finally:
        monkeypatch.undo()
        with SessionLocal() as db:
            accounts.seed_if_empty(db)


def test_a_moderator_calling_admin_actions_is_refused(client, admin):
    mod = moderator_headers(client)
    for method, path in (("GET", "/api/admin/live"), ("GET", "/api/admin/tasks/export"),
                         ("POST", "/api/admin/stages/advance"), ("GET", "/api/admin/guests/export"),
                         ("POST", "/api/admin/rating/freeze"), ("GET", "/api/admin/balance-check")):
        kw = {"json": {"frozen": None}} if path.endswith("freeze") else {}
        assert client.request(method, path, headers=mod, **kw).status_code == 401, path
    # Nor the desk or the stand, while the admin gets in
    for h in (staff_headers(client, "desk"), staff_headers(client, "stand")):
        assert client.get("/api/admin/live", headers=h).status_code == 401
    assert client.get("/api/admin/live", headers=admin).status_code == 200


def test_a_session_of_a_removed_account_is_refused(client, admin):
    with SessionLocal() as db:
        db.execute(update(Session).where(Session.role == "admin").values(staff_id=None))
        db.commit()
    assert client.get("/api/admin/live", headers=admin).status_code == 401


def test_require_role_can_let_moderators_in_beside_the_admin(client, admin):
    """What piece 18's hall screen switches will use."""
    hall = FastAPI()

    @hall.post("/switch", dependencies=[Depends(require_role("admin", "moderator"))])
    def switch() -> str:
        return "ok"

    c = TestClient(hall)
    for h, code in ((moderator_headers(client), 200), (admin, 200), (staff_headers(client, "desk"), 401), ({}, 401)):
        assert c.post("/switch", headers=h).status_code == code


# ---------------------------------------------------------------- job runner

def run(client, secret="jobs-secret"):
    return client.post("/api/jobs/run", headers={"X-Jobs-Secret": secret} if secret is not None else {})


def runs() -> list[JobRun]:
    with SessionLocal() as db:
        return list(db.scalars(select(JobRun).order_by(JobRun.id)))


def test_each_registered_job_runs_and_is_logged(client, monkeypatch):
    done = []
    monkeypatch.setattr(jobs, "JOBS", [("first", lambda db: done.append(1) or ""), ("second", lambda db: done.append(2) or "")])
    r = run(client)
    assert r.status_code == 200, r.text
    assert done == [1, 2]
    assert [(j.job, j.result, j.error) for j in runs()] == [("first", "ok", ""), ("second", "ok", "")]
    assert all(j.finished_at is not None and j.finished_at >= j.started_at for j in runs())


def test_a_failing_job_is_logged_and_the_next_still_runs(client, monkeypatch):
    def broken(db):
        db.execute(update(Guest).values(first_name="испорчено"))
        raise RuntimeError("нет связи")

    monkeypatch.setattr(jobs, "JOBS", [("broken", broken), ("fine", lambda db: "")])
    assert run(client).status_code == 200
    (failed, ok) = runs()
    assert (failed.job, failed.result, failed.error) == ("broken", "failed", "RuntimeError: нет связи")
    assert (ok.job, ok.result) == ("fine", "ok")


def test_a_run_while_the_previous_holds_the_lock_is_skipped(client, monkeypatch):
    done = []
    monkeypatch.setattr(jobs, "JOBS", [("first", lambda db: done.append(1) or "")])
    with engine.connect() as c:
        c.execute(text("SELECT pg_advisory_lock(:key)"), {"key": jobs.RUN_LOCK})
        try:
            assert run(client).json()[0]["result"] == "skipped"
        finally:
            c.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": jobs.RUN_LOCK})
    assert done == []
    assert [j.result for j in runs()] == ["skipped"]
    run(client)
    assert done == [1]


def test_a_run_left_open_by_a_dead_process_is_closed_as_failed(client, monkeypatch):
    monkeypatch.setattr(jobs, "JOBS", [("first", lambda db: "")])
    with SessionLocal() as db:
        db.add(JobRun(job="first", result=""))
        db.commit()
    assert run(client).status_code == 200
    assert [(j.result, j.error, j.finished_at is not None) for j in runs()] == \
        [("failed", "прерван", True), ("ok", "", True)]


@pytest.mark.parametrize("secret", [None, "", "wrong"])
def test_the_job_endpoint_needs_the_workers_secret(client, monkeypatch, secret):
    done = []
    monkeypatch.setattr(jobs, "JOBS", [("first", lambda db: done.append(1) or "")])
    assert run(client, secret).status_code == 401
    assert done == [] and runs() == []


def test_without_jobs_secret_set_every_call_is_refused(client, monkeypatch):
    monkeypatch.setattr(config, "JOBS_SECRET", "")
    assert run(client, "").status_code == 401
    assert run(client, "jobs-secret").status_code == 401
