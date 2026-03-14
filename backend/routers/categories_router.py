"""Роутер справочника категорий доходов и расходов."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user_required, require_edit_access
from backend.database import get_db
from backend.models import Project, TransactionCategory, User
from backend.schemas import (
    TransactionCategoryCreate,
    TransactionCategoryResponse,
    TransactionCategoryUpdate,
)

router = APIRouter(prefix="/categories", tags=["categories"])


async def _ensure_default_project_exists(db: AsyncSession, project_id: int | None) -> None:
    if project_id is None:
        return
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Проект не найден")
    if project.status == "archived":
        raise HTTPException(400, "Нельзя использовать архивный проект")


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
    await _ensure_default_project_exists(db, data.default_project_id)
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

    payload = data.model_dump(exclude_unset=True)
    if "default_project_id" in payload:
        await _ensure_default_project_exists(db, payload["default_project_id"])

    for key, value in payload.items():
        setattr(category, key, value)

    await db.commit()
    await db.refresh(category)
    return TransactionCategoryResponse.model_validate(category)
