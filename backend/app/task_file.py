"""The admin's Excel file: sheet «Этапы» (the day's schedule), sheet «Задания» (the task catalog),
sheet «Вопросы» (the quizzes' questions), sheet «Призы» (the market's prizes) and sheet «Уровни» (the levels by points).

Upload reads the sheets; download writes them back the same way, so the file can be edited and uploaded again.
An upload applies whole or not at all, after a preview of what it adds, changes and hides.
"""
import io
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from decimal import Decimal

from openpyxl import Workbook, load_workbook
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as DbSession

from app import changes, settings
from app.guests import random_code
from app.models import Level, Partner, Prize, Question, Redemption, Stage, Task
from app.stages import EVENT_TZ

STAGES_SHEET = "Этапы"
TASKS_SHEET = "Задания"
PRIZES_SHEET = "Призы"
QUESTIONS_SHEET = "Вопросы"
LEVELS_SHEET = "Уровни"

STAGE_COLUMNS = {
    "number": "Номер",
    "name": "Название",
    "starts_at": "Начало",
    "ends_at": "Конец",
    "message": "Сообщение при смене этапа",
    "market": "Маркет",
    "batch_size": "Карточек в ленте",
    "multiplier": "Множитель",
}
TASK_COLUMNS = {
    "code": "ID",
    "stage": "Этап",
    "type": "Тип",
    "text": "Текст",
    "points": "Баллы",
    "coins": "Монеты",
    "partner_name": "Партнёр",
    "partner_package": "Пакет партнёра",
    "window_start": "Доступно с",
    "window_end": "Доступно до",
    "method": "Выполнение",
    "link": "Ссылка",
    "timer": "Таймер, сек",
    "requires": "Требует",
    "limit": "Лимит",
    "blitz": "Блиц",
    "speed_bonus": "Бонус за скорость",
    "grace_seconds": "Без потерь, сек",
    "bonus_seconds": "Время бонуса, сек",
}
QUESTION_COLUMNS = {
    "task": "ID задания",
    "number": "№ вопроса",
    "text": "Вопрос",
    "option1": "Вариант 1",
    "option2": "Вариант 2",
    "option3": "Вариант 3",
    "option4": "Вариант 4",
    "correct": "Правильный (1–4)",
}
PRIZE_COLUMNS = {
    "code": "ID",
    "name": "Название",
    "partner": "Партнёр",
    "price": "Цена в монетах",
    "quantity": "Количество",
}
LEVEL_COLUMNS = {
    "name": "Название",
    "min_points": "Баллов от",
}
REQUIRED_STAGE = ("number", "name", "starts_at", "ends_at")
REQUIRED_TASK = ("code", "stage", "type", "text", "points")
# A stage's «Карточек в ленте» when the cell is blank
BATCH_SIZE = 15
# A quiz's blitz numbers when the cells are blank: «Бонус за скорость», «Без потерь, сек», «Время бонуса, сек»
SPEED_DEFAULTS = {"speed_bonus": 20, "grace_seconds": 3, "bonus_seconds": 12}
# Locked while the blitz is running
BLITZ_FIELDS = ("blitz", *SPEED_DEFAULTS)
REQUIRED_PRIZE = tuple(PRIZE_COLUMNS)
REQUIRED_QUESTION = ("task", "number", "text", "option1", "option2", "correct")
OPTIONS = ("option1", "option2", "option3", "option4")

# The 10 task types of TAG's rules (section 5). The file names them in Russian; the first name is what export writes.
TYPES = {
    "quiz": ["Квиз"],
    "selfie": ["Селфи"],
    "action": ["Действие"],
    "purchase": ["Покупка"],
    "registration": ["Регистрация"],
    "networking": ["Нетворкинг"],
    "crazy": ["Крейзи", "Крейзи-действие"],
    "attention": ["На внимательность"],
    "territory": ["Территориальное"],
    "pre": ["Предзадание"],
}
# How a task is done; blank = not doable yet (later pieces)
METHODS = {
    "qr": ["QR", "QR-код"],
    "link": ["Ссылка", "Link"],
    "market": ["Маркет", "Market"],
    "photo": ["Фото", "Photo"],
    "text": ["Текст", "Text"],
    "photo_text": ["Фото+текст", "Фото + текст", "Photo+text"],
    "quiz": ["Квиз", "Quiz"],
}
# The «Маркет» cell on a stage: «да» marks where the market opens; export writes the first word
YES = ("да", "yes", "1", "+", "x", "true")
NO = ("", "нет", "no", "0", "-", "false")
# Partner packages in feed order (TAG's rules, section 6)
PACKAGES = {
    "general": ["Генеральный партнёр", "General"],
    "headliner": ["Хедлайнер", "Хедлайнер форума", "Headliner"],
    "mf_partner": ["MF Партнёр", "MF Partner"],
    "supporters": ["Нас поддерживают", "Supporters"],
}
# The limits the form and the file share, so a value one accepts the other accepts too: (kind, field) → a number's
# range, or a text's length from 1
LIMITS = {
    ("stages", "number"): (1, 50), ("stages", "name"): (1, 100), ("stages", "message"): (0, 500),
    ("stages", "batch_size"): (5, 50), ("stages", "multiplier"): (1, 5),
    ("tasks", "code"): (1, 32), ("tasks", "text"): (1, 1000), ("tasks", "points"): (0, 10000),
    ("tasks", "coins"): (0, 10000), ("tasks", "link"): (0, 500), ("tasks", "timer_seconds"): (5, 3600),
    ("tasks", "limit"): (1, 100000), ("tasks", "speed_bonus"): (0, 10000), ("tasks", "grace_seconds"): (0, 3600),
    ("tasks", "bonus_seconds"): (0, 3600),
    ("prizes", "code"): (1, 32), ("prizes", "name"): (1, 200), ("prizes", "price"): (1, 100000),
    ("prizes", "quantity"): (0, 100000),
    ("questions", "number"): (1, 100), ("questions", "text"): (1, 1000), ("questions", "option"): (1, 300),
    ("levels", "name"): (1, 100), ("levels", "min_points"): (0, 100000),
    ("partners", "name"): (1, 100),
}
# A stage's «Множитель» moves in halves: 1, 1.5, 2 … 5
MULTIPLIER_STEP = Decimal("0.5")
DATE_FORMATS = ("%d.%m.%Y %H:%M", "%d.%m.%Y %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S")
EXCEL_DATE = "DD.MM.YYYY HH:MM"


def rule_coins(points: int, partner: bool, multiplier: Decimal) -> int:
    """Coins when the cell is blank: 1:1 with points; for partner tasks × the admin's multiplier (×1.5 in TAG's
    rules, 3.1–3.2), rounded up."""
    return math.ceil(points * multiplier) if partner else points


@dataclass
class ImportResult:
    stages_added: int = 0
    stages_changed: int = 0
    added: int = 0
    changed: int = 0
    hidden: int = 0
    prizes_added: int = 0
    prizes_changed: int = 0
    prizes_hidden: int = 0
    # The «Уровни» sheet replaced the levels (it matched what was loaded, otherwise)
    levels_changed: bool = False
    # Any bad row refuses the whole file: nothing applies, and every bad row is named
    failed: list[dict] = field(default_factory=list)
    # The preview's rows: {sheet, code, name, change: added · changed · hidden}
    items: list[dict] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


class RowError(Exception):
    """A bad row's reason, with the range or length it broke (min, max, column) for the message."""

    def __init__(self, reason: str, **detail):
        super().__init__(reason)
        self.detail = detail


def _lookup(names: dict[str, list[str]], raw: str) -> str | None:
    """«Действие ★», «Квиз (скрытый экспертный)», «Крейзи / на внимательность» → the first type named."""
    first = re.sub(r"\(.*?\)|★", "", raw).split("/")[0].strip().lower()
    for key, aliases in names.items():
        if first in (a.lower() for a in aliases):
            return key
    return None


def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _int(v, reason: str, limit: tuple[str, str]) -> int:
    """A whole number within the form's range for (kind, field); the reason names the range."""
    lo, hi = LIMITS[limit]
    s = _text(v).replace(",", ".")
    try:
        n = float(s)
    except ValueError:
        raise RowError(reason, min=lo, max=hi) from None
    if not n.is_integer() or not lo <= n <= hi:
        raise RowError(reason, min=lo, max=hi)
    return int(n)


def stage_multiplier(v) -> Decimal | None:
    """A stage's «Множитель» from the file or the form: 1 to 5 in steps of 0.5, 1,5 and 1.5 both read; blank = 1.
    None when it isn't one."""
    s = _text(v).replace(",", ".")
    if not s:
        return Decimal(1)
    try:
        m = Decimal(s)
    except ArithmeticError:
        return None
    lo, hi = LIMITS["stages", "multiplier"]
    if not m.is_finite() or not lo <= m <= hi or m % MULTIPLIER_STEP:
        return None
    return m


def _long(text: str, limit: tuple[str, str], column: str) -> str:
    """A text no longer than the form allows for (kind, field)."""
    hi = LIMITS[limit][1]
    if len(text) > hi:
        raise RowError("too_long", column=column, max=hi)
    return text


def _time(v, reason: str) -> datetime:
    """A date-time cell, or text like 13.12.2026 09:00, in Dushanbe time."""
    if isinstance(v, datetime):
        dt = v
    else:
        s = _text(v)
        for fmt in DATE_FORMATS:
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
        else:
            raise RowError(reason)
    return dt.replace(tzinfo=EVENT_TZ) if dt.tzinfo is None else dt


def _sheet_rows(ws, columns: dict[str, str]) -> tuple[dict[str, int], list[tuple[int, list]]]:
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return {}, []
    header = [_text(h).lower() for h in rows[0]]
    cols = {key: header.index(name.lower()) for key, name in columns.items() if name.lower() in header}
    body = [(n, list(r)) for n, r in enumerate(rows[1:], start=2) if any(_text(c) for c in r)]
    return cols, body


def _cell(row: list, cols: dict[str, int], key: str):
    i = cols.get(key)
    return row[i] if i is not None and i < len(row) else None


@dataclass
class QuestionRow:
    row: int
    number: int
    text: str
    options: list[str]
    correct: int


def _questions(cols: dict[str, int], rows: list[tuple[int, list]],
               fail: Callable[[str, int, "str | RowError"], None]) -> dict[str, list[QuestionRow]]:
    """The «Вопросы» sheet grouped by task ID; a bad row fails on its own and the others load."""
    by_task: dict[str, list[QuestionRow]] = {}
    for n, row in rows:
        try:
            code = _text(_cell(row, cols, "task"))
            if not code:
                raise RowError("no_task_id")
            number = _int(_cell(row, cols, "number"), "bad_question_number", ("questions", "number"))
            if any(q.number == number for q in by_task.get(code, [])):
                raise RowError("duplicate_question")
            text = _long(_text(_cell(row, cols, "text")), ("questions", "text"), QUESTION_COLUMNS["text"])
            if not text:
                raise RowError("no_question")
            cells = [_long(_text(_cell(row, cols, k)), ("questions", "option"), QUESTION_COLUMNS[k]) for k in OPTIONS]
            options = [c for c in cells if c]
            # 2–4 options, filled from «Вариант 1» on, so «Правильный» points at the column the admin sees
            if len(options) < 2 or cells[:len(options)] != options:
                raise RowError("bad_options")
            correct = _int(_cell(row, cols, "correct"), "bad_correct", ("questions", "number"))
            if not 1 <= correct <= len(options):
                raise RowError("bad_correct")
        except RowError as e:
            fail(QUESTIONS_SHEET, n, e)
            continue
        by_task.setdefault(code, []).append(QuestionRow(n, number, text, options, correct))
    return by_task


def _loaded(db: DbSession, task: Task) -> list[Question]:
    # Locked, as the upload may replace them: a form save of one at the same moment waits, then is refused as stale
    return list(db.scalars(select(Question).where(Question.task_id == task.id).order_by(Question.number)
                           .with_for_update().execution_options(populate_existing=True)))


def _questions_differ(old: list[Question], rows: list[QuestionRow]) -> bool:
    as_rows = [(q.number, q.text, [o for o in (q.option1, q.option2, q.option3, q.option4) if o], q.correct)
               for q in old]
    return as_rows != [(q.number, q.text, q.options, q.correct) for q in sorted(rows, key=lambda q: q.number)]


def _save_questions(db: DbSession, task: Task, old: list[Question], rows: list[QuestionRow]) -> None:
    """Replace a quiz's questions with the file's."""
    for q in old:
        db.delete(q)
    db.flush()
    for q in sorted(rows, key=lambda q: q.number):
        opts = q.options + [None] * (4 - len(q.options))
        db.add(Question(task_id=task.id, number=q.number, text=q.text, option1=opts[0], option2=opts[1],
                        option3=opts[2], option4=opts[3], correct=q.correct))


# (kind, item, field, old, new) for the change log, or None while previewing
Recorder = Callable[[str, int | None, str, str, object, object], None]


class _Notes:
    """What an upload changes, row by row: the preview's list, and the log rows written once it applies."""

    def __init__(self, result: ImportResult):
        self.result = result
        self.log: list[tuple[str, object, str, object, object]] = []

    def item(self, sheet: str, code: str, name: str, change: str) -> None:
        self.result.items.append({"sheet": sheet, "code": code, "name": name, "change": change})

    def added(self, kind: str, row: object, values: dict) -> None:
        """A new row, and its values, so the log holds what was added."""
        self.log.append((kind, row, changes.CREATED, None, None))
        for k, v in values.items():
            if k not in ("position", "coins_from_rule") and v is not None and v != "":
                self.log.append((kind, row, k, None, v))

    def set(self, kind: str, row: object, values: dict, skip: tuple[str, ...] = ("position",)) -> bool:
        """Put the values on the row; True when one that counts changed (moving a row doesn't count)."""
        changed = False
        for k, v in values.items():
            old = getattr(row, k)
            if old != v and k not in skip:
                self.log.append((kind, row, k, old, v))
                changed = True
            setattr(row, k, v)
        return changed

    def write(self, db: DbSession, record: Recorder) -> None:
        db.flush()
        for kind, row, name, old, new in self.log:
            record(kind, row.id if hasattr(row, "id") else None, changes.label(db, row) if hasattr(row, "id")
                   else str(row), name, changes.shown(db, name, old), changes.shown(db, name, new))


def _partner(db: DbSession, partners: dict[str, Partner], name: str, notes: _Notes) -> Partner:
    """The partner with this name; a new name adds one (with no package until «Задания» gives it)."""
    partner = partners.get(name)
    if partner is None:
        partner = Partner(name=name)
        db.add(partner)
        db.flush()
        partners[name] = partner
        notes.added("partners", partner, {"name": name})
    return partner


def _locked(model: type):
    """The rows an upload may change, locked: a form save of one at the same moment waits, then is refused as stale."""
    return select(model).order_by(model.id).with_for_update().execution_options(populate_existing=True)


def import_xlsx(db: DbSession, raw: bytes, apply: bool = True, record: Recorder | None = None) -> ImportResult:
    """Read the file and diff it with what is loaded. It applies whole or not at all: any bad row refuses the file,
    naming each bad row, and nothing changes. With apply=False (the preview) nothing changes either way."""
    result = ImportResult()
    try:
        wb = load_workbook(io.BytesIO(raw), data_only=True, read_only=True)
    except Exception:
        result.missing = [STAGES_SHEET, TASKS_SHEET]
        return result
    sheets = {name.strip().lower(): name for name in wb.sheetnames}
    result.missing = [s for s in (STAGES_SHEET, TASKS_SHEET) if s.lower() not in sheets]
    if result.missing:
        return result
    stage_cols, stage_rows = _sheet_rows(wb[sheets[STAGES_SHEET.lower()]], STAGE_COLUMNS)
    task_cols, task_rows = _sheet_rows(wb[sheets[TASKS_SHEET.lower()]], TASK_COLUMNS)
    # A file without «Призы» leaves the prizes as they are, so an older file can't empty the market
    prize_sheet = sheets.get(PRIZES_SHEET.lower())
    prize_cols, prize_rows = _sheet_rows(wb[prize_sheet], PRIZE_COLUMNS) if prize_sheet else ({}, [])
    # Without «Вопросы» a quiz task has no questions, so it fails with the reason
    question_sheet = sheets.get(QUESTIONS_SHEET.lower())
    question_cols, question_rows = (_sheet_rows(wb[question_sheet], QUESTION_COLUMNS) if question_sheet
                                    else ({}, []))
    # A file without «Уровни» leaves the levels as they are
    level_sheet = sheets.get(LEVELS_SHEET.lower())
    level_cols, level_rows = _sheet_rows(wb[level_sheet], LEVEL_COLUMNS) if level_sheet else ({}, [])
    result.missing = [f"{STAGES_SHEET}: {STAGE_COLUMNS[c]}" for c in REQUIRED_STAGE if c not in stage_cols] + [
        f"{TASKS_SHEET}: {TASK_COLUMNS[c]}" for c in REQUIRED_TASK if c not in task_cols] + [
        f"{PRIZES_SHEET}: {PRIZE_COLUMNS[c]}" for c in REQUIRED_PRIZE if prize_sheet and c not in prize_cols] + [
        f"{QUESTIONS_SHEET}: {QUESTION_COLUMNS[c]}" for c in REQUIRED_QUESTION
        if question_sheet and c not in question_cols] + [
        f"{LEVELS_SHEET}: {LEVEL_COLUMNS[c]}" for c in LEVEL_COLUMNS if level_sheet and c not in level_cols]
    if result.missing:
        return result

    def fail(sheet: str, row: int, reason: str | RowError) -> None:
        detail = reason.detail if isinstance(reason, RowError) else {}
        result.failed.append({"sheet": sheet, "row": row, "reason": str(reason), **detail})

    notes = _Notes(result)
    multiplier = settings.get(db, "partner_coin_multiplier")
    # Switched-off stages too: a row for one switches it back on, as a hidden task's row brings the task back
    stages = {s.number: s for s in db.scalars(_locked(Stage))}
    seen_stages: set[int] = set()
    for n, row in stage_rows:
        try:
            number = _int(_cell(row, stage_cols, "number"), "bad_stage_number", ("stages", "number"))
            if number in seen_stages:
                raise RowError("duplicate_stage")
            name = _long(_text(_cell(row, stage_cols, "name")), ("stages", "name"), STAGE_COLUMNS["name"])
            if not name:
                raise RowError("no_name")
            message = _long(_text(_cell(row, stage_cols, "message")), ("stages", "message"), STAGE_COLUMNS["message"])
            starts = _time(_cell(row, stage_cols, "starts_at"), "bad_start")
            ends = _time(_cell(row, stage_cols, "ends_at"), "bad_end")
            if ends <= starts:
                raise RowError("end_before_start")
            market_cell = _text(_cell(row, stage_cols, "market")).lower()
            if market_cell not in YES + NO:
                raise RowError("bad_market")
            batch_cell = _cell(row, stage_cols, "batch_size")
            batch_size = (_int(batch_cell, "bad_batch_size", ("stages", "batch_size")) if _text(batch_cell)
                          else BATCH_SIZE)
            points_multiplier = stage_multiplier(_cell(row, stage_cols, "multiplier"))
            if points_multiplier is None:
                raise RowError("bad_multiplier")
        except RowError as e:
            fail(STAGES_SHEET, n, e)
            continue
        seen_stages.add(number)
        values = {"name": name, "starts_at": starts, "ends_at": ends,
                  "message": message, "market": market_cell in YES, "active": True}
        # A file without the column (an older one) leaves the number as it is
        if "batch_size" in stage_cols:
            values["batch_size"] = batch_size
        if "multiplier" in stage_cols:
            values["multiplier"] = points_multiplier
        stage = stages.get(number)
        if stage is None:
            stage = Stage(number=number, **values)
            db.add(stage)
            stages[number] = stage
            result.stages_added += 1
            notes.added("stages", stage, {"number": number, **values})
            notes.item(STAGES_SHEET, str(number), name, "added")
        elif notes.set("stages", stage, values):
            result.stages_changed += 1
            notes.item(STAGES_SHEET, str(number), name, "changed")
    db.flush()

    questions = _questions(question_cols, question_rows, fail)
    tasks = {t.code: t for t in db.scalars(_locked(Task))}
    seen: set[str] = set()
    methods = {_text(_cell(r, task_cols, "code")): _lookup(METHODS, _text(_cell(r, task_cols, "method")))
               for _, r in task_rows}
    # Rows that passed their own checks; «Требует» is checked once all rows are read, since its QR row may sit lower
    parsed: list[tuple[int, str, dict, str, str]] = []
    # Each partner's package as the first row naming it gives it; a row giving another one fails
    packages: dict[str, str] = {}
    ids: set[str] = set()
    # Quiz rows loaded in this upload: their «Требует», whether they already count as added or changed, and the row
    quizzes: dict[str, tuple[str, bool, int]] = {}
    for position, (n, row) in enumerate(task_rows):
        try:
            code = _long(_text(_cell(row, task_cols, "code")), ("tasks", "code"), TASK_COLUMNS["code"])
            if not code:
                raise RowError("no_id")
            if code in ids:
                raise RowError("duplicate_id")
            stage_cell = _text(_cell(row, task_cols, "stage"))
            stage = stages.get(int(stage_cell)) if stage_cell.isdigit() else None
            if stage is None:
                raise RowError("unknown_stage")
            type_ = _lookup(TYPES, _text(_cell(row, task_cols, "type")))
            if type_ is None:
                raise RowError("unknown_type")
            text = _long(_text(_cell(row, task_cols, "text")), ("tasks", "text"), TASK_COLUMNS["text"])
            if not text:
                raise RowError("no_text")
            if not _text(_cell(row, task_cols, "points")):
                raise RowError("no_points")
            points = _int(_cell(row, task_cols, "points"), "bad_points", ("tasks", "points"))
            partner_name = _long(_text(_cell(row, task_cols, "partner_name")), ("partners", "name"),
                                 TASK_COLUMNS["partner_name"])
            package_cell = _text(_cell(row, task_cols, "partner_package"))
            package = _lookup(PACKAGES, package_cell) if package_cell else ""
            if package is None:
                raise RowError("unknown_package")
            if package and not partner_name:
                raise RowError("no_partner_name")
            coins_cell = _cell(row, task_cols, "coins")
            from_rule = not _text(coins_cell)
            coins = (rule_coins(points, bool(partner_name), multiplier) if from_rule
                     else _int(coins_cell, "bad_coins", ("tasks", "coins")))
            w_start = _cell(row, task_cols, "window_start")
            w_end = _cell(row, task_cols, "window_end")
            window_start = _time(w_start, "bad_window") if _text(w_start) else None
            window_end = _time(w_end, "bad_window") if _text(w_end) else None
            if window_start and window_end and window_end <= window_start:
                raise RowError("bad_window")
            method_cell = _text(_cell(row, task_cols, "method"))
            method = _lookup(METHODS, method_cell) if method_cell else ""
            if method is None:
                raise RowError("unknown_method")
            link = (_long(_text(_cell(row, task_cols, "link")), ("tasks", "link"), TASK_COLUMNS["link"])
                    if method == "link" else "")
            if method == "link" and not link:
                raise RowError("no_link")
            if link and not re.match(r"https?://\S+$", link):
                raise RowError("bad_link")
            timer_cell = _cell(row, task_cols, "timer") if method == "quiz" else None
            timer = _int(timer_cell, "bad_timer", ("tasks", "timer_seconds")) if _text(timer_cell) else None
            requires = _text(_cell(row, task_cols, "requires")) if method == "quiz" else ""
            blitz_cell = _text(_cell(row, task_cols, "blitz")).lower()
            if blitz_cell not in YES + NO:
                raise RowError("bad_blitz")
            if blitz_cell in YES and method != "quiz":
                raise RowError("blitz_quiz_only")
            # The blitz numbers, read on a quiz only (as its timer); a file without a column leaves that one as it is
            speed: dict = {"blitz": blitz_cell in YES} if "blitz" in task_cols or method != "quiz" else {}
            if method == "quiz":
                for key, default in SPEED_DEFAULTS.items():
                    cell = _cell(row, task_cols, key)
                    if key in task_cols:
                        speed[key] = _int(cell, f"bad_{key}", ("tasks", key)) if _text(cell) else default
                old = tasks.get(code)
                kept = {k: getattr(old, k) if old else d for k, d in SPEED_DEFAULTS.items()}
                # Grace below bonus time, so the bonus falls to 0 and never divides by zero
                if speed.get("grace_seconds", kept["grace_seconds"]) >= speed.get("bonus_seconds",
                                                                                  kept["bonus_seconds"]):
                    raise RowError("bad_speed_window")
            limit_cell = _cell(row, task_cols, "limit")
            limit = _int(limit_cell, "bad_limit", ("tasks", "limit")) if _text(limit_cell) else None
            # A quiz added in the form before its questions is written back with none: as loaded, not a bad row
            empty_quiz = code in tasks and tasks[code].method == "quiz" and not _loaded(db, tasks[code])
            if method == "quiz" and not questions.get(code) and not empty_quiz:
                raise RowError("no_questions")
            # A blank package cell gives none; two different ones for one partner can't both hold
            if package and packages.setdefault(partner_name, package) != package:
                raise RowError("package_conflict")
        except RowError as e:
            fail(TASKS_SHEET, n, e)
            continue
        ids.add(code)
        parsed.append((n, code, {"stage_id": stage.id, "type": type_, "text": text, "points": points, "coins": coins,
                                 "coins_from_rule": from_rule, "window_start": window_start, "window_end": window_end,
                                 "method": method, "link": link, "timer_seconds": timer, "position": position,
                                 "active": True, **speed,
                                 # A file without the column (an older one) leaves the limit as it is
                                 **({"limit": limit} if "limit" in task_cols else {})}, requires, partner_name))
    partners = {p.name: p for p in db.scalars(_locked(Partner))}
    # A quiz gated on a QR row that is missing or failed would open to everyone, or never: it fails instead
    loaded_qr = {code for _, code, values, _, _ in parsed if values["method"] == "qr"}
    # The quiz router builds on this module, so it is imported here, not at the top
    from app.routers.quiz import running
    for n, code, values, requires, partner_name in parsed:
        if requires and requires not in loaded_qr:
            fail(TASKS_SHEET, n, "unknown_requires")
            continue
        # A running blitz keeps its settings: judged by the stored window and timer, before the row applies
        old = tasks.get(code)
        if (old is not None and old.method == "quiz"
                and any(k in values and getattr(old, k) != values[k] for k in BLITZ_FIELDS) and running(db, old)):
            fail(TASKS_SHEET, n, "blitz_running")
            continue
        partner = _partner(db, partners, partner_name, notes) if partner_name else None
        if partner is not None:
            # The «Задания» sheet sets the package: the one its rows give, or none
            notes.set("partners", partner, {"package": packages.get(partner_name, "")})
        values["partner_id"] = partner.id if partner else None
        seen.add(code)
        method = values["method"]
        task = tasks.get(code)
        counted = True
        if task is None:
            task = Task(code=code, **values)
            db.add(task)
            tasks[code] = task
            result.added += 1
            notes.added("tasks", task, {"code": code, **values})
            notes.item(TASKS_SHEET, code, values["text"], "added")
        else:
            # Moving a row doesn't count as a change; editing it, or bringing a hidden one back, does
            counted = notes.set("tasks", task, values)
            if counted:
                result.changed += 1
                notes.item(TASKS_SHEET, code, values["text"], "changed")
        if method == "quiz":
            quizzes[code] = (requires, counted, n)
        if method == "qr" and not task.qr_code:
            task.qr_code = _new_qr(db)
    _link_quizzes(db, tasks, quizzes, questions, methods, notes, fail)
    for code, task in tasks.items():
        if code not in seen and task.active:
            notes.set("tasks", task, {"active": False})
            result.hidden += 1
            notes.item(TASKS_SHEET, code, task.text, "hidden")
    if prize_sheet:
        _import_prizes(db, prize_cols, prize_rows, partners, notes, fail)
    if level_sheet:
        _import_levels(db, level_cols, level_rows, notes, fail)
    if result.failed:
        # Refused whole: nothing of it applies, and the counts say so
        db.rollback()
        return ImportResult(failed=result.failed)
    if not apply:
        db.rollback()
        return result
    if record is not None:
        notes.write(db, record)
    db.commit()
    return result


def _link_quizzes(db: DbSession, tasks: dict[str, Task], quizzes: dict[str, tuple[str, bool, int]],
                  questions: dict[str, list[QuestionRow]], methods: dict[str, str | None], notes: _Notes,
                  fail: Callable[[str, int, "str | RowError"], None]) -> None:
    """After all task rows: point each quiz at its «Требует» QR task, save its questions,
    and fail the questions of an ID that isn't a quiz in the file (a quiz row that failed has its own reason).
    A quiz whose blitz is open keeps its questions: changing them fails the quiz's row."""
    # The quiz router builds on this module, so it is imported here, not at the top
    from app.routers.quiz import running
    db.flush()
    for code, (requires, counted, n) in quizzes.items():
        task = tasks[code]
        requires_id = tasks[requires].id if requires else None
        changed = notes.set("tasks", task, {"requires_task_id": requires_id})
        old = _loaded(db, task)
        if _questions_differ(old, questions.get(code, [])):
            if old and running(db, task):
                fail(TASKS_SHEET, n, "quiz_running")
                continue
            notes.log.append(("tasks", task, "questions", len(old), len(questions[code])))
            _save_questions(db, task, old, questions[code])
            changed = True
        if changed and not counted:
            notes.result.changed += 1
            notes.item(TASKS_SHEET, code, task.text, "changed")
    for code, rows in questions.items():
        if methods.get(code) != "quiz":
            for q in rows:
                fail(QUESTIONS_SHEET, q.row, "not_a_quiz")


def _import_prizes(db: DbSession, cols: dict[str, int], rows: list[tuple[int, list]], partners: dict[str, Partner],
                   notes: _Notes, fail: Callable[[str, int, "str | RowError"], None]) -> None:
    result = notes.result
    prizes = {p.code: p for p in db.scalars(_locked(Prize))}
    seen: set[str] = set()
    for position, (n, row) in enumerate(rows):
        try:
            code = _long(_text(_cell(row, cols, "code")), ("prizes", "code"), PRIZE_COLUMNS["code"])
            if not code:
                raise RowError("no_id")
            if code in seen:
                raise RowError("duplicate_id")
            name = _long(_text(_cell(row, cols, "name")), ("prizes", "name"), PRIZE_COLUMNS["name"])
            if not name:
                raise RowError("no_name")
            partner = _long(_text(_cell(row, cols, "partner")), ("partners", "name"), PRIZE_COLUMNS["partner"])
            if not partner:
                raise RowError("no_partner")
            price = _int(_cell(row, cols, "price"), "bad_price", ("prizes", "price"))
            quantity = _int(_cell(row, cols, "quantity"), "bad_quantity", ("prizes", "quantity"))
            prize = prizes.get(code)
            # Bought prizes stay bought: the quantity can't go below them
            if prize is not None and quantity < sold(db, prize.id):
                raise RowError("below_sold")
        except RowError as e:
            fail(PRIZES_SHEET, n, e)
            continue
        seen.add(code)
        # Matched by name, or added with no package: only «Задания» gives packages
        values = {"name": name, "partner_id": _partner(db, partners, partner, notes).id, "price": price,
                  "quantity": quantity, "position": position, "active": True}
        if prize is None:
            prize = Prize(code=code, **values)
            db.add(prize)
            result.prizes_added += 1
            notes.added("prizes", prize, {"code": code, **values})
            notes.item(PRIZES_SHEET, code, name, "added")
        elif notes.set("prizes", prize, values):
            result.prizes_changed += 1
            notes.item(PRIZES_SHEET, code, name, "changed")
    for code, prize in prizes.items():
        if code not in seen and prize.active:
            notes.set("prizes", prize, {"active": False})
            result.prizes_hidden += 1
            notes.item(PRIZES_SHEET, code, prize.name, "hidden")


def sold(db: DbSession, prize_id: int) -> int:
    return db.scalar(select(func.count()).where(Redemption.prize_id == prize_id))


def _import_levels(db: DbSession, cols: dict[str, int], rows: list[tuple[int, list]], notes: _Notes,
                   fail: Callable[[str, int, "str | RowError"], None]) -> None:
    """The levels are replaced as a whole by the sheet's."""
    levels: list[tuple[str, int]] = []
    for n, row in rows:
        try:
            name = _long(_text(_cell(row, cols, "name")), ("levels", "name"), LEVEL_COLUMNS["name"])
            if not name:
                raise RowError("no_name")
            points = _int(_cell(row, cols, "min_points"), "bad_level_points", ("levels", "min_points"))
            if n == rows[0][0] and points != 0:
                raise RowError("no_zero_level")
            if levels and points <= levels[-1][1]:
                raise RowError("levels_out_of_order")
        except RowError as e:
            fail(LEVELS_SHEET, n, e)
            continue
        levels.append((name, points))
    if not rows:
        # A header with no levels under it: there is no 0 level
        fail(LEVELS_SHEET, 2, "no_zero_level")
    old = [(lv.name, lv.min_points) for lv in db.scalars(select(Level).order_by(Level.min_points))]
    if notes.result.failed or levels == old:
        return
    db.execute(delete(Level))
    db.add_all(Level(name=name, min_points=points) for name, points in levels)
    notes.result.levels_changed = True
    notes.item(LEVELS_SHEET, "", "", "changed")
    shown = "; ".join(f"{name} {points}" for name, points in old)
    notes.log.append(("levels", LEVELS_SHEET, "levels", shown, "; ".join(f"{name} {points}" for name, points in levels)))


def _new_qr(db: DbSession) -> str:
    db.flush()
    while True:
        code = random_code()
        if not db.scalar(select(Task.id).where(Task.qr_code == code)):
            return code


def _local(dt: datetime | None) -> datetime | None:
    # Excel has no time zones: write Dushanbe wall-clock time, which is how the admin typed it
    return dt.astimezone(EVENT_TZ).replace(tzinfo=None) if dt else None


def _number(d: Decimal) -> int | float:
    """1, 1.5: a number cell, without trailing zeros."""
    return int(d) if d == d.to_integral_value() else float(d)


def export_xlsx(db: DbSession) -> bytes:
    """All five sheets with what is loaded now; with nothing loaded, an empty template with the right columns
    (and the levels, which start as TAG's five)."""
    wb = Workbook()
    ws = wb.active
    ws.title = STAGES_SHEET
    ws.append(list(STAGE_COLUMNS.values()))
    stages = list(db.scalars(select(Stage).order_by(Stage.number)))
    # A switched-off stage stays out of the file; uploading it back leaves it off
    for s in stages:
        if s.active:
            ws.append([s.number, s.name, _local(s.starts_at), _local(s.ends_at), s.message,
                       YES[0] if s.market else None, s.batch_size, _number(s.multiplier)])
    for col in "CD":
        for cell in ws[col][1:]:
            cell.number_format = EXCEL_DATE

    wt = wb.create_sheet(TASKS_SHEET)
    wt.append(list(TASK_COLUMNS.values()))
    numbers = {s.id: s.number for s in stages}
    partners = {p.id: p for p in db.scalars(select(Partner))}
    active = list(db.scalars(select(Task).where(Task.active).order_by(Task.position, Task.id)))
    codes = {t.id: t.code for t in active}
    for t in active:
        # «Партнёр» and «Пакет партнёра» are written back from the partner
        partner = partners.get(t.partner_id)
        wt.append([t.code, numbers[t.stage_id], TYPES[t.type][0], t.text, t.points,
                   None if t.coins_from_rule else t.coins, partner.name if partner else "",
                   PACKAGES[partner.package][0] if partner and partner.package else None,
                   _local(t.window_start), _local(t.window_end),
                   METHODS[t.method][0] if t.method else None, t.link or None, t.timer_seconds,
                   codes.get(t.requires_task_id), t.limit,
                   *([YES[0] if t.blitz else None, t.speed_bonus, t.grace_seconds, t.bonus_seconds]
                     if t.method == "quiz" else [None] * 4)])
    for col in "IJ":
        for cell in wt[col][1:]:
            cell.number_format = EXCEL_DATE

    wp = wb.create_sheet(PRIZES_SHEET)
    wp.append(list(PRIZE_COLUMNS.values()))
    for p in db.scalars(select(Prize).where(Prize.active).order_by(Prize.position, Prize.id)):
        wp.append([p.code, p.name, partners[p.partner_id].name, p.price, p.quantity])

    wq = wb.create_sheet(QUESTIONS_SHEET)
    wq.append(list(QUESTION_COLUMNS.values()))
    order = {t.id: i for i, t in enumerate(active) if t.method == "quiz"}
    loaded = db.scalars(select(Question).where(Question.task_id.in_(list(order))))
    for q in sorted(loaded, key=lambda q: (order[q.task_id], q.number)):
        wq.append([codes[q.task_id], q.number, q.text, q.option1, q.option2, q.option3, q.option4, q.correct])

    wl = wb.create_sheet(LEVELS_SHEET)
    wl.append(list(LEVEL_COLUMNS.values()))
    for lv in db.scalars(select(Level).order_by(Level.min_points)):
        wl.append([lv.name, lv.min_points])

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
