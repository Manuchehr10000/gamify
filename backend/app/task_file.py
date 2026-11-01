"""The admin's Excel file: sheet «Этапы» (the day's schedule), sheet «Задания» (the task catalog),
sheet «Вопросы» (the quizzes' questions), sheet «Призы» (the market's prizes) and sheet «Уровни» (the levels by points).

Upload reads both sheets; download writes them back the same way, so the file can be edited and uploaded again.
"""
import io
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from openpyxl import Workbook, load_workbook
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from app.guests import random_code
from app.models import Level, Prize, Question, Stage, Task
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
DATE_FORMATS = ("%d.%m.%Y %H:%M", "%d.%m.%Y %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S")
EXCEL_DATE = "DD.MM.YYYY HH:MM"


def rule_coins(points: int, partner: bool) -> int:
    """Coins when the cell is blank: 1:1 with points; ×1.5 rounded up for partner tasks (TAG's rules, 3.1–3.2)."""
    return math.ceil(points * 1.5) if partner else points


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
    # The «Уровни» sheet replaced the levels (it failed whole, or matched what was loaded, otherwise)
    levels_changed: bool = False
    failed: list[dict] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


class RowError(Exception):
    pass


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


def _int(v, reason: str) -> int:
    s = _text(v).replace(",", ".")
    try:
        n = float(s)
    except ValueError:
        raise RowError(reason) from None
    if not n.is_integer() or n < 0:
        raise RowError(reason)
    return int(n)


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
               fail: Callable[[str, int, str], None]) -> dict[str, list[QuestionRow]]:
    """The «Вопросы» sheet grouped by task ID; a bad row fails on its own and the others load."""
    by_task: dict[str, list[QuestionRow]] = {}
    for n, row in rows:
        try:
            code = _text(_cell(row, cols, "task"))
            if not code:
                raise RowError("no_task_id")
            number = _int(_cell(row, cols, "number"), "bad_question_number")
            if number < 1:
                raise RowError("bad_question_number")
            if any(q.number == number for q in by_task.get(code, [])):
                raise RowError("duplicate_question")
            text = _text(_cell(row, cols, "text"))
            if not text:
                raise RowError("no_question")
            cells = [_text(_cell(row, cols, k)) for k in OPTIONS]
            options = [c for c in cells if c]
            # 2–4 options, filled from «Вариант 1» on, so «Правильный» points at the column the admin sees
            if len(options) < 2 or cells[:len(options)] != options:
                raise RowError("bad_options")
            correct = _int(_cell(row, cols, "correct"), "bad_correct")
            if not 1 <= correct <= len(options):
                raise RowError("bad_correct")
        except RowError as e:
            fail(QUESTIONS_SHEET, n, str(e))
            continue
        by_task.setdefault(code, []).append(QuestionRow(n, number, text, options, correct))
    return by_task


def _save_questions(db: DbSession, task: Task, rows: list[QuestionRow]) -> bool:
    """Replace a quiz's questions with the file's; True when they differ from what was loaded."""
    old = list(db.scalars(select(Question).where(Question.task_id == task.id).order_by(Question.number)))
    new = sorted(rows, key=lambda q: q.number)
    as_rows = [(q.number, q.text, [o for o in (q.option1, q.option2, q.option3, q.option4) if o], q.correct)
               for q in old]
    if as_rows == [(q.number, q.text, q.options, q.correct) for q in new]:
        return False
    for q in old:
        db.delete(q)
    db.flush()
    for q in new:
        opts = q.options + [None] * (4 - len(q.options))
        db.add(Question(task_id=task.id, number=q.number, text=q.text, option1=opts[0], option2=opts[1],
                        option3=opts[2], option4=opts[3], correct=q.correct))
    return True


def import_xlsx(db: DbSession, raw: bytes) -> ImportResult:
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

    def fail(sheet: str, row: int, reason: str) -> None:
        result.failed.append({"sheet": sheet, "row": row, "reason": reason})

    stages = {s.number: s for s in db.scalars(select(Stage))}
    seen_stages: set[int] = set()
    for n, row in stage_rows:
        try:
            number = _int(_cell(row, stage_cols, "number"), "bad_stage_number")
            if number < 1:
                raise RowError("bad_stage_number")
            if number in seen_stages:
                raise RowError("duplicate_stage")
            name = _text(_cell(row, stage_cols, "name"))
            if not name:
                raise RowError("no_name")
            starts = _time(_cell(row, stage_cols, "starts_at"), "bad_start")
            ends = _time(_cell(row, stage_cols, "ends_at"), "bad_end")
            if ends <= starts:
                raise RowError("end_before_start")
            market_cell = _text(_cell(row, stage_cols, "market")).lower()
            if market_cell not in YES + NO:
                raise RowError("bad_market")
        except RowError as e:
            fail(STAGES_SHEET, n, str(e))
            continue
        seen_stages.add(number)
        values = {"name": name, "starts_at": starts, "ends_at": ends,
                  "message": _text(_cell(row, stage_cols, "message")), "market": market_cell in YES}
        stage = stages.get(number)
        if stage is None:
            stage = Stage(number=number, **values)
            db.add(stage)
            stages[number] = stage
            result.stages_added += 1
        elif any(getattr(stage, k) != v for k, v in values.items()):
            for k, v in values.items():
                setattr(stage, k, v)
            result.stages_changed += 1
    db.flush()

    questions = _questions(question_cols, question_rows, fail)
    tasks = {t.code: t for t in db.scalars(select(Task))}
    seen: set[str] = set()
    methods = {_text(_cell(r, task_cols, "code")): _lookup(METHODS, _text(_cell(r, task_cols, "method")))
               for _, r in task_rows}
    # Rows that passed their own checks; «Требует» is checked once all rows are read, since its QR row may sit lower
    parsed: list[tuple[int, str, dict, str]] = []
    ids: set[str] = set()
    # Quiz rows loaded in this upload: their «Требует» and whether they already count as added or changed
    quizzes: dict[str, tuple[str, bool]] = {}
    for position, (n, row) in enumerate(task_rows):
        try:
            code = _text(_cell(row, task_cols, "code"))
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
            text = _text(_cell(row, task_cols, "text"))
            if not text:
                raise RowError("no_text")
            if not _text(_cell(row, task_cols, "points")):
                raise RowError("no_points")
            points = _int(_cell(row, task_cols, "points"), "bad_points")
            partner_name = _text(_cell(row, task_cols, "partner_name"))
            package_cell = _text(_cell(row, task_cols, "partner_package"))
            package = _lookup(PACKAGES, package_cell) if package_cell else ""
            if package is None:
                raise RowError("unknown_package")
            if package and not partner_name:
                raise RowError("no_partner_name")
            coins_cell = _cell(row, task_cols, "coins")
            from_rule = not _text(coins_cell)
            coins = rule_coins(points, bool(partner_name)) if from_rule else _int(coins_cell, "bad_coins")
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
            link = _text(_cell(row, task_cols, "link")) if method == "link" else ""
            if method == "link" and not link:
                raise RowError("no_link")
            if link and not re.match(r"https?://\S+$", link):
                raise RowError("bad_link")
            timer_cell = _cell(row, task_cols, "timer") if method == "quiz" else None
            timer = _int(timer_cell, "bad_timer") if _text(timer_cell) else None
            if timer == 0:
                raise RowError("bad_timer")
            requires = _text(_cell(row, task_cols, "requires")) if method == "quiz" else ""
            if method == "quiz" and not questions.get(code):
                raise RowError("no_questions")
        except RowError as e:
            fail(TASKS_SHEET, n, str(e))
            continue
        ids.add(code)
        parsed.append((n, code, {"stage_id": stage.id, "type": type_, "text": text, "points": points, "coins": coins,
                                 "coins_from_rule": from_rule, "partner_name": partner_name,
                                 "partner_package": package, "window_start": window_start, "window_end": window_end,
                                 "method": method, "link": link, "timer_seconds": timer, "position": position,
                                 "active": True}, requires))
    # A quiz gated on a QR row that is missing or failed would open to everyone, or never: it fails instead
    loaded_qr = {code for _, code, values, _ in parsed if values["method"] == "qr"}
    for n, code, values, requires in parsed:
        if requires and requires not in loaded_qr:
            fail(TASKS_SHEET, n, "unknown_requires")
            continue
        seen.add(code)
        method = values["method"]
        task = tasks.get(code)
        counted = True
        if task is None:
            task = Task(code=code, **values)
            db.add(task)
            tasks[code] = task
            result.added += 1
        else:
            # Moving a row doesn't count as a change; editing it, or bringing a hidden one back, does
            counted = any(getattr(task, k) != v for k, v in values.items() if k != "position")
            if counted:
                result.changed += 1
            for k, v in values.items():
                setattr(task, k, v)
        if method == "quiz":
            quizzes[code] = (requires, counted)
        if method == "qr" and not task.qr_code:
            task.qr_code = _new_qr(db)
    _link_quizzes(db, tasks, quizzes, questions, methods, result, fail)
    for code, task in tasks.items():
        if code not in seen and task.active:
            task.active = False
            result.hidden += 1
    if prize_sheet:
        _import_prizes(db, prize_cols, prize_rows, result, fail)
    if level_sheet:
        _import_levels(db, level_cols, level_rows, result, fail)
    db.commit()
    return result


def _link_quizzes(db: DbSession, tasks: dict[str, Task], quizzes: dict[str, tuple[str, bool]],
                  questions: dict[str, list[QuestionRow]], methods: dict[str, str | None], result: ImportResult,
                  fail: Callable[[str, int, str], None]) -> None:
    """After all task rows: point each quiz at its «Требует» QR task, save its questions,
    and fail the questions of an ID that isn't a quiz in the file (a quiz row that failed has its own reason)."""
    db.flush()
    for code, (requires, counted) in quizzes.items():
        task = tasks[code]
        requires_id = tasks[requires].id if requires else None
        changed = task.requires_task_id != requires_id
        task.requires_task_id = requires_id
        changed = _save_questions(db, task, questions[code]) or changed
        if changed and not counted:
            result.changed += 1
    for code, rows in questions.items():
        if methods.get(code) != "quiz":
            for q in rows:
                fail(QUESTIONS_SHEET, q.row, "not_a_quiz")


def _import_prizes(db: DbSession, cols: dict[str, int], rows: list[tuple[int, list]], result: ImportResult,
                   fail: Callable[[str, int, str], None]) -> None:
    prizes = {p.code: p for p in db.scalars(select(Prize))}
    seen: set[str] = set()
    for position, (n, row) in enumerate(rows):
        try:
            code = _text(_cell(row, cols, "code"))
            if not code:
                raise RowError("no_id")
            if code in seen:
                raise RowError("duplicate_id")
            name = _text(_cell(row, cols, "name"))
            if not name:
                raise RowError("no_name")
            partner = _text(_cell(row, cols, "partner"))
            if not partner:
                raise RowError("no_partner")
            price = _int(_cell(row, cols, "price"), "bad_price")
            if price < 1:
                raise RowError("bad_price")
            quantity = _int(_cell(row, cols, "quantity"), "bad_quantity")
        except RowError as e:
            fail(PRIZES_SHEET, n, str(e))
            continue
        seen.add(code)
        values = {"name": name, "partner": partner, "price": price, "quantity": quantity,
                  "position": position, "active": True}
        prize = prizes.get(code)
        if prize is None:
            db.add(Prize(code=code, **values))
            result.prizes_added += 1
        else:
            if any(getattr(prize, k) != v for k, v in values.items() if k != "position"):
                result.prizes_changed += 1
            for k, v in values.items():
                setattr(prize, k, v)
    for code, prize in prizes.items():
        if code not in seen and prize.active:
            prize.active = False
            result.prizes_hidden += 1


def _import_levels(db: DbSession, cols: dict[str, int], rows: list[tuple[int, list]], result: ImportResult,
                   fail: Callable[[str, int, str], None]) -> None:
    """The levels go in whole or not at all: a bad sheet fails with the reason and the old levels stay."""
    levels: list[tuple[str, int]] = []
    failed = False
    for n, row in rows:
        try:
            name = _text(_cell(row, cols, "name"))
            if not name:
                raise RowError("no_name")
            points = _int(_cell(row, cols, "min_points"), "bad_level_points")
            if n == rows[0][0] and points != 0:
                raise RowError("no_zero_level")
            if levels and points <= levels[-1][1]:
                raise RowError("levels_out_of_order")
        except RowError as e:
            fail(LEVELS_SHEET, n, str(e))
            failed = True
            continue
        levels.append((name, points))
    if not rows:
        # A header with no levels under it: there is no 0 level
        fail(LEVELS_SHEET, 2, "no_zero_level")
        failed = True
    old = [(lv.name, lv.min_points) for lv in db.scalars(select(Level).order_by(Level.min_points))]
    if failed or levels == old:
        return
    db.execute(delete(Level))
    db.add_all(Level(name=name, min_points=points) for name, points in levels)
    result.levels_changed = True


def _new_qr(db: DbSession) -> str:
    db.flush()
    while True:
        code = random_code()
        if not db.scalar(select(Task.id).where(Task.qr_code == code)):
            return code


def _local(dt: datetime | None) -> datetime | None:
    # Excel has no time zones: write Dushanbe wall-clock time, which is how the admin typed it
    return dt.astimezone(EVENT_TZ).replace(tzinfo=None) if dt else None


def export_xlsx(db: DbSession) -> bytes:
    """All five sheets with what is loaded now; with nothing loaded, an empty template with the right columns
    (and the levels, which start as TAG's five)."""
    wb = Workbook()
    ws = wb.active
    ws.title = STAGES_SHEET
    ws.append(list(STAGE_COLUMNS.values()))
    stages = list(db.scalars(select(Stage).order_by(Stage.number)))
    for s in stages:
        ws.append([s.number, s.name, _local(s.starts_at), _local(s.ends_at), s.message, YES[0] if s.market else None])
    for col in "CD":
        for cell in ws[col][1:]:
            cell.number_format = EXCEL_DATE

    wt = wb.create_sheet(TASKS_SHEET)
    wt.append(list(TASK_COLUMNS.values()))
    numbers = {s.id: s.number for s in stages}
    active = list(db.scalars(select(Task).where(Task.active).order_by(Task.position, Task.id)))
    codes = {t.id: t.code for t in active}
    for t in active:
        wt.append([t.code, numbers[t.stage_id], TYPES[t.type][0], t.text, t.points,
                   None if t.coins_from_rule else t.coins, t.partner_name,
                   PACKAGES[t.partner_package][0] if t.partner_package else None,
                   _local(t.window_start), _local(t.window_end),
                   METHODS[t.method][0] if t.method else None, t.link or None, t.timer_seconds,
                   codes.get(t.requires_task_id)])
    for col in "IJ":
        for cell in wt[col][1:]:
            cell.number_format = EXCEL_DATE

    wp = wb.create_sheet(PRIZES_SHEET)
    wp.append(list(PRIZE_COLUMNS.values()))
    for p in db.scalars(select(Prize).where(Prize.active).order_by(Prize.position, Prize.id)):
        wp.append([p.code, p.name, p.partner, p.price, p.quantity])

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
