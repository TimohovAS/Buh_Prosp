from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user_required, require_admin, require_edit_access
from backend.database import get_db
from backend.efaktura_service import (
    get_efaktura_enterprise,
    import_efaktura_documents,
    sync_efaktura_documents,
)
from backend.models import EfakturaImportRecord, Enterprise, User
from backend.schemas import (
    EfakturaImportHistoryItem,
    EfakturaImportResult,
    EfakturaSettingsResponse,
    EfakturaSettingsUpdate,
    EfakturaSyncResponse,
)

router = APIRouter(prefix="/efaktura", tags=["efaktura"])


def _enterprise_to_settings(enterprise: Enterprise | None) -> EfakturaSettingsResponse:
    if enterprise is None:
        return EfakturaSettingsResponse()
    return EfakturaSettingsResponse(
        efaktura_enabled=bool(enterprise.efaktura_enabled),
        efaktura_api_base_url=enterprise.efaktura_api_base_url,
        efaktura_api_key=enterprise.efaktura_api_key,
        efaktura_api_key_header=enterprise.efaktura_api_key_header or "ApiKey",
        efaktura_api_key_prefix=enterprise.efaktura_api_key_prefix or "",
        efaktura_sync_incoming=bool(enterprise.efaktura_sync_incoming),
        efaktura_sync_outgoing=bool(enterprise.efaktura_sync_outgoing),
        efaktura_sync_lookback_days=int(enterprise.efaktura_sync_lookback_days or 30),
        efaktura_incoming_list_path=enterprise.efaktura_incoming_list_path,
        efaktura_incoming_document_path=enterprise.efaktura_incoming_document_path,
        efaktura_outgoing_list_path=enterprise.efaktura_outgoing_list_path,
        efaktura_outgoing_document_path=enterprise.efaktura_outgoing_document_path,
    )


@router.get("/settings", response_model=EfakturaSettingsResponse)
async def get_efaktura_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    enterprise = await get_efaktura_enterprise(db)
    return _enterprise_to_settings(enterprise)


@router.put("/settings", response_model=EfakturaSettingsResponse)
async def update_efaktura_settings(
    data: EfakturaSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await db.execute(select(Enterprise).order_by(Enterprise.id.asc()).limit(1))
    enterprise = result.scalar_one_or_none()
    payload = data.model_dump()
    if enterprise is None:
        enterprise = Enterprise(name="ProspEl", **payload)
        db.add(enterprise)
    else:
        for key, value in payload.items():
            setattr(enterprise, key, value)
    await db.commit()
    await db.refresh(enterprise)
    return _enterprise_to_settings(enterprise)


@router.post("/import-xml", response_model=EfakturaImportResult)
async def import_efaktura_xml(
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    if not files:
        raise HTTPException(400, "No XML files selected")
    documents = []
    for upload in files:
        documents.append({
            "file_name": upload.filename or "unknown.xml",
            "content": await upload.read(),
        })
    return await import_efaktura_documents(db, user_id=current_user.id, documents=documents, source="xml")


@router.post("/sync", response_model=EfakturaSyncResponse)
async def sync_efaktura(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    try:
        return await sync_efaktura_documents(db, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/history", response_model=list[EfakturaImportHistoryItem])
async def get_efaktura_history(
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(EfakturaImportRecord)
        .order_by(EfakturaImportRecord.created_at.desc(), EfakturaImportRecord.id.desc())
        .limit(limit)
    )
    return [EfakturaImportHistoryItem.model_validate(item) for item in result.scalars().all()]
