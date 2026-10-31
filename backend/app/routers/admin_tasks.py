from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from app.auth import require_role
from app.db import get_db
from app.routers.feed import StageOut, stage_out
from app.stages import advance, day
from app.task_file import ImportResult, export_xlsx, import_xlsx

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_role("admin"))])

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
def advance_stage(db: DbSession = Depends(get_db)) -> Schedule:
    if not advance(db):
        raise HTTPException(409, "no_next_stage")
    return _schedule(db)


@router.post("/tasks/import")
async def import_tasks(file: UploadFile, db: DbSession = Depends(get_db)) -> ImportResult:
    result = import_xlsx(db, await file.read())
    if result.missing:
        raise HTTPException(400, {"code": "missing", "items": result.missing})
    return result


@router.get("/tasks/export")
def export_tasks(db: DbSession = Depends(get_db)) -> Response:
    return Response(export_xlsx(db), media_type=XLSX,
                    headers={"Content-Disposition": 'attachment; filename="tasks.xlsx"'})
