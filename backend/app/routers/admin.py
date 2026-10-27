from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session as DbSession

from app.auth import require_role
from app.db import get_db
from app.guest_list import ImportResult, export_csv, import_csv

router = APIRouter(prefix="/api/admin/guests", dependencies=[Depends(require_role("admin"))])


@router.post("/import")
async def import_guests(file: UploadFile, db: DbSession = Depends(get_db)) -> ImportResult:
    result = import_csv(db, await file.read())
    if result.missing_columns:
        raise HTTPException(400, {"code": "missing_columns", "columns": result.missing_columns})
    return result


@router.get("/export")
def export_guests(db: DbSession = Depends(get_db)) -> Response:
    return Response(export_csv(db), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="guests.csv"'})
