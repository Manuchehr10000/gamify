"""Piece 015 (console look: quizzes and rewards) changes only the look of the quiz, market, rating and profile screens and the level and badge moment.
These pin what those screens draw from the API, one test per «How to check it» line that code can check, and the
language-file words the new look adds."""
import json
from pathlib import Path

from tests.test_badges import ids
from tests.test_levels import feed, profile, top_up
from tests.test_market import buy, make_guest, market, market_file, prize
from tests.test_qr_tasks import qr_codes, scan
from tests.test_quiz import answer, at, card, play, qr, questions, quiz, start  # noqa: F401 (fixtures)
from tests.test_quiz import load as load_quiz
from tests.test_rating import freeze, guests, login, rating, score
from tests.test_tasks import admin, clock, guest, upload  # noqa: F401 (fixtures)

RU = json.loads((Path(__file__).parents[2] / "frontend" / "src" / "locales" / "ru.json").read_text("utf-8"))


def load_market(client, admin, prizes):
    r = upload(client, admin, market_file(prizes=prizes))
    assert r.status_code == 200, r.text


# Quiz

def test_a_started_quiz_gives_question_1_of_n_with_its_answers_and_the_countdown(client, admin, guest, at):
    load_quiz(client, admin, [quiz("B1", "Блиц", timer=60)],
              questions("B1", 4) + [["B1", 5, "Вопрос 5", "Да", "Нет", None, None, 1]])
    at("09:30:00")
    s = start(client, guest, card(client, guest, "Блиц")["id"]).json()
    # «Вопрос 1 из 5»: the screen shows answered + 1 of total
    assert (s["answered"] + 1, s["total"]) == (1, 5)
    assert s["question"]["text"] == "Вопрос 1"
    assert len(s["question"]["options"]) == 4
    assert s["seconds_left"] == 60


def test_two_answer_question_gives_two_lettered_buttons(client, admin, guest, at):
    load_quiz(client, admin, [quiz("Q1", "Да или нет")], [["Q1", 1, "Вопрос", "Да", "Нет", None, None, 1]])
    at("09:30:00")
    s = start(client, guest, card(client, guest, "Да или нет")["id"]).json()
    assert sorted(o["text"] for o in s["question"]["options"]) == ["Да", "Нет"]
    # A quiz with no timer shows no countdown
    assert s["seconds_left"] is None


def test_the_countdown_reaches_10_seconds_from_the_server(client, admin, guest, at):
    load_quiz(client, admin, [quiz("B1", "Блиц", timer=60)], questions("B1", 5))
    at("09:30:00")
    task_id = card(client, guest, "Блиц")["id"]
    start(client, guest, task_id)
    at("09:30:50")
    # 10 seconds or less: the screen turns the timer red and says «Мало времени»
    assert start(client, guest, task_id).json()["seconds_left"] == 10
    assert RU["quiz"]["lowTime"] == "Мало времени"


def test_time_up_gives_3_of_5_with_points_and_coins(client, admin, guest, at):
    load_quiz(client, admin, [quiz("B1", "Блиц", timer=60)], questions("B1", 5))
    at("09:30:00")
    task_id = card(client, guest, "Блиц")["id"]
    start(client, guest, task_id)
    for q in (1, 2, 3):
        answer(client, guest, task_id, q, 1)
    at("09:31:00")
    r = client.post(f"/api/quiz/{task_id}/finish", headers=guest).json()["result"]
    assert r == {"correct": 3, "total": 5, "points": 30, "coins": 30, "speed": None}
    assert RU["quiz"]["timeUp"] == "Время вышло"
    assert RU["quiz"]["result"] == "{{correct}} из {{total}} · {{points}}, {{coins}}"


def test_a_quiz_before_the_check_in_is_refused_with_its_reason(client, admin, guest, at):
    load_quiz(client, admin, [quiz("M1", "Мастер-класс", requires="HALL"), qr("HALL", "Отметиться в зале")],
              questions("M1", 2))
    at("09:30:00")
    r = start(client, guest, card(client, guest, "Мастер-класс")["id"])
    # The screen turns 403 into one message card with a lock and «Сначала отметьтесь в зале»
    assert (r.status_code, r.json()["detail"]) == (403, "check_in_first")
    assert RU["quiz"]["checkInFirst"] == "Сначала отметьтесь в зале"
    assert scan(client, guest, qr_codes(client, admin)["HALL"]).status_code == 200


# Market

def test_48_coins_and_a_60_coin_prize_is_12_short_and_cant_be_bought(client, admin, clock):
    load_market(client, admin, [["P1", "Худи", "Alif", 60, 3]])
    g = make_guest(client, "R-1", "Иван", coins=48)
    clock("14:30")
    m = market(client, g)
    hoodie = prize(m, "Худи")
    # The card shows a disabled «Не хватает 12 монет»
    assert (m["open"], m["coins"], hoodie["price"], hoodie["left"], hoodie["code"]) == (True, 48, 60, 3, None)
    assert hoodie["price"] - m["coins"] == 12
    assert RU["market"]["short_many"] == "Не хватает {{count}} монет"
    r = buy(client, g, m, "Худи")
    assert (r.status_code, r.json()["detail"]) == (409, "not_enough_coins")


def test_a_bought_prize_shows_its_code_then_received_after_the_stand(client, admin, clock):
    load_market(client, admin, [["P1", "Термокружка", "Coca-Cola", 30, 5]])
    g = make_guest(client, "R-1", "Иван", coins=100)
    clock("14:30")
    r = buy(client, g, market(client, g), "Термокружка")
    assert r.status_code == 200, r.text
    mug = prize(r.json(), "Термокружка")
    # Waiting at the stand: the QR and «Код: …»
    assert len(mug["code"]) == 6 and mug["issued_at"] is None
    stand = {"Authorization": "Bearer " + client.post("/api/staff/login", json={"role": "stand", "secret": "5678"})
             .json()["token"]}
    assert client.post(f"/api/stand/{mug['code']}/issue", headers=stand).json()["result"] == "issued"
    # «Получено»
    assert prize(market(client, g), "Термокружка")["issued_at"] is not None


def test_a_closed_market_says_when_it_opens(client, admin, clock):
    load_market(client, admin, [["P1", "Термокружка", "Coca-Cola", 30, 5]])
    g = make_guest(client, "R-1", "Иван", coins=100)
    clock("11:00")
    m = market(client, g)
    # «Маркет откроется в 14:00» and every «Обменять» locked
    assert m["open"] is False and m["opens_at"].startswith("2026-12-13T14:00:00+05:00")
    assert (buy(client, g, m, "Термокружка").json()["detail"]) == "market_closed"


# Rating

def test_37th_place_sees_the_top_list_and_a_card_with_place_and_points(client):
    g = guests("ID;Имя\n" + "".join(f"R-{i};Гость{i}\n" for i in range(1, 41)))
    for i in range(1, 41):
        score(g[f"Гость{i}"], 1000 - i * 10, i)
    body = rating(client, login(client, g["Гость37"]))
    assert len(body["top"]) == 20 and not any(r["me"] for r in body["top"])
    # «Вы на 37-м месте · 630 баллов»: place and points only
    assert body["me"] == {"place": 37, "points": 630}


def test_my_row_in_the_top_list_is_marked_me(client):
    g = guests("ID;Имя\nR-1;Анна\nR-2;Борис\n")
    score(g["Анна"], 120, 1)
    score(g["Борис"], 90, 2)
    body = rating(client, login(client, g["Борис"]))
    assert [r["me"] for r in body["top"]] == [False, True]
    assert all({"level", "badges"} <= set(r) for r in body["top"])
    assert RU["rating"]["you"] == "Вы"


def test_frozen_results_say_so_above_the_list(client, admin):
    g = guests("ID;Имя\nR-1;Анна\n")
    score(g["Анна"], 120, 1)
    assert freeze(client, admin).status_code == 200
    assert rating(client, login(client, g["Анна"]))["frozen"] is True
    assert RU["rating"]["frozen"] == "Итоги зафиксированы"


# Profile and the moment

def test_profile_lists_held_badges_and_the_screen_greys_the_rest(client, admin, guest, clock):
    assert [b["code"] for b in profile(client, guest)["badges"] if b["held"]] == []
    codes = [f"q{i}" for i in range(1, 6)]
    load_quiz(client, admin, [quiz(c, f"Квиз {c}", points=10) for c in codes], [q for c in codes for q in questions(c, 2)])
    t = ids(client, admin)
    clock("09:30")
    for c in codes:
        play(client, guest, t[c], right=2)
    shelf = profile(client, guest)["badges"]
    assert [b["code"] for b in shelf if b["held"]] == ["erudite"]
    # Every badge is on the shelf; the greyed ones' condition is written from each rule type's words
    assert [b["code"] for b in shelf] == ["photo_hunter", "networker", "erudite", "brand_friend", "forum_spirit"]
    rules = RU["badges"]["rules"]
    assert all(rules.get(b["rule"]) or rules.get(f'{b["rule"]}_many') for b in shelf)
    assert (RU["badges"]["held"], RU["badges"]["notHeld"]) == ("получен", "не получен")


def test_a_30_coin_purchase_is_minus_30_in_the_history_once(client, admin, clock):
    load_market(client, admin, [["P1", "Термокружка", "Coca-Cola", 30, 5]])
    g = make_guest(client, "R-1", "Иван", coins=100)
    clock("14:30")
    assert buy(client, g, market(client, g), "Термокружка").status_code == 200
    bought = [e for e in profile(client, g)["history"] if e["kind"] == "buy"]
    # The API sends the coins spent below zero; the screen writes the one minus itself: «−30 монет»
    assert [(e["text"], e["coins"]) for e in bought] == [("Термокружка", -30)]
    assert RU["profile"]["spent"] == "Покупка в маркете"


def test_levelling_up_gives_the_moment_once(client, admin, guest, clock):
    clock("09:30")
    feed(client, guest)
    top_up(client, guest, 60)
    assert feed(client, guest)["new_level"] == "Участник"
    assert feed(client, guest)["new_level"] is None
    assert RU["level"]["close"] == "Отлично"
