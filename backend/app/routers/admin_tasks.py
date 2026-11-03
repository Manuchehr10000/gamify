from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm.exc import StaleDataError

from app import changes, settings
from app.auth import require_role
from app.db import get_db
from app.models import Stage, Staff, Task
from app.routers.feed import StageOut, stage_out
from app.stages import advance, day
from app.task_file import ImportResult, export_xlsx, import_xlsx

# One dependency object: the router's check and the endpoints' acting admin are the same lookup
ADMIN = require_role("admin")
router = APIRouter(prefix="/api/admin", dependencies=[Depends(ADMIN)])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class Schedule(BaseModel):
    state: str
    current: int | None
    stages: list[StageOut]


def _schedule(db: DbSession) -> Schedule:
    d = day(db)
    return Schedule(state=d.state, current=d.current.number if d.current else None,
                    stages=[stage_out(s) for s in d.stages])


@router.get("/stages")
def stages(db: DbSession = Depends(get_db)) -> Schedule:
    return _schedule(db)


@router.post("/stages/advance")
def advance_stage(confirm: bool = False, admin: Staff = Depends(ADMIN), db: DbSession = Depends(get_db)) -> Schedule:
    """Ends the current stage now and starts the next. Without confirm it changes nothing and says what would."""
    # Locked, so a form save of a stage at the same moment waits and is then refused as stale, not failed
    db.scalars(select(Stage).where(Stage.active).with_for_update().execution_options(populate_existing=True)).all()
    d = day(db)
    before = {s.id: (s.starts_at, s.ends_at) for s in d.stages}
    if not advance(db):
        raise HTTPException(409, "no_next_stage")
    if not confirm:
        after = day(db)
        db.rollback()
        raise HTTPException(409, {"code": "confirm", "impact": [{
            "code": "stage_change", "from": d.current.number if d.current else None,
            "to": after.current.number if after.current else None}]})
    for s in d.stages:
        for name, old, new in (("starts_at", before[s.id][0], s.starts_at), ("ends_at", before[s.id][1], s.ends_at)):
            if old != new:
                changes.record(db, admin, "stages", s.id, changes.label(db, s), name, old, new)
    settings.bump(db)
    db.commit()
    return _schedule(db)


@router.post("/tasks/import")
async def import_tasks(file: UploadFile, admin: Staff = Depends(ADMIN), db: DbSession = Depends(get_db)) -> ImportResult:
    """Applies the file whole, or refuses it whole naming each bad row (the counts are then 0)."""
    return _upload(db, await file.read(), admin, apply=True)


@router.post("/tasks/import/preview")
async def preview_tasks(file: UploadFile, admin: Staff = Depends(ADMIN),
                        db: DbSession = Depends(get_db)) -> ImportResult:
    """What the file would add, change and hide, or its bad rows. Nothing changes."""
    return _upload(db, await file.read(), admin, apply=False)


def _upload(db: DbSession, raw: bytes, admin: Staff, apply: bool) -> ImportResult:
    logged = []

    def record(kind: str, item_id: int | None, item: str, field: str, old: object, new: object) -> None:
        # Written in the upload's transaction; the first change also moves the config version
        if not logged:
            settings.bump(db)
        logged.append(field)
        changes.record(db, admin, kind, item_id, item, field, old, new, source="excel")

    try:
        result = import_xlsx(db, raw, apply=apply, record=record)
    except StaleDataError:
        # A form save moved one of the file's rows first: the upload is refused whole, like a stale save
        db.rollback()
        raise HTTPException(409, {"code": "stale"}) from None
    if result.missing:
        raise HTTPException(400, {"code": "missing", "items": result.missing})
    return result


@router.get("/tasks/export")
def export_tasks(db: DbSession = Depends(get_db)) -> Response:
    return Response(export_xlsx(db), media_type=XLSX,
                    headers={"Content-Disposition": 'attachment; filename="tasks.xlsx"'})


class QrTask(BaseModel):
    code: str
    stage: int
    text: str
    qr_code: str


@router.get("/tasks/qr")
def qr_tasks(db: DbSession = Depends(get_db)) -> list[QrTask]:
    """Every QR task's code, to print and put up at the venue. The page turns each into <site>/q/<code>."""
    rows = db.execute(select(Task, Stage.number).join(Stage, Task.stage_id == Stage.id)
                      .where(Task.active, Task.method == "qr").order_by(Stage.number, Task.position))
    return [QrTask(code=t.code, stage=n, text=t.text, qr_code=t.qr_code) for t, n in rows]
