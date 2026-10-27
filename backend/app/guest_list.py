"""TAG's guest list as CSV: read an upload (UTF-8 or Excel's Windows-1251), write it back with links."""
import csv
import io
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.guests import clean_phone, link, new_code
from app.models import Guest

# Column → header names we accept (matched lowercase). The first one is what the export writes.
COLUMNS = {
    "reg_id": ["ID регистрации", "id", "reg_id", "registration id", "номер регистрации", "регистрационный номер"],
    "last_name": ["Фамилия", "last name", "last_name", "surname"],
    "first_name": ["Имя", "first name", "first_name", "name"],
    "phone": ["Телефон", "phone", "мобильный телефон", "моб. телефон"],
    "company": ["Компания", "company", "организация"],
}
FULL_NAME = ["фио", "full name"]
LINK_HEADER = "Ссылка"


@dataclass
class ImportResult:
    added: int = 0
    updated: int = 0
    failed: list[dict] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1251")


def _reader(text: str) -> csv.reader:
    first = text.split("\n", 1)[0]
    delimiter = max(";,\t", key=first.count)
    return csv.reader(io.StringIO(text), delimiter=delimiter)


def _columns(header: list[str]) -> dict[str, int]:
    names = [h.strip().lower() for h in header]
    found = {}
    for col, aliases in COLUMNS.items():
        for i, n in enumerate(names):
            if n in (a.lower() for a in aliases):
                found[col] = i
                break
    for i, n in enumerate(names):
        if n in FULL_NAME:
            found["full_name"] = i
    return found


def import_csv(db: DbSession, raw: bytes) -> ImportResult:
    result = ImportResult()
    rows = list(_reader(_decode(raw)))
    if not rows:
        result.missing_columns = ["reg_id", "first_name"]
        return result
    cols = _columns(rows[0])
    result.missing_columns = [c for c in ("reg_id", "first_name") if c not in cols and not (
        c == "first_name" and "full_name" in cols)]
    if result.missing_columns:
        return result

    def cell(row: list[str], col: str) -> str:
        i = cols.get(col)
        return row[i].strip() if i is not None and i < len(row) else ""

    existing = {g.reg_id: g for g in db.scalars(select(Guest).where(Guest.reg_id.is_not(None)))}
    seen: set[str] = set()
    for n, row in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in row):
            continue
        reg_id = cell(row, "reg_id")
        first, last = cell(row, "first_name"), cell(row, "last_name")
        if not first and "full_name" in cols:
            # ФИО is written surname first: "Иванов Иван Иванович"
            parts = cell(row, "full_name").split()
            last, first = (parts[0], parts[1]) if len(parts) > 1 else ("", parts[0] if parts else "")
        if not reg_id:
            result.failed.append({"row": n, "reason": "no_reg_id"})
            continue
        if not first:
            result.failed.append({"row": n, "reason": "no_first_name"})
            continue
        if reg_id in seen:
            result.failed.append({"row": n, "reason": "duplicate_reg_id"})
            continue
        seen.add(reg_id)
        values = {"first_name": first, "last_name": last, "phone": clean_phone(cell(row, "phone")),
                  "company": cell(row, "company")}
        guest = existing.get(reg_id)
        if guest:
            # Re-upload: details may change, the link never does
            for k, v in values.items():
                setattr(guest, k, v)
            result.updated += 1
        else:
            db.add(Guest(reg_id=reg_id, code=new_code(db), **values))
            db.flush()
            result.added += 1
    db.commit()
    return result


def export_csv(db: DbSession) -> str:
    out = io.StringIO()
    # Semicolons and a BOM so Excel opens Cyrillic correctly
    w = csv.writer(out, delimiter=";")
    w.writerow([COLUMNS[c][0] for c in COLUMNS] + [LINK_HEADER])
    for g in db.scalars(select(Guest).order_by(Guest.id)):
        w.writerow([g.reg_id or "", g.last_name, g.first_name, g.phone, g.company, link(g)])
    return "﻿" + out.getvalue()
