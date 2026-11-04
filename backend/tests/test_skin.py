import json
import re
from pathlib import Path

from tests.conftest import staff_headers
from tests.test_admin_settings import log
from tests.test_tasks import admin  # noqa: F401 (fixture)


def skin_setting(client, h) -> dict:
    return next(s for s in client.get("/api/admin/settings", headers=h).json() if s["key"] == "skin")


def put_skin(client, h, value, version, confirm=False):
    path = "/api/admin/settings/skin" + ("?confirm=true" if confirm else "")
    return client.put(path, json={"value": value, "version": version}, headers=h)


def test_the_four_skins_show_with_console_chosen(client, admin):
    s = skin_setting(client, admin)
    assert (s["text"], s["choices"], s["effect"]) == ("console", ["console", "steampunk", "space", "ornament"], "now")
    # Phones, the hall and the staff login pages read it with no login
    assert client.get("/api/version").json()["skin"] == "console"


def test_saving_a_skin_asks_first_and_cancelling_changes_nothing(client, admin):
    s = skin_setting(client, admin)
    before = client.get("/api/version").json()
    r = put_skin(client, admin, "steampunk", s["version"])
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "confirm"
    assert r.json()["detail"]["impact"] == [{"code": "skin"}]
    # Nothing kept: the skin, the version phones poll and the log are as before
    assert client.get("/api/version").json() == before
    assert skin_setting(client, admin)["text"] == "console"
    assert log(client, admin, kind="settings") == []


def test_a_confirmed_skin_reaches_every_page_and_the_log(client, admin):
    s = skin_setting(client, admin)
    before = client.get("/api/version").json()["version"]
    r = put_skin(client, admin, "steampunk", s["version"], confirm=True)
    assert r.status_code == 200, r.text
    assert r.json()["text"] == "steampunk"
    # Every page polls this every 10 seconds: the version moves and names the new skin
    now = client.get("/api/version").json()
    assert now["skin"] == "steampunk" and now["version"] > before
    (event,) = log(client, admin, kind="settings")
    assert (event["item"], event["old_value"], event["new_value"]) == ("skin", "console", "steampunk")
    assert event["staff_name"]


def test_an_unknown_skin_is_refused(client, admin):
    s = skin_setting(client, admin)
    r = put_skin(client, admin, "neon", s["version"], confirm=True)
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["code"] == "bad_value"
    assert client.get("/api/version").json()["skin"] == "console"


def test_only_an_admin_changes_the_skin(client, admin):
    s = skin_setting(client, admin)
    desk = staff_headers(client, "desk")
    assert put_skin(client, desk, "space", s["version"], confirm=True).status_code in (401, 403)
    assert client.get("/api/version").json()["skin"] == "console"


# The pages: the theme each skin puts on guest and staff screens, its fonts and its words

FRONTEND = Path(__file__).parents[2] / "frontend" / "src"
CONSOLE = FRONTEND / "components" / "console"
RU = json.loads((FRONTEND / "locales" / "ru.json").read_text("utf-8"))
CSS = (CONSOLE / "console.css").read_text("utf-8")
SKIN_TS = (CONSOLE / "skin.ts").read_text("utf-8")
# Skin: (dark theme for guests and the hall, light theme for staff and admins)
THEMES = {"console": ("console", "label"), "steampunk": ("brass", "parchment"), "space": ("orbit", "station"),
          "ornament": ("lapis", "suzani")}


def families(css: str) -> set[str]:
    return set(re.findall(r"font-family: '([^']+)'", css))


def stack(skin: str) -> set[str]:
    """The faces a skin's theme names in its --font-* stacks."""
    dark = THEMES[skin][0]
    block = next(b for sel, b in re.findall(r"([^{}]+)\{([^}]*)\}", CSS)
                 if f'[data-theme="{dark}"]' in sel and "--font-sans" in b)
    return set(re.findall(r'"([^"]+)"', " ".join(re.findall(r"--font-\w+: ([^;]+);", block)))) - {"Segoe UI", "Times New Roman"}


def test_the_skin_names_and_the_confirmation_are_in_russian():
    assert RU["settingsAdmin"]["choices"]["skin"] == {
        "console": "Консоль", "steampunk": "Стимпанк", "space": "Космос", "ornament": "Таджикский орнамент"}
    assert RU["settingsAdmin"]["impact"]["skin"] == "Оформление сменится на всех экранах: у гостей, на стойках и в зале"
    assert RU["settingsAdmin"]["fields"]["settings"]["skin"]


def test_guest_pages_and_the_hall_are_dark_staff_and_admin_pages_light_in_every_skin():
    for skin, (dark, light) in THEMES.items():
        assert f"{skin}: {{ dark: '{dark}', light: '{light}' }}" in SKIN_TS
        for theme in (dark, light):
            assert re.search(rf'\[data-theme="{theme}"\] \{{[^}}]*--ground: #', CSS), theme
    pages = {p.stem: p.read_text("utf-8") for p in (FRONTEND / "pages").glob("*.tsx")}
    for page in ("Desk", "Stand", "Moderate"):
        assert '<Screen theme="light"' in pages[page] and 'theme="dark"' not in pages[page]
    assert '<Shell theme="dark"' in pages["Hall"]
    assert '<Screen theme="light"' in (FRONTEND / "components" / "StaffLogin.tsx").read_text("utf-8")


def test_every_console_screen_follows_the_polled_skin_and_remembers_it():
    ui = (CONSOLE / "ui.tsx").read_text("utf-8")
    shell = ui[ui.index("function useConsoleShell"):ui.index("useLayoutEffect(() => {")]
    assert "useSkin()" in shell and "useConfigVersion()" in shell and "useSkinFonts(skin)" in shell
    version = (FRONTEND / "version.ts").read_text("utf-8")
    assert "VERSION_POLL_MS = 10_000" in version and "setSkin(skin)" in version
    # The last skin seen opens the next page straight away, also offline; the first paint waits for it
    assert "localStorage.getItem(KEY)" in SKIN_TS and "localStorage.setItem(KEY, skin)" in SKIN_TS
    assert "skinReady().then(" in (FRONTEND / "main.tsx").read_text("utf-8")


def test_a_page_loads_only_its_skins_fonts_shipped_with_the_app():
    assert "@font-face" not in CSS
    for skin in THEMES:
        css = (CONSOLE / "fonts" / f"{skin}.css").read_text("utf-8")
        assert f"{skin}: () => import('./fonts/{skin}.css')" in SKIN_TS
        # The file holds exactly the faces the skin's theme names, from the app's own packages
        assert families(css) == stack(skin), skin
        assert all(u.startswith("@fontsource/") for u in re.findall(r"url\('([^']+)'\)", css))
    for f in [*FRONTEND.rglob("*.css"), *FRONTEND.rglob("*.ts*"), FRONTEND.parent / "index.html"]:
        assert "fonts.googleapis" not in f.read_text("utf-8"), f


def test_every_skins_text_faces_carry_tajik_letters():
    for skin in THEMES:
        css = (CONSOLE / "fonts" / f"{skin}.css").read_text("utf-8")
        tajik = {fam for fam, sub in re.findall(r"font-family: '([^']+)'.*?-(cyrillic-ext)-\d+-normal", css)}
        # JetBrains Mono sets IDs and counts, Pixelify Sans numbers only (Exo 2 follows it for any letter)
        assert families(css) - {"JetBrains Mono", "Pixelify Sans"} <= tajik, skin
    # A display face with no ҳ is followed by the same skin's face that has it
    for face, then in (("Press Start 2P", "Exo 2"), ("Old Standard TT", "PT Serif"), ("Philosopher", "Noto Sans")):
        assert re.search(rf'"{face}", "{then}"', CSS), face


def test_the_qr_quiet_zone_is_light_in_every_light_theme():
    # Staff QR cards (/desk, the /admin/tasks/qr sheet) sit on the light theme's raised surface, never on dark ink
    rule = re.search(r'([^{}]+)\{ background: var\(--surface-raised\); \}', CSS[CSS.index(".gc-qr-card__quiet {"):])
    assert rule and ".gc-qr-card__quiet" in rule.group(1)
    for _, light in THEMES.values():
        assert f'[data-theme="{light}"]' in rule.group(1), light


def test_only_the_settings_previews_load_the_other_skins_fonts():
    admin_page = (FRONTEND / "pages" / "AdminSettings.tsx").read_text("utf-8")
    assert "usePreviewFonts(skin)" in admin_page and "useSkinFonts" not in admin_page
    # The first paint waits for the skin's faces' stylesheet, so a reload shows no fallback faces first
    ready = SKIN_TS[SKIN_TS.index("export async function skinReady"):SKIN_TS.index("function subscribe")]
    assert "await loadFonts(current)" in ready
