from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session as DbSession

from app import changes, settings
from app.auth import require_role
from app.db import get_db
from app.guest_list import ImportResult, export_csv, import_csv
from app.models import Staff

ADMIN = require_role("admin")
router = APIRouter(prefix="/api/admin/guests", dependencies=[Depends(ADMIN)])


@router.post("/import")
async def import_guests(file: UploadFile, admin: Staff = Depends(ADMIN), db: DbSession = Depends(get_db)) -> ImportResult:
    """Applies the list whole, or refuses it whole naming each bad row (the counts are then 0)."""
    return _upload(db, await file.read(), admin, apply=True)


@router.post("/import/preview")
async def preview_guests(file: UploadFile, admin: Staff = Depends(ADMIN),
                         db: DbSession = Depends(get_db)) -> ImportResult:
    """Whom the list would add and change, or its bad rows. Nothing changes."""
    return _upload(db, await file.read(), admin, apply=False)


def _upload(db: DbSession, raw: bytes, admin: Staff, apply: bool) -> ImportResult:
    def record(result: ImportResult) -> None:
        # The guests aren't settings: the log gets one row per upload, with what it added and changed
        changes.record(db, admin, "guests", None, "Список гостей", "_import", None,
                       f"добавлено {result.added}, изменено {result.changed}", source="excel")
        settings.bump(db)

    result = import_csv(db, raw, apply=apply, record=record)
    if result.missing_columns:
        raise HTTPException(400, {"code": "missing_columns", "columns": result.missing_columns})
    return result


@router.get("/export")
def export_guests(db: DbSession = Depends(get_db)) -> Response:
    return Response(export_csv(db), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="guests.csv"'})
