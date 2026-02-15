"""Роутер планируемых (периодических) расходов."""
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.services import create_expense_reversal
from backend.models import PlannedExpense, PlannedExpensePayment, Expense, User
from backend.planned_expenses_service import next_payment_dates, payment_dates_in_range
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


@router.get("", response_model=list[PlannedExpenseResponse])
async def list_planned_expenses(
    is_active: Optional[bool] = Query(None),
    category: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Список планируемых расходов."""
    q = select(PlannedExpense).order_by(PlannedExpense.name)
    if is_active is not None:
        q = q.where(PlannedExpense.is_active == is_active)
    if category:
        q = q.where(PlannedExpense.category == category)
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
            select(PlannedExpensePayment.planned_expense_id, PlannedExpensePayment.due_date).where(
                PlannedExpensePayment.planned_expense_id.in_([pe.id for pe in items])
            )
        )
        paid_set = {(row[0], row[1]) for row in r_paid.fetchall()}

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
    desc = f"{pe.name}" + (f" ({pe.description})" if pe.description else "")
    if len(desc) > 500:
        desc = desc[:497] + "..."
    expense = Expense(
        date=paid_d,
        description=desc,
        amount=pe.amount,
        currency=pe.currency or "RSD",
        category=pe.category or "other",
        note=data.note,
        paid_date=paid_d,
        source="planned",
        created_by=current_user.id,
    )
    db.add(expense)
    await db.flush()
    pep = PlannedExpensePayment(
        planned_expense_id=pe.id,
        due_date=due_d,
        paid_date=paid_d,
        expense_id=expense.id,
        note=data.note,
    )
    db.add(pep)
    await db.flush()
    return {"ok": True, "expense_id": expense.id}


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
    expense_id = pep.expense_id
    if expense_id:
        r_exp = await db.execute(select(Expense).where(Expense.id == expense_id))
        exp = r_exp.scalar_one_or_none()
        if exp and getattr(exp, "status", "paid") != "reversed" and not getattr(exp, "reversed_expense_id", None):
            await create_expense_reversal(
                db, exp,
                reverse_date=getattr(exp, "paid_date", None) or exp.date,
                source="planned",
                created_by=current_user.id,
            )
    await db.delete(pep)
    await db.flush()
    return {"ok": True}


@router.post("", response_model=PlannedExpenseResponse)
async def create_planned_expense(
    data: PlannedExpenseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Добавить планируемый расход."""
    pe = PlannedExpense(
        name=data.name,
        description=data.description,
        amount=data.amount,
        currency=data.currency,
        category=data.category,
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
    await db.flush()
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
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(pe, k, v)
    await db.flush()
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
    return {"ok": True}
