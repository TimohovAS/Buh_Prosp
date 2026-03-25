"""Сервисные административные операции."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import require_admin
from backend.backup_service import (
    create_backup,
    get_backup_dir,
    get_backup_status,
    is_backup_supported,
    restore_backup,
)
from backend.config import get_settings
from backend.database import get_db
from backend.models import Enterprise
from backend.schemas import (
    ServiceBackupOperationResponse,
    ServiceBackupSettings,
    ServiceBackupSettingsUpdate,
    ServiceBackupStatusResponse,
    ServiceRestoreResponse,
)

router = APIRouter(prefix="/service", tags=["service"])


async def _get_or_create_enterprise(db: AsyncSession) -> Enterprise:
    result = await db.execute(select(Enterprise).limit(1))
    enterprise = result.scalar_one_or_none()
    if enterprise is None:
        enterprise = Enterprise(name=get_settings().app_name)
        db.add(enterprise)
        await db.flush()
    return enterprise


@router.get("/backups", response_model=ServiceBackupStatusResponse)
async def list_service_backups(
    current_user=Depends(require_admin),
):
    del current_user
    return await get_backup_status()


@router.put("/backups/settings", response_model=ServiceBackupSettings)
async def update_service_backup_settings(
    data: ServiceBackupSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    del current_user
    enterprise = await _get_or_create_enterprise(db)
    payload = data.model_dump(exclude_unset=True)
    field_map = {
        "backup_dir": "backup_dir",
        "auto_enabled": "backup_auto_enabled",
        "auto_interval_hours": "backup_auto_interval_hours",
        "auto_retention_count": "backup_auto_retention_count",
        "manual_retention_count": "backup_manual_retention_count",
        "pre_restore_retention_count": "backup_pre_restore_retention_count",
        "scheduler_check_minutes": "backup_scheduler_check_minutes",
    }
    for source_field, target_field in field_map.items():
        if source_field in payload:
            setattr(enterprise, target_field, payload[source_field])

    await db.commit()
    status = await get_backup_status()
    return status["settings"]


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
