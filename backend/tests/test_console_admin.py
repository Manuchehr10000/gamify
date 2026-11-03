"""Piece 017 (console look: admin pages) changes only the look of /admin/live, /admin/tasks, /admin/tasks/qr and
/admin/guests, and adds the shared admin menu. These pin what those pages draw from the API, one test per «How to
check it» line that code can check, the language-file words the new look shows, and the stylesheet rules the phone,
print and keyboard lines rest on."""
import json
import re
from pathlib import Path

from tests.conftest import staff_headers
from tests.test_guest_list import LIST
from tests.test_rating import freeze, guests, score
from tests.test_tasks import admin, clock, guest, task, upload, xlsx  # noqa: F401 (fixtures)

ROOT = Path(__file__).parents[2]
FRONTEND = ROOT / "frontend" / "src"
RU = json.loads((FRONTEND / "locales" / "ru.json").read_text("utf-8"))
CSS = (FRONTEND / "components" / "console" / "console.css").read_text("utf-8")
ADMIN = (FRONTEND / "components" / "console" / "admin.tsx").read_text("utf-8")
PAGES = {name: (FRONTEND / "pages" / f"{name}.tsx").read_text("utf-8")
         for name in ("AdminLive", "AdminTasks", "AdminTasksQr", "AdminGuests")}


def media(query: str) -> str:
    """Everything inside the @media blocks with this query."""
    out = []
    for m in re.finditer(re.escape(f"@media {query}") + r" \{", CSS):
        depth, i = 1, m.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(CSS[i], 0)
            i += 1
        out.append(CSS[m.end():i - 1])
    return "\n".join(out)


def rule(css: str, selector: str) -> str:
    m = re.search(re.escape(selector) + r" \{([^}]*)\}", css)
    assert m, selector
    return m.group(1)


def preview_guests(client, h, text: str):
    files = {"file": ("guests.csv", text.encode(), "text/csv")}
    return client.post("/api/admin/guests/import/preview", files=files, headers=h)


def preview_tasks(client, h, data: bytes):
    files = {"file": ("tasks.xlsx", data, "application/octet-stream")}
    return client.post("/api/admin/tasks/import/preview", files=files, headers=h)


# Live page on a laptop: the side menu, seven readouts, three tables, no «Уникальных участников» for types and stages

def test_live_gives_the_seven_readouts_and_the_three_tables(client, admin):  # noqa: F811
    body = client.get("/api/admin/live", headers=admin).json()
    for key in ("logged_in", "active", "waiting", "oldest_seconds", "bought", "issued", "left"):
        assert key in body
    assert body["by_type"] == [] and body["by_stage"] == [] and body["partners"] == []
    assert [RU["live"][k] for k in ("loggedIn", "active", "waiting", "oldest", "bought", "issued", "left")] == [
        "Гостей вошло", "Активны за 15 минут", "Ждут проверки", "Самая старая ждёт",
        "Призов куплено", "Выдано на стендах", "Осталось"]
    page = PAGES["AdminLive"]
    assert page.count("<StatTile ") == 7
    assert page.count("<DataTable") == 4  # the three tables and the balance check's mismatches
    # Types and stages have Выполнений only; partners also Уникальных участников
    assert page.count("t('live.guests')") == 1
    assert (RU["live"]["byType"], RU["live"]["byStage"], RU["live"]["partners"]) == (
        "Выполнения по типам заданий", "Выполнения по этапам", "Партнёры")
    assert RU["live"]["report"] == "Скачать отчёт по партнёрам"


def test_the_oldest_wait_is_whole_minutes_with_no_warning_colour():
    assert RU["live"]["minutes"] == "{{count}} мин"
    assert "Math.floor(oldest / 60)" in PAGES["AdminLive"]
    assert "tone" not in re.search(r"<StatTile label=\{t\('live.oldest'\)\}[^\n]*", PAGES["AdminLive"]).group(0)


def test_from_768px_the_menu_is_a_side_menu_with_woodgrain_trim():
    wide = media("(min-width: 768px)")
    assert "flex: 0 0 240px" in rule(wide, ".gc-admin-shell__bar")
    assert "flex-direction: column" in rule(wide, ".gc-admin-shell__nav-list")
    assert 'className="gc-admin-shell__trim gc-wood"' in ADMIN


# The menu

def test_the_menu_lists_every_admin_page_and_names_itself_for_screen_readers():
    links = re.findall(r"\{ to: '([^']+)', label: '([^']+)'", ADMIN)
    assert links == [
        ("/admin/live", "live.title"), ("/admin/tasks", "tasksAdmin.title"), ("/admin/guests", "staff.adminTitle"),
        ("/admin/tasks/qr", "qrSheet.title")]
    labels = [RU[a][b] for _, key in links for a, b in [key.split(".")]]
    assert labels == ["Живые цифры", "Задания и этапы", "Список гостей", "QR-коды заданий"]
    assert RU["admin"]["nav"] == "Разделы"
    assert "aria-label={t('admin.nav')}" in ADMIN
    # The menu replaces the QR sheet's «Назад»; «QR-коды для печати» on /admin/tasks stays
    assert "common.back" not in PAGES["AdminTasksQr"]
    assert 'to="/admin/tasks/qr"' in PAGES["AdminTasks"] and RU["tasksAdmin"]["qrLink"] == "QR-коды для печати"
    for page in PAGES.values():
        assert "<AdminShell" in page


def test_tapping_list_of_guests_needs_no_second_login(client):
    # The menu is in-app links; every admin page reads the one admin token the first login stored
    h = staff_headers(client, "admin")
    assert client.get("/api/admin/live", headers=h).status_code == 200
    assert client.get("/api/admin/guests/export", headers=h).status_code == 200
    assert "<NavLink" in ADMIN
    for page in PAGES.values():
        assert "tokens.get('admin')" in page


# Phone

def test_on_a_phone_the_menu_is_a_top_bar_and_each_table_row_is_a_card():
    assert "overflow-x: auto" in rule(CSS, ".gc-admin-shell__nav-list")
    narrow = media("(max-width: 767.98px)")
    assert "display: block" in rule(narrow, ".gc-data-table__table, .gc-data-table__body, .gc-data-table__tr, .gc-data-table__td")
    card = rule(narrow, ".gc-data-table__tr")
    assert "border: var(--border-w) solid var(--border)" in card and "background: var(--surface-raised)" in card
    assert "content: attr(data-label)" in rule(narrow, ".gc-data-table__td::before")


def test_at_320px_only_the_menu_scrolls_sideways():
    main = rule(CSS, ".gc-admin-shell__main")
    assert "overflow-x: clip" in main and "min-width: 0" in main
    # Long words and numbers wrap in the cards rather than widening them
    assert "overflow-wrap: anywhere" in rule(CSS, ".gc-data-table__td")
    assert "white-space: normal" in rule(media("(max-width: 767.98px)"), ".gc-data-table__td.gc-num")
    assert "minmax(min(100%, 8rem), 1fr)" in rule(CSS, ".gc-admin-stats")


def test_the_phone_rules_hold_taps_of_48px_no_zoom_and_still_under_reduced_motion():
    assert "min-height: var(--target)" in rule(CSS, ".gc-admin-shell__nav-link")
    assert "min-height: var(--target)" in rule(CSS, ".gc-file-upload__btn")
    assert ".gc-root *, .gc-root *::before, .gc-root *::after, .gc-root { animation: none !important; transition: none !important;" in CSS
    # The only field is the file picker: no text typed, so nothing to zoom
    assert "<input" not in "".join(PAGES.values())


# Uploads

def test_a_tasks_file_with_two_bad_rows_names_both_rows(client, admin):  # noqa: F811
    rows = [task("A", 1, "Хорошее"), task("B", 7, "Нет такого этапа"), task("C", 1, "Без баллов", points=None)]
    body = preview_tasks(client, admin, xlsx(task_rows=rows)).json()
    assert body["failed"] == [
        {"sheet": "Задания", "row": 3, "reason": "unknown_stage"},
        {"sheet": "Задания", "row": 4, "reason": "no_points"},
    ]
    assert RU["tasksAdmin"]["row"] == "«{{sheet}}», строка {{row}}: {{reason}}"
    # One red strip naming every row; a good file gives the green strip with the counts
    assert '<Callout tone="danger">' in PAGES["AdminTasks"] and '<Callout tone="success">' in PAGES["AdminTasks"]
    good = upload(client, admin, xlsx(task_rows=[task("A", 1, "Хорошее"), task("B", 2, "Второе")])).json()
    assert (good["failed"], good["stages_added"], good["added"]) == ([], 4, 2)
    assert RU["tasksAdmin"]["added"] == "Добавлено заданий: {{count}}"


def test_a_guest_list_with_two_bad_rows_is_a_two_row_table(client):
    h = staff_headers(client, "admin")
    body = preview_guests(client, h, LIST + ";Сидоров;Пётр;;\nR-4;Кузнецов;;;\n").json()
    assert body["failed"] == [{"row": 4, "reason": "no_reg_id"}, {"row": 5, "reason": "no_first_name"}]
    assert (RU["admin"]["failedRows"], RU["admin"]["rowNumber"], RU["admin"]["reason"]) == (
        "Не загружены строки:", "Строка", "Причина")
    assert "caption={t('admin.failedRows')}" in PAGES["AdminGuests"]
    good = client.post("/api/admin/guests/import", files={"file": ("g.csv", LIST.encode(), "text/csv")}, headers=h).json()
    assert (good["failed"], good["added"]) == ([], 2)
    assert '<Callout tone="success">' in PAGES["AdminGuests"]
    assert RU["admin"]["added"] == "Добавлено гостей: {{count}}"


def test_a_file_with_missing_columns_or_sheets_says_so_as_today(client, admin):  # noqa: F811
    r = preview_guests(client, admin, "Фамилия;Телефон\nИванов;900\n")
    assert (r.status_code, r.json()["detail"]["code"]) == (400, "missing_columns")
    assert RU["admin"]["missingColumns"] == "В файле нет столбцов: {{columns}}"
    r = preview_tasks(client, admin, xlsx(task_head=["ID", "Этап", "Тип", "Текст"]))
    assert (r.status_code, r.json()["detail"]) == (400, {"code": "missing", "items": ["Задания: Баллы"]})
    assert RU["tasksAdmin"]["missing"] == "В файле нет: {{items}}"


# Next stage and the rating freeze ask in the card

def test_next_stage_asks_in_the_card_and_cancel_leaves_the_stage(client, admin, clock):  # noqa: F811
    upload(client, admin, xlsx())
    clock("11:00")
    assert client.get("/api/admin/stages", headers=admin).json()["current"] == 2
    # «Отмена» never reaches the server; the server itself still changes nothing unasked
    assert client.post("/api/admin/stages/advance", headers=admin).status_code == 409
    assert client.get("/api/admin/stages", headers=admin).json()["current"] == 2
    assert client.post("/api/admin/stages/advance?confirm=true", headers=admin).json()["current"] == 3
    assert RU["tasksAdmin"]["confirmNext"].startswith("Начать следующий этап прямо сейчас? ")
    assert (RU["market"]["cancel"], RU["market"]["yes"]) == ("Отмена", "Подтвердить")
    assert RU["tasksAdmin"]["now"] == "(сейчас идёт)"
    # The question names the stage that ends and the one that starts, as the server's unconfirmed answer says
    assert "setAsking([t('tasksAdmin.confirmNext'), ...lines]" in PAGES["AdminTasks"]
    assert "t('settingsAdmin.impact.stage_change'" in PAGES["AdminTasks"]
    assert "'/api/admin/stages/advance', { token, method: 'POST' }" in PAGES["AdminTasks"]
    assert "<InlineConfirm question={asking}" in ADMIN
    assert "window.confirm" not in PAGES["AdminTasks"] + ADMIN


def test_freezing_and_unfreezing_ask_in_the_card(client, admin):  # noqa: F811
    g = guests("ID;Имя\nR-1;Анна\n")
    score(g["Анна"], 10, 1)
    assert freeze(client, admin).json()["frozen"] is True
    assert freeze(client, admin, frozen=False).json()["frozen"] is False
    page = PAGES["AdminTasks"]
    assert "<InlineConfirm" in page and "'ratingAdmin.confirmUnfreeze' : 'ratingAdmin.confirmFreeze'" in page


# Print

def test_printing_shows_no_switches_no_menu_no_ground_and_one_card_per_cut_out():
    printed = media("print")
    assert ".gc-admin-shell__bar, .gc-admin-shell__head, .gc-button, .gc-no-print { display: none !important; }" in printed
    assert "background: none" in rule(printed, "html[data-theme], html[data-theme] body, .gc-ribs")
    qr = rule(printed, ".gc-qr-card")
    assert "break-inside: avoid" in qr and "box-shadow: none" in qr
    # The QR sheet: only the cards; its hint is not printed
    assert 'gc-no-print">{t(\'qrSheet.hint\'' in PAGES["AdminTasksQr"]
    assert '<div className="gc-no-print"><Callout tone="danger">' in PAGES["AdminTasksQr"]
    assert '<div className="gc-no-print"><Loading />' in PAGES["AdminTasksQr"]


def test_printing_the_top_10_leaves_out_the_rest_of_the_tasks_page(client, admin):  # noqa: F811
    g = guests("ID;Имя;Компания\nR-1;Анна;TAG\n")
    score(g["Анна"], 10, 1)
    top = freeze(client, admin).json()["top"]
    assert [(r["place"], r["first_name"], r["company"], r["points"]) for r in top] == [(1, "Анна", "TAG", 10)]
    page = PAGES["AdminTasks"]
    assert page.count('className="gc-admin-shell__body gc-no-print"') == 2
    # The print switch is a console Button, which printing hides
    assert '<Button variant="outline" icon="printer"' in page.split("function RatingFreeze")[1]
    assert RU["ratingAdmin"]["listTitle"] == "Топ-10 для ведущего"


# Keyboard and the light browser bar

def test_every_control_shows_a_thick_focus_ring():
    assert ".gc-root :focus-visible { outline: 3px solid var(--focus); outline-offset: 2px; }" in CSS
    # The file picker's ring is drawn on its visible key
    assert "outline: 3px solid var(--focus)" in rule(CSS, ".gc-file-upload__input:focus-visible + .gc-file-upload__btn")


def test_the_browser_bar_is_light():
    assert '<ConsoleTheme theme="label" />' in ADMIN
    assert "color-scheme: light" in rule(CSS, 'html[data-theme="label"],\nhtml[data-theme="label"] body')


# lucide-react is gone

def test_no_screen_uses_lucide_react_and_it_left_the_packages():
    sources = "".join(p.read_text("utf-8") for p in FRONTEND.rglob("*.ts*"))
    assert "from 'lucide-react'" not in sources
    assert "lucide-react" not in (ROOT / "frontend" / "package.json").read_text("utf-8")
    assert "lucide-react" not in json.loads((ROOT / "ship.json").read_text("utf-8"))["stack"]["node"]
