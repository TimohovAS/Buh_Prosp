"""Роутер справочника категорий (статьи ДДС)."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import TransactionCategory, User
from backend.schemas import (
    TransactionCategoryCreate,
    TransactionCategoryUpdate,
    TransactionCategoryResponse,
)
from backend.auth import get_current_user_required, require_edit_access

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[TransactionCategoryResponse])
async def list_categories(
    category_type: Optional[str] = Query(None),
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Список категорий (по умолчанию только активные)."""
    q = select(TransactionCategory).order_by(
        TransactionCategory.sort_order, TransactionCategory.name_ru
    )
    if category_type:
        q = q.where(TransactionCategory.category_type == category_type)
    if not include_inactive:
        q = q.where(TransactionCategory.is_active == True)
    result = await db.execute(q)
    return [TransactionCategoryResponse.model_validate(c) for c in result.scalars().all()]


@router.post("", response_model=TransactionCategoryResponse)
async def create_category(
    data: TransactionCategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Создать категорию."""
    cat = TransactionCategory(
        name_ru=data.name_ru,
        name_sr=data.name_sr,
        category_type=data.category_type,
        category_group=data.category_group,
        is_active=data.is_active,
        sort_order=data.sort_order,
    )
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return TransactionCategoryResponse.model_validate(cat)


@router.patch("/{category_id}", response_model=TransactionCategoryResponse)
async def update_category(
    category_id: int,
    data: TransactionCategoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Обновить категорию (включая деактивацию через is_active=false)."""
    r = await db.execute(
        select(TransactionCategory).where(TransactionCategory.id == category_id)
    )
    cat = r.scalar_one_or_none()
    if not cat:
        raise HTTPException(404, "Категория не найдена")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(cat, k, v)
    await db.commit()
    await db.refresh(cat)
    return TransactionCategoryResponse.model_validate(cat)
