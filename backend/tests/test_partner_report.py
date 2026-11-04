import io
from datetime import datetime, timedelta

from openpyxl import load_workbook
from sqlalchemy import select, update

from app import stages
from app.db import SessionLocal
from app.models import (Guest, LogoShow, Partner, Prize, PushMessage, PushSubscription, Redemption, ScoreEvent,
                        Submission, Task)
from tests.conftest import moderator_headers, staff_headers
from tests.test_live import TASKS, live, partner, typed
from tests.test_market import load, make_guest
from tests.test_moderation import decide
from tests.test_rating import freeze
from tests.test_submissions import ids, jpeg, send_photo, send_text
from tests.test_tasks import DUSHANBE, admin, clock  # noqa: F401 (fixtures)

KEY = "photo_delete_date"
PRIZES = [
    ["P1", "Термокружка", "Кока-Кола", 30, 5],
    ["P2", "Футболка", "Кока-Кола", 10, 3],
    ["P3", "Блокнот", "Алиф", 10, 100],
]


def setup(client, admin, clock) -> dict[str, int]:
    load(client, admin, tasks=TASKS, prizes=PRIZES)
    clock("09:30")
    return ids(client, admin)


def partner_id(name: str) -> int:
    with SessionLocal() as db:
        return db.scalar(select(Partner.id).where(Partner.name == name))


def report(client, admin, name: str = "Кока-Кола"):
    r = client.get(f"/api/admin/partners/{partner_id(name)}/report", headers=admin)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    return load_workbook(io.BytesIO(r.content))


def rows(ws) -> list[list]:
    return [list(r) for r in ws.iter_rows(values_only=True)]


def task_rows(wb) -> dict[str, list]:
    """«Сводка»'s task table: task text → [stage, completions, unique guests, rejected]."""
    table = rows(wb["Сводка"])
    start = next(i for i, r in enumerate(table) if r[0] == "Задание") + 1
    out = {}
    for r in table[start:]:
        out[r[0]] = r[1:5]
        if r[0] == "Итого":
            return out
    return out


def photo_links(wb) -> list[str]:
    return [r[2] for r in rows(wb["Фото"])[1:]]


def first_column(wb) -> list:
    return [r[0] for r in rows(wb["Сводка"])]


def open_photo(client, link: str):
    return client.get(link.replace("http://api.test", ""))


def set_date(client, admin, value: str):
    s = next(s for s in client.get("/api/admin/settings", headers=admin).json() if s["key"] == KEY)
    return client.put(f"/api/admin/settings/{KEY}", json={"value": value, "version": s["version"]}, headers=admin)


def submission_ids() -> list[int]:
    with SessionLocal() as db:
        return list(db.scalars(select(Submission.id).order_by(Submission.id)))


def test_report_needs_the_admin_password(client, admin, clock):
    setup(client, admin, clock)
    url = f"/api/admin/partners/{partner_id('Кока-Кола')}/report"
    guest = make_guest(client, "R-1", "Иван")
    for h in ({}, guest, staff_headers(client, "desk"), staff_headers(client, "stand"), moderator_headers(client)):
        assert client.get(url, headers=h).status_code == 401
    assert client.get("/api/admin/partners/999/report", headers=admin).status_code == 404


def test_three_sheets_with_cyrillic_and_the_partners_tasks_only(client, admin, clock):
    t = setup(client, admin, clock)
    ivan, anna = make_guest(client, "R-1", "Иван"), make_guest(client, "R-2", "Анна")
    send_photo(client, ivan, t["cola"])
    send_photo(client, anna, t["cola"])
    send_text(client, ivan, t["cola2"], "Вкусно")
    send_photo(client, ivan, t["selfie"])
    wb = report(client, admin)
    assert wb.sheetnames == ["Сводка", "Детали", "Фото"]
    assert first_column(wb)[:2] == ["Отчёт партнёра: Кока-Кола", "Пакет"]
    assert rows(wb["Сводка"])[1][1] == "MF Партнёр"
    assert task_rows(wb) == {
        "Фото с бутылкой": ["1. Начало", 2, 2, 0],
        "Отзыв о напитке": ["1. Начало", 1, 1, 0],
        "Итого": [None, 3, 2, 0],
    }
    # Another partner's and non-partner tasks are not in it
    assert not any("Селфи у входа" in str(v) or "Алиф" in str(v)
                   for ws in wb for r in ws.iter_rows(values_only=True) for v in r)


def test_totals_match_admin_live(client, admin, clock):
    t = setup(client, admin, clock)
    guests = [make_guest(client, f"R-{n}", f"Гость {n}") for n in range(1, 5)]
    for g in guests[:3]:
        send_photo(client, g, t["cola"])
    for g in guests[1:]:
        send_text(client, g, t["cola2"], "Вкусно")
    mod = moderator_headers(client)
    decide(client, mod, submission_ids()[0], "penalty")
    page = partner(live(client, admin), "Кока-Кола")
    total = task_rows(report(client, admin))["Итого"]
    assert (total[1], total[2]) == (page["completions"], page["guests"]) == (5, 3)


def test_a_rejected_photo_leaves_photos_for_the_rejected_column(client, admin, clock):
    t = setup(client, admin, clock)
    ivan, anna, oleg, olga = (make_guest(client, f"R-{n}", name)
                              for n, name in enumerate(["Иван", "Анна", "Олег", "Ольга"], 1))
    for g in (ivan, anna, oleg, olga):
        send_photo(client, g, t["cola"])
    # Waiting for a moderator: counted, but no photo listed
    wb = report(client, admin)
    assert task_rows(wb)["Фото с бутылкой"][1:] == [4, 4, 0]
    assert photo_links(wb) == []
    mod = moderator_headers(client)
    first, second, third, fourth = submission_ids()
    decide(client, mod, first, "accept")
    decide(client, mod, second, "bonus")
    decide(client, mod, third, "penalty")
    decide(client, mod, fourth, "retake")
    wb = report(client, admin)
    assert task_rows(wb)["Фото с бутылкой"][1:] == [2, 2, 2]
    with SessionLocal() as db:
        tokens = dict(db.execute(select(Submission.id, Submission.photo_token)).all())
    assert photo_links(wb) == [f"http://api.test/api/photos/{tokens[first]}",
                               f"http://api.test/api/photos/{tokens[second]}"]
    assert rows(wb["Фото"])[1][0] == "Фото с бутылкой"
    assert isinstance(rows(wb["Фото"])[1][1], datetime)
    # The rejected ones' links do not open
    for sid in (third, fourth):
        assert open_photo(client, f"http://api.test/api/photos/{tokens[sid]}").status_code == 404


def test_moving_a_task_to_another_partner_moves_its_numbers(client, admin, clock):
    t = setup(client, admin, clock)
    ivan, anna = make_guest(client, "R-1", "Иван"), make_guest(client, "R-2", "Анна")
    send_photo(client, ivan, t["cola"])
    send_photo(client, anna, t["cola"])
    decide(client, moderator_headers(client), submission_ids()[0], "accept")
    assert task_rows(report(client, admin))["Итого"][1] == 2
    assert task_rows(report(client, admin, "Алиф"))["Итого"][1] == 0
    with SessionLocal() as db:
        db.execute(update(Task).where(Task.id == t["cola"]).values(partner_id=partner_id("Алиф")))
        db.commit()
    cola, alif = report(client, admin), report(client, admin, "Алиф")
    assert "Фото с бутылкой" not in task_rows(cola) and task_rows(cola)["Итого"][1] == 0
    assert photo_links(cola) == []
    assert task_rows(alif)["Фото с бутылкой"][1:] == [2, 2, 0]
    assert task_rows(alif)["Итого"][1:] == [2, 2, 0]
    assert len(photo_links(alif)) == 1


def test_a_photo_link_shows_the_photo_until_the_deletion_date(client, admin, clock, monkeypatch):
    t = setup(client, admin, clock)
    ivan = make_guest(client, "R-1", "Иван")
    photo = jpeg(1600, 1200)
    send_photo(client, ivan, t["cola"], data=photo)
    decide(client, moderator_headers(client), submission_ids()[0], "accept")
    [link] = photo_links(report(client, admin))
    # No login
    r = open_photo(client, link)
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert r.headers["cache-control"] == "no-store"
    assert r.content == photo
    # Default: the last stage ends 13.12.2026 → links work through 11.01.2027
    monkeypatch.setattr(stages, "now", lambda: datetime(2027, 1, 11, 23, 59, tzinfo=DUSHANBE))
    assert open_photo(client, link).status_code == 200
    after = lambda: monkeypatch.setattr(  # noqa: E731
        stages, "now", lambda: datetime(2027, 1, 12, 0, 0, tzinfo=DUSHANBE))
    after()
    assert open_photo(client, link).status_code == 404
    # The admin's date wins, checked on every open. It is set during the forum: from 7 days before it, it is locked
    clock("12:00")
    assert set_date(client, admin, "2027-02-01").status_code == 200
    after()
    assert open_photo(client, link).status_code == 200
    clock("12:00")
    assert set_date(client, admin, "2027-01-12").status_code == 200
    after()
    assert open_photo(client, link).status_code == 404
    # A made-up token, or the submission's ID, opens nothing
    clock("12:00")
    assert set_date(client, admin, "").status_code == 200
    assert open_photo(client, "/api/photos/nope").status_code == 404
    assert open_photo(client, f"/api/photos/{submission_ids()[0]}").status_code == 404


def test_a_waiting_photo_is_not_listed_and_has_no_working_link(client, admin, clock):
    t = setup(client, admin, clock)
    ivan = make_guest(client, "R-1", "Иван")
    send_photo(client, ivan, t["cola"])
    # An accepted photo of a task without a partner has no working link either
    send_photo(client, ivan, t["selfie"])
    waiting, own = submission_ids()
    decide(client, moderator_headers(client), own, "accept")
    assert photo_links(report(client, admin)) == []
    with SessionLocal() as db:
        tokens = dict(db.execute(select(Submission.id, Submission.photo_token)).all())
    assert tokens[waiting] and tokens[own] and tokens[waiting] != tokens[own]
    assert len(tokens[waiting]) >= 32
    for sid in (waiting, own):
        assert open_photo(client, f"/api/photos/{tokens[sid]}").status_code == 404


def test_preliminary_until_the_ranking_is_frozen(client, admin, clock):
    t = setup(client, admin, clock)
    ivan = make_guest(client, "R-1", "Иван")
    send_photo(client, ivan, t["cola"])
    marked = lambda wb: any(str(v).startswith("Предварительные данные") for v in first_column(wb))  # noqa: E731
    assert marked(report(client, admin))
    assert freeze(client, admin).status_code == 200
    assert not marked(report(client, admin))
    assert freeze(client, admin, False).status_code == 200
    assert marked(report(client, admin))


def test_first_sheet_says_until_when_links_work(client, admin, clock):
    setup(client, admin, clock)
    assert "Ссылки на фото работают до 12.01.2027" in first_column(report(client, admin))
    assert set_date(client, admin, "2027-03-05").status_code == 200
    assert "Ссылки на фото работают до 05.03.2027" in first_column(report(client, admin))


def test_the_deletion_date_is_a_date_or_blank(client, admin):
    r = set_date(client, admin, "05.03.2027")
    assert (r.status_code, r.json()["detail"]["code"]) == (400, "bad_value")
    assert set_date(client, admin, "2027-03-05").json()["text"] == "2027-03-05"
    assert set_date(client, admin, " ").json()["text"] == ""


def test_summary_has_prizes_logo_time_and_push_reach(client, admin, clock):
    load(client, admin, tasks=TASKS, prizes=PRIZES)
    clock("14:30")
    with SessionLocal() as db:
        prizes = {p.code: p.id for p in db.scalars(select(Prize))}
    ivan, anna = make_guest(client, "R-1", "Иван", coins=100), make_guest(client, "R-2", "Анна", coins=100)
    client.post(f"/api/market/{prizes['P1']}/buy", headers=ivan)
    client.post(f"/api/market/{prizes['P1']}/buy", headers=anna)
    client.post(f"/api/market/{prizes['P2']}/buy", headers=ivan)
    client.post(f"/api/market/{prizes['P3']}/buy", headers=ivan)
    with SessionLocal() as db:
        code = db.scalar(select(Redemption.code).where(Redemption.prize_id == prizes["P1"]).limit(1))
    assert client.post(f"/api/stand/{code}/issue", headers=staff_headers(client, "stand")).status_code == 200
    # Before anything is recorded: zeros
    table = rows(report(client, admin)["Сводка"])
    assert ["Логотип на экране в зале", "Пакет", "Показов", "Секунд"] in [r[:4] for r in table]
    with SessionLocal() as db:
        cola, alif = partner_id("Кока-Кола"), partner_id("Алиф")
        at = stages.now()
        db.add_all([LogoShow(partner_id=cola, started_at=at, seconds=8),
                    LogoShow(partner_id=cola, started_at=at + timedelta(seconds=8), seconds=6),
                    LogoShow(partner_id=alif, started_at=at, seconds=8)])
        guest_id = db.scalar(select(ScoreEvent.guest_id).limit(1))
        db.add_all([PushSubscription(key="a", guest_id=guest_id, endpoint="https://push.test/a", p256dh="p", auth="x"),
                    PushSubscription(key="b", guest_id=guest_id, endpoint="https://push.test/b", p256dh="p", auth="x",
                                     active=False),
                    PushMessage(kind="one_off", at=at, title="Привет", sends=3, deliveries=2),
                    PushMessage(kind="one_off", at=at, title="Ещё", sends=2, deliveries=1)])
        db.commit()
    table = rows(report(client, admin)["Сводка"])
    i = next(n for n, r in enumerate(table) if r[0] == "Приз")
    assert [r[:3] for r in table[i:i + 4]] == [["Приз", "Куплено", "Выдано на стендах"], ["Термокружка", 2, 1],
                                               ["Футболка", 1, 0], ["Итого", 3, 1]]
    i = next(n for n, r in enumerate(table) if r[0] == "Логотип на экране в зале")
    assert table[i + 1][1:4] == ["MF Партнёр", 2, 14]
    i = next(n for n, r in enumerate(table) if r[0] == "Push-уведомления (весь форум)")
    assert table[i][1:3] == ["Подписаны", "Доставлено"]
    assert table[i + 1][1:3] == [1, 3]


def test_no_guest_names_anywhere_in_the_file(client, admin, clock):
    t = setup(client, admin, clock)
    ivan = make_guest(client, "R-1", "Вениамин")
    with SessionLocal() as db:
        db.execute(update(Guest).values(last_name="Запорожцев", company="Рогаикопыта", phone="+992900000001"))
        db.commit()
    send_photo(client, ivan, t["cola"])
    send_text(client, ivan, t["cola2"], "Вкусно")
    decide(client, moderator_headers(client), submission_ids()[0], "accept")
    wb = report(client, admin)
    assert len(photo_links(wb)) == 1
    found = [v for ws in wb for r in ws.iter_rows(values_only=True) for v in r
             if any(w in str(v) for w in ("Вениамин", "Запорожцев", "Рогаикопыта", "+992900000001", "R-1", "Вкусно"))]
    assert found == []


def test_details_by_task_and_local_hour(client, admin, clock):
    t = setup(client, admin, clock)
    ivan, anna, oleg = (make_guest(client, f"R-{n}", name) for n, name in enumerate(["Иван", "Анна", "Олег"], 1))
    for g in (ivan, anna, oleg):
        send_photo(client, g, t["cola"])
    send_text(client, ivan, t["cola2"], "Вкусно")
    decide(client, moderator_headers(client), submission_ids()[2], "penalty")
    # Stamp the completions and sends at 09:10, 09:50 and 10:05 local time
    times = [datetime(2026, 12, 13, 9, 10, tzinfo=DUSHANBE), datetime(2026, 12, 13, 9, 50, tzinfo=DUSHANBE),
             datetime(2026, 12, 13, 10, 5, tzinfo=DUSHANBE)]
    with SessionLocal() as db:
        guests = [s.guest_id for s in db.scalars(select(Submission).where(Submission.task_id == t["cola"])
                                                  .order_by(Submission.id))]
        for g, at in zip(guests, times):
            db.execute(update(ScoreEvent).where(ScoreEvent.guest_id == g, ScoreEvent.reason == f"task:{t['cola']}")
                       .values(created_at=at))
            db.execute(update(Submission).where(Submission.guest_id == g, Submission.task_id == t["cola"])
                       .values(created_at=at))
        db.execute(update(ScoreEvent).where(ScoreEvent.reason == f"task:{t['cola2']}").values(created_at=times[2]))
        db.commit()
    detail = rows(report(client, admin)["Детали"])
    assert detail[0] == ["Задание", "Этап", "Час", "Выполнений", "Уникальных участников", "Отклонено"]
    assert detail[1:] == [
        ["Фото с бутылкой", "1. Начало", datetime(2026, 12, 13, 9, 0), 2, 2, 0],
        ["Фото с бутылкой", "1. Начало", datetime(2026, 12, 13, 10, 0), 0, 0, 1],
        ["Отзыв о напитке", "1. Начало", datetime(2026, 12, 13, 10, 0), 1, 1, 0],
    ]


def test_text_that_looks_like_a_formula_is_written_as_text(client, admin, clock):
    load(client, admin, tasks=[typed("Действие", "promo", 1, "-20% на кофе у стенда", method="Текст",
                                     partner="@Кофе", package="MF Партнёр"),
                               typed("Действие", "promo2", 1, "Второе задание", method="Текст",
                                     partner="@Кофе", package="MF Партнёр")])
    # The task file itself would carry a leading = as a formula, so that text is set here
    with SessionLocal() as db:
        db.execute(update(Task).where(Task.text == "Второе задание").values(text="=1+1 приз"))
        db.commit()
    wb = report(client, admin, "@Кофе")
    assert first_column(wb)[0] == "Отчёт партнёра: @Кофе"
    assert "-20% на кофе у стенда" in task_rows(wb)
    assert "=1+1 приз" in task_rows(wb)
    assert all(c.data_type != "f" for ws in wb for r in ws.iter_rows() for c in r)
