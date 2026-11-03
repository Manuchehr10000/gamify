from sqlalchemy import select

from app import ledger
from app.db import SessionLocal
from app.models import Guest
from tests.conftest import moderator_headers
from tests.test_levels import feed, profile
from tests.test_moderation import decide, queue
from tests.test_quiz import load, play, questions, quiz
from tests.test_rating import hall, rating
from tests.test_submissions import ids, send_photo
from tests.test_tasks import admin, clock, guest  # noqa: F401 (fixtures)

LINK = "https://example.com"


def codes(badges) -> list[str]:
    return [b["code"] for b in badges]


def new(f) -> list[str]:
    """The badges a feed load shows the moment for."""
    return codes(f["new_badges"])


def held(p) -> list[str]:
    """The badges the profile shows in colour."""
    return [b["code"] for b in p["badges"] if b["held"]]


def row(code, text, type_="Действие", method="Фото", points=10, partner=None):
    return [code, 1, type_, text, points, None, partner, None, None, None, method,
            LINK if method == "Ссылка" else None, None, None]


def photos(n, method="Фото"):
    return [row(f"photo{i}", f"Фото {i}", method=method) for i in range(1, n + 1)]


def link(client, guest, task_id):
    r = client.post(f"/api/tasks/{task_id}/complete", headers=guest)
    assert r.json()["result"] == "awarded", r.text
    return r


def send(client, guest, task_id, text=None):
    r = send_photo(client, guest, task_id, text=text)
    assert r.json()["result"] == "awarded", r.text
    return r


def seed(points):
    with SessionLocal() as db:
        ledger.write(db, db.scalar(select(Guest.id)), f"seed{points}", "bonus", points, 0)
        db.commit()


def photo_hunter(client, admin, guest, clock):
    """Five photo tasks done, one of them «Фото+текст»; returns the task ids."""
    load(client, admin, photos(5) + [row("text1", "Фото с подписью", method="Фото+текст")], [])
    t = ids(client, admin)
    clock("09:30")
    for code in ("photo1", "photo2", "photo3", "photo4"):
        send(client, guest, t[code])
    return t


def test_fifth_photo_task_shows_the_badge_moment_once(client, admin, guest, clock):
    t = photo_hunter(client, admin, guest, clock)
    f = feed(client, guest)
    assert new(f) == []
    assert held(profile(client, guest)) == []
    send(client, guest, t["text1"], text="Подпись")
    assert new(feed(client, guest)) == ["photo_hunter"]
    # Not again after a reload
    assert new(feed(client, guest)) == []
    assert held(profile(client, guest)) == ["photo_hunter"]


def test_a_rejection_removes_the_badge_from_profile_and_ranking(client, admin, guest, clock):
    t = photo_hunter(client, admin, guest, clock)
    send(client, guest, t["photo5"])
    assert new(feed(client, guest)) == ["photo_hunter"]
    assert codes(rating(client, guest)["top"][0]["badges"]) == ["photo_hunter"]
    assert codes(hall(client)["top"][0]["badges"]) == ["photo_hunter"]
    mod = moderator_headers(client)
    assert decide(client, mod, queue(client, mod)["items"][0]["id"], "penalty").status_code == 200
    assert held(profile(client, guest)) == []
    assert codes(rating(client, guest)["top"][0]["badges"]) == []
    assert codes(hall(client)["top"][0]["badges"]) == []
    # Removed with no moment
    assert new(feed(client, guest)) == []


def test_earning_the_badge_again_shows_the_moment_again_even_without_a_feed_load_between(client, admin, guest, clock):
    t = photo_hunter(client, admin, guest, clock)
    send(client, guest, t["photo5"])
    assert new(feed(client, guest)) == ["photo_hunter"]
    mod = moderator_headers(client)
    decide(client, mod, queue(client, mod)["items"][0]["id"], "retake")
    # Five again straight away, the feed not opened in between
    send(client, guest, t["text1"], text="Подпись")
    assert new(feed(client, guest)) == ["photo_hunter"]


def test_a_photo_waiting_for_a_moderator_counts_and_an_accepted_one_still_does(client, admin, guest, clock):
    t = photo_hunter(client, admin, guest, clock)
    send(client, guest, t["photo5"])
    assert held(profile(client, guest)) == ["photo_hunter"]
    mod = moderator_headers(client)
    for item in queue(client, mod)["items"]:
        decide(client, mod, item["id"], "accept")
    assert held(profile(client, guest)) == ["photo_hunter"]


def test_five_perfect_quizzes_in_a_row_give_erudite_and_a_mistake_resets_the_run(client, admin, guest, clock):
    """4 perfect, one with a mistake, then 5 perfect: «Эрудит» only after the last five (piece 20)."""
    quizzes = [f"q{i}" for i in range(1, 11)]
    load(client, admin, [quiz(c, f"Квиз {c}", points=10) for c in quizzes],
         [q for c in quizzes for q in questions(c, 2)])
    t = ids(client, admin)
    clock("09:30")
    for c in quizzes[:4]:
        assert play(client, guest, t[c], right=2)["result"]["correct"] == 2
    # One wrong answer: finished, but with a mistake, so the run starts again
    assert play(client, guest, t["q5"], right=1)["result"]["correct"] == 1
    for c in quizzes[5:9]:
        play(client, guest, t[c], right=2)
    assert new(feed(client, guest)) == []
    play(client, guest, t["q10"], right=2)
    assert new(feed(client, guest)) == ["erudite"]


def test_three_tasks_of_one_partner_give_brand_friend_and_three_partners_dont(client, admin, guest, clock):
    rows = [row("a1", "Партнёр А 1", method="Ссылка", partner="Альфа"),
            row("b1", "Партнёр Б 1", method="Ссылка", partner="Бета"),
            row("c1", "Партнёр В 1", method="Ссылка", partner="Гамма"),
            row("a2", "Партнёр А 2", method="Ссылка", partner="Альфа"),
            row("a3", "Партнёр А 3", method="Ссылка", partner="Альфа")]
    load(client, admin, rows, [])
    t = ids(client, admin)
    clock("09:30")
    for code in ("a1", "b1", "c1"):
        link(client, guest, t[code])
    assert new(feed(client, guest)) == []
    link(client, guest, t["a2"])
    assert new(feed(client, guest)) == []
    link(client, guest, t["a3"])
    assert new(feed(client, guest)) == ["brand_friend"]


def test_a_moderators_bonus_on_a_crazy_photo_gives_forum_spirit(client, admin, guest, clock):
    load(client, admin, [row("crazy1", "Крейзи-фото", type_="Крейзи"), row("crazy2", "Ещё крейзи", type_="Крейзи"),
                         row("plain", "Обычное фото")], [])
    t = ids(client, admin)
    clock("09:30")
    mod = moderator_headers(client)
    send(client, guest, t["crazy1"])
    send(client, guest, t["plain"])
    items = {i["task"]: i["id"] for i in queue(client, mod)["items"]}
    # A bonus on a task that isn't Крейзи, or a Крейзи photo only accepted, doesn't count
    decide(client, mod, items["Обычное фото"], "bonus")
    decide(client, mod, items["Крейзи-фото"], "accept")
    assert new(feed(client, guest)) == []
    send(client, guest, t["crazy2"])
    decide(client, mod, queue(client, mod)["items"][0]["id"], "bonus")
    assert new(feed(client, guest)) == ["forum_spirit"]


def test_every_networking_task_gives_networker(client, admin, guest, clock):
    load(client, admin, [row("net1", "Селфи с другом", type_="Нетворкинг"),
                         row("net2", "Селфи с новым знакомым", type_="Нетворкинг", method="Ссылка"),
                         row("other", "Другое", method="Ссылка")], [])
    t = ids(client, admin)
    clock("09:30")
    send(client, guest, t["net1"])
    link(client, guest, t["other"])
    assert new(feed(client, guest)) == []
    link(client, guest, t["net2"])
    assert new(feed(client, guest)) == ["networker"]


def test_no_networking_tasks_in_the_file_gives_nobody_networker(client, admin, guest, clock):
    load(client, admin, [row("other", "Другое", method="Ссылка")], [])
    clock("09:30")
    link(client, guest, ids(client, admin)["other"])
    assert held(profile(client, guest)) == []


def test_a_level_and_a_badge_from_the_same_task_show_both_moments(client, admin, guest, clock):
    t = photo_hunter(client, admin, guest, clock)
    seed(100)
    assert feed(client, guest)["new_level"] == "Участник"
    # 140 → 150 and the fifth photo with one send
    send(client, guest, t["photo5"])
    f = feed(client, guest)
    assert (f["new_level"], new(f)) == ("Актив", ["photo_hunter"])
    f = feed(client, guest)
    assert (f["new_level"], new(f)) == (None, [])


def test_profile_lists_held_badges_in_order(client, admin, guest, clock):
    load(client, admin, photos(5) + [row("net1", "Нетворкинг", type_="Нетворкинг", method="Ссылка")], [])
    t = ids(client, admin)
    clock("09:30")
    link(client, guest, t["net1"])
    for i in range(1, 6):
        send(client, guest, t[f"photo{i}"])
    assert held(profile(client, guest)) == ["photo_hunter", "networker"]
    assert new(feed(client, guest)) == ["photo_hunter", "networker"]
