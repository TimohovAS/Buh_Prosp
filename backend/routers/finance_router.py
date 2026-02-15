"""Роутер финансовых отчётов (accrual/cash)."""
from datetime import date
from typing import Optional, Literal
from fastapi import APIRouter, Depends, Query

from backend.database import get_db
from backend.models import User
from backend.auth import get_current_user_required
from backend.finance_service import get_finance_summary, get_accounts_receivable, get_cashflow, get_finance_by_project
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/finance", tags=["finance"])


@router.get("/summary")
async def finance_summary(
    from_: date = Query(..., alias="from", description="Начало периода"),
    to: date = Query(..., alias="to", description="Конец периода"),
    group_by: Literal["day", "month", "year"] = Query("month"),
    mode: Literal["accrual", "cash", "both"] = Query("both"),
    client_id: Optional[int] = Query(None),
    contract_id: Optional[int] = Query(None),
    project_id: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    is_tax_related: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Финансовый агрегатор: метрики accrual и cash по периодам."""
    filters = {}
    if client_id is not None:
        filters["client_id"] = client_id
    if contract_id is not None:
        filters["contract_id"] = contract_id
    if project_id is not None:
        filters["project_id"] = project_id
    if category is not None:
        filters["category"] = category
    if is_tax_related is not None:
        filters["is_tax_related"] = is_tax_related
    return await get_finance_summary(db, from_, to, group_by, mode, filters)


@router.get("/ar")
async def finance_ar(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Дебиторская задолженность: unpaid incomes (paid_date is null)."""
    return await get_accounts_receivable(db)


@router.get("/cashflow")
async def finance_cashflow(
    from_: date = Query(..., alias="from", description="Начало периода"),
    to: date = Query(..., alias="to", description="Конец периода"),
    group_by: Literal["day", "month", "year"] = Query("month"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Cash flow: opening + inflow - outflow = closing (cumulative)."""
    return await get_cashflow(db, from_, to, group_by)


@router.get("/by-project")
async def finance_by_project(
    from_: date = Query(..., alias="from", description="Начало периода"),
    to: date = Query(..., alias="to", description="Конец периода"),
    mode: Literal["accrual", "cash"] = Query("accrual"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Аналитика по проектам: revenue, expenses, profit."""
    return await get_finance_by_project(db, from_, to, mode)
