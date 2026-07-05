"""Роутер планируемых (периодических) расходов."""

from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.db_utils import get_category_or_none, get_unassigned_project_id
from backend.models import PlannedExpense, PlannedExpensePayment, User, Worker
from backend.planned_expenses_service import payment_dates_in_range
from backend.schemas import (
    PlannedExpenseCreate,
    PlannedExpenseUpdate,
    PlannedExpenseResponse,
    UpcomingPaymentItem,
    PlannedExpenseMarkPaid,
    PlannedExpenseUnmarkPaid,
)
from backend.auth import get_current_user_required, require_edit_access

router = APIRouter(prefix="/planned-expenses", tags=["planned-expenses"])


async def _resolve_category_project_id(db: AsyncSession, category_id: int | None, project_id: int | None) -> int | None:
    category = await get_category_or_none(db, category_id)
    if category and category.default_project_id:
        return category.default_project_id
    return project_id


async def _validate_worker_id(db: AsyncSession, worker_id: int | None) -> int | None:
    if worker_id is None:
        return None
    result = await db.execute(select(Worker.id).where(Worker.id == worker_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(404, "Worker not found")
    return worker_id


@router.get("", response_model=list[PlannedExpenseResponse])
async def list_planned_expenses(
    is_active: Optional[bool] = Query(None),
    category: Optional[str] = Query(None),
    category_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Список планируемых расходов."""
    q = select(PlannedExpense).order_by(PlannedExpense.name)
    if is_active is not None:
        q = q.where(PlannedExpense.is_active == is_active)
    if category:
        q = q.where(PlannedExpense.category == category)
    if category_id:
        q = q.where(PlannedExpense.category_id == category_id)
    result = await db.execute(q)
    items = result.scalars().all()
    return [PlannedExpenseResponse.model_validate(i) for i in items]


@router.get("/upcoming", response_model=list[UpcomingPaymentItem])
async def get_upcoming_payments(
    days: int = Query(60, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Предстоящие платежи: просроченные + в ближайшие N дней. Неоплаченные по дате, оплаченные в конце."""
    today = date.today()
    range_start = today - timedelta(days=days)
    range_end = today + timedelta(days=days)
    r = await db.execute(select(PlannedExpense).where(PlannedExpense.is_active == True))
    items = r.scalars().all()
    paid_set = set()
    if items:
        r_paid = await db.execute(
            select(
                PlannedExpensePayment.planned_expense_id,
                PlannedExpensePayment.due_date,
                PlannedExpensePayment.worker_payout_id,
            ).where(PlannedExpensePayment.planned_expense_id.in_([pe.id for pe in items]))
        )
        paid_set = {(row[0], row[1]): row[2] for row in r_paid.fetchall()}

    unpaid = []
    paid = []
    for pe in items:
        dates = payment_dates_in_range(pe, range_start, range_end, limit=24)
        for d in dates:
            item = UpcomingPaymentItem(
                planned_expense_id=pe.id,
                name=pe.name,
                amount=pe.amount,
                currency=pe.currency,
                due_date=d.isoformat(),
                reminder_days=pe.reminder_days or 0,
                is_paid=(pe.id, d) in paid_set,
                worker_id=pe.worker_id,
                worker_payout_id=paid_set.get((pe.id, d)),
            )
            if item.is_paid:
                paid.append(item)
            else:
                unpaid.append(item)
    unpaid.sort(key=lambda x: x.due_date)
    paid.sort(key=lambda x: x.due_date)
    return unpaid + paid


@router.post("/mark-paid")
async def mark_planned_expense_paid(
    data: PlannedExpenseMarkPaid,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Отметить платёж планируемого расхода как оплаченный и создать запись в расходах."""
    r = await db.execute(select(PlannedExpense).where(PlannedExpense.id == data.planned_expense_id))
    pe = r.scalar_one_or_none()
    if not pe:
        raise HTTPException(404, "Планируемый расход не найден")
    due_d = data.due_date if hasattr(data.due_date, "year") else date.fromisoformat(str(data.due_date))
    paid_d = data.paid_date if hasattr(data.paid_date, "year") else date.fromisoformat(str(data.paid_date))
    r_exist = await db.execute(
        select(PlannedExpensePayment).where(
            PlannedExpensePayment.planned_expense_id == pe.id,
            PlannedExpensePayment.due_date == due_d,
        )
    )
    if r_exist.scalar_one_or_none():
        raise HTTPException(400, "Этот платёж уже отмечен как оплаченный")
    pep = PlannedExpensePayment(
        planned_expense_id=pe.id,
        due_date=due_d,
        paid_date=paid_d,
        note=data.note,
    )
    db.add(pep)
    await db.commit()
    return {"ok": True}


@router.post("/mark-unpaid")
async def mark_planned_expense_unpaid(
    data: PlannedExpenseUnmarkPaid,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Отменить отметку об оплате: сторно расхода, удаление PlannedExpensePayment."""
    due_d = data.due_date if hasattr(data.due_date, "year") else date.fromisoformat(str(data.due_date))
    r = await db.execute(
        select(PlannedExpensePayment).where(
            PlannedExpensePayment.planned_expense_id == data.planned_expense_id,
            PlannedExpensePayment.due_date == due_d,
        )
    )
    pep = r.scalar_one_or_none()
    if not pep:
        raise HTTPException(404, "Оплата не найдена")
    await db.delete(pep)
    await db.commit()
    return {"ok": True}


@router.post("", response_model=PlannedExpenseResponse)
async def create_planned_expense(
    data: PlannedExpenseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Добавить планируемый расход."""
    project_id = await _resolve_category_project_id(
        db,
        data.category_id if hasattr(data, "category_id") else None,
        data.project_id if hasattr(data, "project_id") else None,
    )
    if not project_id:
        project_id = await get_unassigned_project_id(db)
    worker_id = await _validate_worker_id(db, data.worker_id)
    pe = PlannedExpense(
        name=data.name,
        description=data.description,
        amount=data.amount,
        currency=data.currency,
        category=data.category,
        category_id=data.category_id if hasattr(data, "category_id") else None,
        project_id=project_id,
        worker_id=worker_id,
        period=data.period,
        payment_day=data.payment_day,
        payment_day_of_week=data.payment_day_of_week,
        start_date=data.start_date,
        end_date=data.end_date,
        reminder_days=data.reminder_days,
        is_active=data.is_active,
        note=data.note,
    )
    db.add(pe)
    await db.commit()
    await db.refresh(pe)
    return PlannedExpenseResponse.model_validate(pe)


@router.get("/{expense_id}", response_model=PlannedExpenseResponse)
async def get_planned_expense(
    expense_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Получить планируемый расход."""
    r = await db.execute(select(PlannedExpense).where(PlannedExpense.id == expense_id))
    pe = r.scalar_one_or_none()
    if not pe:
        raise HTTPException(404, "Планируемый расход не найден")
    return PlannedExpenseResponse.model_validate(pe)


@router.patch("/{expense_id}", response_model=PlannedExpenseResponse)
async def update_planned_expense(
    expense_id: int,
    data: PlannedExpenseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Обновить планируемый расход."""
    r = await db.execute(select(PlannedExpense).where(PlannedExpense.id == expense_id))
    pe = r.scalar_one_or_none()
    if not pe:
        raise HTTPException(404, "Планируемый расход не найден")
    dump = data.model_dump(exclude_unset=True)
    desired_project_id = await _resolve_category_project_id(
        db,
        dump.get("category_id", pe.category_id),
        dump.get("project_id", pe.project_id),
    )
    if desired_project_id is None:
        desired_project_id = await get_unassigned_project_id(db)
    dump["project_id"] = desired_project_id
    if "project_id" in dump and not dump["project_id"]:
        dump["project_id"] = await get_unassigned_project_id(db)
    if "worker_id" in dump:
        dump["worker_id"] = await _validate_worker_id(db, dump.get("worker_id"))
    for k, v in dump.items():
        setattr(pe, k, v)
    await db.commit()
    await db.refresh(pe)
    return PlannedExpenseResponse.model_validate(pe)


@router.delete("/{expense_id}")
async def delete_planned_expense(
    expense_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Удалить планируемый расход."""
    r = await db.execute(select(PlannedExpense).where(PlannedExpense.id == expense_id))
    pe = r.scalar_one_or_none()
    if not pe:
        raise HTTPException(404, "Планируемый расход не найден")
    await db.delete(pe)
    await db.commit()
    return {"ok": True}
