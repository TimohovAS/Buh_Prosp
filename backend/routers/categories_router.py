"""Роутер справочника категорий доходов и расходов."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user_required, require_edit_access
from backend.database import get_db
from backend.models import TransactionCategory, User
from backend.schemas import (
    TransactionCategoryCreate,
    TransactionCategoryResponse,
    TransactionCategoryUpdate,
)

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[TransactionCategoryResponse])
async def list_categories(
    category_type: Optional[str] = Query(None),
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    query = select(TransactionCategory)
    if category_type:
        query = query.where(TransactionCategory.category_type == category_type)
    if not include_inactive:
        query = query.where(TransactionCategory.is_active.is_(True))
    query = query.order_by(
        TransactionCategory.sort_order,
        TransactionCategory.name_ru,
        TransactionCategory.name_sr,
    )
    result = await db.execute(query)
    return [TransactionCategoryResponse.model_validate(item) for item in result.scalars().all()]


@router.post("", response_model=TransactionCategoryResponse)
async def create_category(
    data: TransactionCategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    category = TransactionCategory(**data.model_dump())
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return TransactionCategoryResponse.model_validate(category)


@router.patch("/{category_id}", response_model=TransactionCategoryResponse)
async def update_category(
    category_id: int,
    data: TransactionCategoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    result = await db.execute(
        select(TransactionCategory).where(TransactionCategory.id == category_id)
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(404, "Категория не найдена")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(category, key, value)

    await db.commit()
    await db.refresh(category)
    return TransactionCategoryResponse.model_validate(category)
