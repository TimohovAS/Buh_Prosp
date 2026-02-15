"""Роутер настроек предприятия."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import Enterprise, User
from backend.schemas import EnterpriseBase, EnterpriseUpdate, EnterpriseResponse
from backend.auth import get_current_user_required, require_admin

router = APIRouter(prefix="/enterprise", tags=["enterprise"])


@router.get("", response_model=EnterpriseResponse | None)
async def get_enterprise(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Получить данные предприятия."""
    r = await db.execute(select(Enterprise).limit(1))
    ent = r.scalar_one_or_none()
    if not ent:
        return None
    return EnterpriseResponse.model_validate(ent)


@router.put("", response_model=EnterpriseResponse)
async def update_enterprise(
    data: EnterpriseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Обновить данные предприятия."""
    r = await db.execute(select(Enterprise).limit(1))
    ent = r.scalar_one_or_none()
    if not ent:
        ent = Enterprise(**data.model_dump(exclude_unset=True))
        db.add(ent)
    else:
        for k, v in data.model_dump(exclude_unset=True).items():
            setattr(ent, k, v)
    await db.flush()
    await db.refresh(ent)
    return EnterpriseResponse.model_validate(ent)
