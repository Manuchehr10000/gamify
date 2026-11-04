"""/admin/settings: the lists, the game settings, partner logos and the change log. Every save checks the version
the form read, says first what it changes in the live game, moves the config version and writes the log."""
import io
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from openpyxl import Workbook
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.orm import Session as DbSession

from app import badges, changes, photos, settings, stages
from app.admin_lists import KINDS, Kind, parse, refuse, row_out, schema, set_secret
from app.auth import require_role
from app.db import get_db
from app.models import ChangeEvent, Partner, Session, Setting, Staff, Task
from app.routers.admin_tasks import XLSX
from app.routers.live import cell
from app.stages import EVENT_TZ
from app.task_file import rule_coins

ADMIN = require_role("admin")
router = APIRouter(prefix="/api/admin", dependencies=[Depends(ADMIN)])

STALE = "stale"
LOGO_MAX = 1024 * 1024
PNG = b"\x89PNG\r\n\x1a\n"
JPEG = b"\xff\xd8\xff"


def _kind(kind: str) -> Kind:
    if kind not in KINDS:
        raise HTTPException(404, "unknown_kind")
    return KINDS[kind]


def _lock_guests(db: DbSession, k: Kind) -> None:
    """A save that rechecks badges locks every guest first, before its own row: guests before tasks, everywhere."""
    if k.recheck is not None:
        badges.lock_all(db)


def _locked_row(db: DbSession, k: Kind, row_id: int):
    row = db.get(k.model, row_id, with_for_update=True, populate_existing=True)
    if row is None:
        raise HTTPException(404, "not_found")
    return row


def _confirm(db: DbSession, impact: list[dict], confirm: bool) -> None:
    """A change that hits the live game is only saved when resent with confirm; until then nothing is kept."""
    if impact and not confirm:
        db.rollback()
        raise refuse("confirm", status=409, impact=impact)


def _flush(db: DbSession) -> None:
    try:
        db.flush()
    except (IntegrityError, StaleDataError):
        # Two admins adding the same ID at once, or a row another save moved: refused like a stale save
        db.rollback()
        raise refuse(STALE, status=409) from None


def _columns(k: Kind) -> list[str]:
    return [f.name for f in k.fields if f.type != "secret"]


def _apply(db: DbSession, k: Kind, row: object, values: dict, creating: bool) -> list[tuple[str, object, object]]:
    """Put the values on the row and run its checks; the fields that changed, with old and new values."""
    with db.no_autoflush:
        return _apply_unflushed(db, k, row, values, creating)


def _apply_unflushed(db: DbSession, k: Kind, row: object, values: dict,
                     creating: bool) -> list[tuple[str, object, object]]:
    before = {name: getattr(row, name, None) for name in _columns(k)}
    for name, value in values.items():
        if name in k.secret_fields:
            if value is not None:
                set_secret(db, row, value)
        else:
            setattr(row, name, value)
    if creating and k.secret_fields and not any(values.get(s) for s in k.secret_fields):
        raise refuse("required", field=k.secret_fields[0])
    k.after(db, row, values)
    k.check(db, row, creating)
    diff = [(name, before[name], getattr(row, name)) for name in _columns(k) if before[name] != getattr(row, name)]
    diff += [(name, None, "••••") for name in k.secret_fields if values.get(name)]
    return diff


def _out(db: DbSession, k: Kind, row: object) -> dict:
    return row_out(k, row, k.extra(db, [row]).get(row.id, {}))


def _record_values(db: DbSession, admin: Staff, kind: str, row: object, item: str, added: bool) -> None:
    for name in _columns(KINDS[kind]):
        value = changes.shown(db, name, getattr(row, name))
        if value is not None and value != "":
            changes.record(db, admin, kind, row.id, item, name, None if added else value, value if added else None)


class ListOut(BaseModel):
    fields: list[dict]
    rows: list[dict]


@router.get("/lists/{kind}")
def list_rows(kind: str, db: DbSession = Depends(get_db)) -> ListOut:
    k = _kind(kind)
    if k.refresh is not None:
        k.refresh(db)
        db.commit()
    rows = list(db.scalars(select(k.model).order_by(*k.order())))
    extra = k.extra(db, rows)
    return ListOut(fields=schema(db, k), rows=[row_out(k, r, extra.get(r.id, {})) for r in rows])


@router.post("/lists/{kind}")
def add_row(kind: str, values: dict = Body(embed=True), confirm: bool = False, admin: Staff = Depends(ADMIN),
            db: DbSession = Depends(get_db)) -> dict:
    k = _kind(kind)
    _lock_guests(db, k)
    parsed = parse(db, k, values, None)
    before = k.state(db, None)
    row = k.model()
    if "active" in {f.name for f in k.fields}:
        row.active = parsed.get("active", True)
    _apply(db, k, row, parsed, creating=True)
    with db.no_autoflush:
        k.lock(db, row)
    db.add(row)
    _flush(db)
    _confirm(db, k.impact(db, row, before, False), confirm)
    if k.recheck is not None:
        k.recheck(db)
    item = changes.label(db, row)
    changes.record(db, admin, kind, row.id, item, changes.CREATED)
    # The new row's values, so the log holds what was added
    _record_values(db, admin, kind, row, item, added=True)
    settings.bump(db)
    db.commit()
    return _out(db, k, row)


@router.put("/lists/{kind}/{row_id}")
def save_row(kind: str, row_id: int, values: dict = Body(), version: int = Body(), confirm: bool = False,
             admin: Staff = Depends(ADMIN), db: DbSession = Depends(get_db)) -> dict:
    k = _kind(kind)
    _lock_guests(db, k)
    row = _locked_row(db, k, row_id)
    # Read under the row's lock: of two admins saving at once, the second finds the version moved
    if row.version != version:
        db.rollback()
        raise refuse(STALE, status=409)
    parsed = parse(db, k, values, row)
    k.lock(db, row)
    before = k.state(db, row)
    # One flush for the whole save: the checks' queries don't write a half-applied row (or move its version twice)
    with db.no_autoflush:
        diff = _apply(db, k, row, parsed, creating=False)
        if not diff:
            db.rollback()
            return _out(db, k, _locked_row(db, k, row_id))
        # A question moved to another quiz is locked by that quiz's blitz too
        k.lock(db, row)
    _flush(db)
    _confirm(db, k.impact(db, row, before, False), confirm)
    if k.recheck is not None:
        k.recheck(db)
    item = changes.label(db, row)
    for name, old, new in diff:
        changes.record(db, admin, kind, row.id, item, name, changes.shown(db, name, old), changes.shown(db, name, new))
    settings.bump(db)
    db.commit()
    return _out(db, k, row)


@router.delete("/lists/{kind}/{row_id}")
def delete_row(kind: str, row_id: int, confirm: bool = False, admin: Staff = Depends(ADMIN),
               db: DbSession = Depends(get_db)) -> dict:
    """Only a row nothing uses: one other data uses is switched off instead."""
    k = _kind(kind)
    _lock_guests(db, k)
    row = _locked_row(db, k, row_id)
    reason = k.keep(db, row)
    if reason:
        db.rollback()
        raise refuse(reason, status=409)
    k.lock(db, row)
    before = k.state(db, row)
    item = changes.label(db, row)
    _confirm(db, k.impact(db, row, before, True), confirm)
    # The deleted row's values, so the log still holds them
    _record_values(db, admin, kind, row, item, added=False)
    if isinstance(row, Staff):
        # Its sessions go with it
        db.execute(delete(Session).where(Session.staff_id == row.id))
    db.delete(row)
    _flush(db)
    if k.recheck is not None:
        k.recheck(db)
    changes.record(db, admin, kind, row_id, item, changes.DELETED)
    settings.bump(db)
    db.commit()
    return {"id": row_id}


# Settings --------------------------------------------------------------------------------------------------------

class SettingOut(BaseModel):
    key: str
    value: float
    min: float
    max: float
    effect: str
    integer: bool
    # A text setting's value (min and max are then its length); None for a number
    text: str | None
    # The ids a choice setting (the skin) takes; None for the others
    choices: list[str] | None
    version: int


def _setting_out(s: Setting) -> SettingOut:
    spec = settings.SETTINGS[s.key]
    return SettingOut(key=s.key, value=float(s.value), min=float(s.min_value), max=float(s.max_value),
                      effect=s.effect, integer=spec.integer, text=s.text_value if spec.text is not None else None,
                      choices=list(spec.choices) if spec.choices else None, version=s.version)


@router.get("/settings")
def list_settings(db: DbSession = Depends(get_db)) -> list[SettingOut]:
    rows = {s.key: s for s in db.scalars(select(Setting).where(Setting.key.in_(list(settings.SETTINGS))))}
    return [_setting_out(rows[k]) for k in settings.SETTINGS if k in rows]


@router.put("/settings/{key}")
def save_setting(key: str, value: str | float = Body(), version: int = Body(), confirm: bool = False,
                 admin: Staff = Depends(ADMIN), db: DbSession = Depends(get_db)) -> SettingOut:
    spec = settings.SETTINGS.get(key)
    if spec is None:
        raise HTTPException(404, "unknown_setting")
    s = db.get(Setting, key, with_for_update=True, populate_existing=True)
    if s.version != version:
        db.rollback()
        raise refuse(STALE, status=409)
    if spec.text is not None:
        return _save_text(db, admin, s, value, confirm)
    try:
        new = Decimal(str(value).replace(",", ".")).normalize()
    except InvalidOperation:
        raise refuse("bad_value", field=key) from None
    if not new.is_finite():
        # «NaN» and «Infinity» parse as numbers but compare with nothing
        raise refuse("bad_value", field=key)
    if not s.min_value <= new <= s.max_value or (spec.integer and new != new.to_integral_value()) or (
            new.as_tuple().exponent < -2):
        raise refuse("out_of_range", field=key, min=float(s.min_value), max=float(s.max_value))
    if new == s.value:
        db.rollback()
        return _setting_out(s)
    impact = []
    rule_tasks = []
    if key == "partner_coin_multiplier":
        # Tasks whose coins follow the rule pay the new coins from now on; coins already paid stay
        # Locked, so a form save of one of them waits and is then refused as stale, not failed
        rule_tasks = list(db.scalars(select(Task).where(Task.coins_from_rule, Task.partner_id.is_not(None))
                                     .order_by(Task.id).with_for_update().execution_options(populate_existing=True)))
        impact.append({"code": "rule_coins", "count": len(rule_tasks)})
    if spec.live and stages.day(db).state == "running":
        impact.append({"code": "setting_live"})
    _confirm(db, impact, confirm)
    old = s.value
    s.value = new
    changes.record(db, admin, "settings", None, key, "value", old, new)
    for t in rule_tasks:
        coins = rule_coins(t.points, True, new)
        if coins != t.coins:
            changes.record(db, admin, "tasks", t.id, t.code, "coins", t.coins, coins)
            t.coins = coins
    _flush(db)
    settings.bump(db)
    db.commit()
    return _setting_out(s)


def _save_text(db: DbSession, admin: Staff, s: Setting, value: str | float, confirm: bool) -> SettingOut:
    """A text setting (a push text, a date kept as YYYY-MM-DD, or the skin): its length is checked against the limits,
    a date must be one and a choice one of its ids; it applies from now on."""
    new = value.strip() if isinstance(value, str) else None
    choices = settings.SETTINGS[s.key].choices
    if choices and new not in choices:
        raise refuse("bad_value", field=s.key)
    # Once admins are warned (7 days before), the deletion date stays as announced
    if s.key == "photo_delete_date" and photos.locked(db):
        db.rollback()
        raise refuse("photo_date_locked", status=409)
    if settings.SETTINGS[s.key].date and new:
        try:
            new = date.fromisoformat(new).isoformat()
        except ValueError:
            raise refuse("bad_value", field=s.key) from None
    # A new date, or a blank one falling back to the stages' default, leaves admins their 7 days' warning
    if s.key == "photo_delete_date" and new is not None and photos.too_soon(
            date.fromisoformat(new) if new else photos.default_date(db)):
        db.rollback()
        raise refuse("photo_date_too_soon", status=409)
    if new is None or not s.min_value <= len(new) <= s.max_value:
        raise refuse("length", field=s.key, min=int(s.min_value), max=int(s.max_value))
    if new == s.text_value:
        db.rollback()
        return _setting_out(s)
    if choices:
        # A new skin switches every phone, stand and the hall screen within seconds, game running or not
        _confirm(db, [{"code": "skin"}], confirm)
    changes.record(db, admin, "settings", None, s.key, "value", s.text_value, new)
    s.text_value = new
    _flush(db)
    settings.bump(db)
    db.commit()
    return _setting_out(s)


# Partner logos ---------------------------------------------------------------------------------------------------

def image_type(data: bytes) -> str | None:
    """PNG or JPEG, told from the bytes; SVG is refused, since it can carry script."""
    if data.startswith(PNG):
        return "image/png"
    if data.startswith(JPEG):
        return "image/jpeg"
    return None


@router.post("/partners/{partner_id}/logo")
def upload_logo(partner_id: int, file: UploadFile, admin: Staff = Depends(ADMIN),
                db: DbSession = Depends(get_db)) -> dict:
    data = file.file.read(LOGO_MAX + 1)
    if len(data) > LOGO_MAX:
        raise HTTPException(413, "logo_too_large")
    if image_type(data) is None:
        raise HTTPException(400, "not_png_or_jpeg")
    p = db.get(Partner, partner_id, with_for_update=True)
    if p is None:
        raise HTTPException(404, "not_found")
    had = db.scalar(select(Partner.logo.is_not(None)).where(Partner.id == partner_id))
    p.logo = data
    changes.record(db, admin, "partners", p.id, p.name, "logo", "загружен" if had else None, "загружен")
    settings.bump(db)
    db.commit()
    return _out(db, KINDS["partners"], p)


# Change log ------------------------------------------------------------------------------------------------------

class Event(BaseModel):
    id: int
    created_at: datetime
    staff_id: int | None
    staff_name: str
    kind: str
    item: str
    field: str
    old_value: str | None
    new_value: str | None
    source: str


def _events(db: DbSession, kind: str, item: str, staff_id: int | None, date_from: date | None,
            date_to: date | None):
    q = select(ChangeEvent)
    if kind:
        q = q.where(ChangeEvent.kind == kind)
    if item.strip():
        q = q.where(func.lower(ChangeEvent.item).contains(item.strip().lower()))
    if staff_id is not None:
        q = q.where(ChangeEvent.staff_id == staff_id)
    # Dates are Dushanbe days
    if date_from:
        q = q.where(ChangeEvent.created_at >= datetime.combine(date_from, time(), EVENT_TZ))
    if date_to:
        q = q.where(ChangeEvent.created_at < datetime.combine(date_to + timedelta(days=1), time(), EVENT_TZ))
    return q.order_by(ChangeEvent.id.desc())


LOG_LIMIT = 500


@router.get("/log")
def change_log(kind: str = "", item: str = "", staff_id: int | None = None, date_from: date | None = None,
               date_to: date | None = None, db: DbSession = Depends(get_db)) -> list[Event]:
    """The newest changes first, the latest 500 of the filter; the export holds them all."""
    rows = db.scalars(_events(db, kind, item, staff_id, date_from, date_to).limit(LOG_LIMIT))
    return [Event(id=e.id, created_at=e.created_at.astimezone(EVENT_TZ), staff_id=e.staff_id,
                  staff_name=e.staff_name, kind=e.kind, item=e.item, field=e.field, old_value=e.old_value,
                  new_value=e.new_value, source=e.source) for e in rows]


LOG_HEAD = ["Время", "Администратор", "Раздел", "Запись", "Поле", "Было", "Стало", "Источник"]
KIND_NAMES = {"stages": "Этапы", "tasks": "Задания", "prizes": "Призы", "questions": "Вопросы", "levels": "Уровни",
              "partners": "Партнёры", "staff": "Доступ", "settings": "Настройки", "rating": "Рейтинг",
              "guests": "Гости", "push": "Push", "badges": "Бейджи"}
SOURCES = {"form": "Форма", "excel": "Excel"}
# The file names fields as the forms and the Excel sheets do
FIELD_NAMES = {
    changes.CREATED: "Добавлено", changes.DELETED: "Удалено", "active": "Включено", "number": "Номер",
    "name": "Название", "starts_at": "Начало", "ends_at": "Конец", "message": "Сообщение при смене этапа",
    "market": "Маркет", "code": "ID", "stage_id": "Этап", "type": "Тип", "text": "Текст", "points": "Баллы",
    "coins": "Монеты", "partner_id": "Партнёр", "method": "Выполнение", "link": "Ссылка",
    "window_start": "Доступно с", "window_end": "Доступно до", "timer_seconds": "Таймер, сек",
    "requires_task_id": "Требует", "limit": "Лимит", "batch_size": "Карточек в ленте", "multiplier": "Множитель",
    "questions": "Вопросы",
    "price": "Цена в монетах", "quantity": "Количество",
    "task_id": "Задание", "option1": "Вариант 1", "option2": "Вариант 2", "option3": "Вариант 3",
    "option4": "Вариант 4", "correct": "Правильный", "min_points": "Баллов от", "levels": "Уровни",
    "package": "Пакет партнёра", "logo": "Логотип", "role": "Роль", "secret": "PIN / пароль",
    "value": "Значение", "frozen": "Заморожен", "_import": "Загрузка списка",
    "kind": "Вид", "at": "Время", "title": "Заголовок", "state": "Состояние",
    "rule": "Тип правила", "count": "Число", "kinds": "Тип задания", "any_partner": "Любой один партнёр",
    "on_screen": "На экран",
}


@router.get("/log/export")
def export_log(kind: str = "", item: str = "", staff_id: int | None = None, date_from: date | None = None,
               date_to: date | None = None, db: DbSession = Depends(get_db)) -> Response:
    wb = Workbook()
    ws = wb.active
    ws.title = "Журнал"
    ws.append(LOG_HEAD)
    for e in db.scalars(_events(db, kind, item, staff_id, date_from, date_to)):
        ws.append([e.created_at.astimezone(EVENT_TZ).replace(tzinfo=None), cell(e.staff_name),
                   KIND_NAMES.get(e.kind, e.kind), cell(e.item), FIELD_NAMES.get(e.field, e.field), cell(e.old_value or ""),
                   cell(e.new_value or ""), SOURCES.get(e.source, e.source)])
    for c in ws["A"][1:]:
        c.number_format = "DD.MM.YYYY HH:MM:SS"
    out = io.BytesIO()
    wb.save(out)
    return Response(out.getvalue(), media_type=XLSX,
                    headers={"Content-Disposition": 'attachment; filename="change-log.xlsx"'})
