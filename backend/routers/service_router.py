"""Сервисные административные операции."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from backend.auth import require_admin
from backend.backup_service import (
    create_backup,
    get_backup_dir,
    get_backup_status,
    is_backup_supported,
    restore_backup,
)
from backend.schemas import (
    ServiceBackupOperationResponse,
    ServiceBackupStatusResponse,
    ServiceRestoreResponse,
)

router = APIRouter(prefix="/service", tags=["service"])


@router.get("/backups", response_model=ServiceBackupStatusResponse)
async def list_service_backups(
    current_user=Depends(require_admin),
):
    del current_user
    return await get_backup_status()


@router.post("/backups", response_model=ServiceBackupOperationResponse)
async def create_service_backup(
    current_user=Depends(require_admin),
):
    del current_user
    if not is_backup_supported():
        raise HTTPException(status_code=400, detail="Backup доступен только для SQLite")
    backup = await create_backup("manual")
    return {
        "backup": backup,
        "message": "Backup создан",
    }


@router.post("/backups/{backup_name}/restore", response_model=ServiceRestoreResponse)
async def restore_service_backup(
    backup_name: str,
    current_user=Depends(require_admin),
):
    del current_user
    if not is_backup_supported():
        raise HTTPException(status_code=400, detail="Восстановление доступно только для SQLite")
    try:
        result = await restore_backup(backup_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        **result,
        "message": "База восстановлена из backup",
    }


@router.get("/backups/{backup_name}/download")
async def download_service_backup(
    backup_name: str,
    current_user=Depends(require_admin),
):
    del current_user
    backup_path = (get_backup_dir() / backup_name).resolve()
    backup_dir = get_backup_dir().resolve()
    if backup_path.parent != backup_dir or not backup_path.exists() or not backup_path.is_file():
        raise HTTPException(status_code=404, detail="Backup не найден")

    return FileResponse(
        path=backup_path,
        filename=backup_path.name,
        media_type="application/zip",
    )
