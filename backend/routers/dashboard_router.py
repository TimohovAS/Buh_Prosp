"""Роутер дашборда и отчётов."""
from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from backend.database import get_db
from backend.models import Income, Payment, Expense, PlannedExpense, PlannedExpensePayment, MonthlyObligation, PaymentType, User
from backend.schemas import DashboardStats, DashboardIncomeResponse, IncomeLimitStatus, UpcomingObligationItem, UpcomingPlannedItem
from backend.auth import get_current_user_required
from backend.services import get_income_total, get_income_total_12_months, get_income_limit_status
from backend.planned_expenses_service import planned_expenses_sum_until_including_overdue, payment_dates_in_range
from backend.payments_service import get_or_create_obligations
from backend.config import get_settings

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
settings = get_settings()


@router.get("", response_model=DashboardStats)
async def get_dashboard(
    year: int = Query(None, description="Год (по умолчанию текущий)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Сводные данные дашборда."""
    today = date.today()
    y = year or today.year

    year_income = await get_income_total(db, year=y)
    month_income = await get_income_total(db, year=y, month=today.month)
    limit_status = await get_income_limit_status(db, y)

    # Расходы за год и месяц
    r_yr = await db.execute(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.date >= date(y, 1, 1),
            Expense.date <= date(y, 12, 31),
        )
    )
    year_expenses = float(r_yr.scalar() or 0)
    import calendar
    last_day = calendar.monthrange(y, today.month)[1]
    r_mo = await db.execute(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.date >= date(y, today.month, 1),
            Expense.date <= date(y, today.month, last_day),
        )
    )
    month_expenses = float(r_mo.scalar() or 0)

    balance_month = month_income - month_expenses
    balance_year = year_income - year_expenses

    # Периодические расходы до конца месяца (включая просроченные неоплаченные)
    month_end = date(y, today.month, last_day)
    range_start = date(y, 1, 1)  # начало года — включает просроченные
    r_pe = await db.execute(select(PlannedExpense).where(PlannedExpense.is_active == True))
    planned_items = r_pe.scalars().all()
    paid_pairs = set()
    if planned_items:
        r_paid = await db.execute(
            select(PlannedExpensePayment.planned_expense_id, PlannedExpensePayment.due_date).where(
                PlannedExpensePayment.planned_expense_id.in_([p.id for p in planned_items])
            )
        )
        paid_pairs = {(row[0], row[1]) for row in r_paid.fetchall()}
    planned_expenses_until_month_end = planned_expenses_sum_until_including_overdue(
        planned_items, range_start, month_end, paid_pairs
    )

    # Обязательные платежи: создаём если нет, добавляем в сумму до конца месяца и собираем предупреждения
    await get_or_create_obligations(db, y)
    r_ob = await db.execute(
        select(MonthlyObligation).where(
            MonthlyObligation.year == y,
            MonthlyObligation.status.in_(["unpaid", "overdue"]),
        )
    )
    unpaid_ob = r_ob.scalars().all()
    pt_ids = list({o.payment_type_id for o in unpaid_ob})
    type_map = {}
    if pt_ids:
        r_pt = await db.execute(select(PaymentType).where(PaymentType.id.in_(pt_ids)))
        for t in r_pt.scalars().all():
            type_map[t.id] = t
    obligations_sum_until_month_end = sum(
        o.amount for o in unpaid_ob if o.deadline <= month_end
    )
    planned_expenses_until_month_end += obligations_sum_until_month_end
    # Показывать только просроченные или со сроком в ближайшие 14 дней
    APPROACHING_DAYS = 14
    upcoming_obligations = []
    for o in sorted(unpaid_ob, key=lambda x: x.deadline):
        days_until = (o.deadline - today).days
        if days_until > APPROACHING_DAYS:
            continue
        pt = type_map.get(o.payment_type_id)
        upcoming_obligations.append(UpcomingObligationItem(
            id=o.id,
            payment_type_name=(pt.name_sr if pt else "Плаћање"),
            amount=o.amount,
            deadline=o.deadline.isoformat(),
            status="overdue" if o.deadline < today else "upcoming",
            days_until=days_until,
        ))

    unpaid_payments_count = len(unpaid_ob)
    next_dl = next((o.deadline for o in unpaid_ob if o.deadline >= today), None) if unpaid_ob else None
    upcoming = next_dl.strftime("%d.%m.%Y") if next_dl else (
        f"15.{(today.month % 12) + 1:02d}.{today.year}" if today.day >= 15 else f"15.{today.month:02d}.{today.year}"
    )

    # Периодические расходы: просроченные и приближающиеся (14 дней)
    range_start_pe = today - timedelta(days=APPROACHING_DAYS)
    range_end_pe = today + timedelta(days=APPROACHING_DAYS)
    upcoming_planned = []
    for pe in planned_items:
        dates = payment_dates_in_range(pe, range_start_pe, range_end_pe, limit=12)
        for d in dates:
            if (pe.id, d) in paid_pairs:
                continue
            days_until = (d - today).days
            upcoming_planned.append(UpcomingPlannedItem(
                planned_expense_id=pe.id,
                name=pe.name,
                amount=pe.amount,
                currency=pe.currency or "RSD",
                due_date=d.isoformat(),
                status="overdue" if d < today else "upcoming",
                days_until=days_until,
            ))
    upcoming_planned.sort(key=lambda x: x.due_date)

    # Последние доходы (загружаем client для актуального имени)
    r2 = await db.execute(
        select(Income).options(selectinload(Income.client)).order_by(Income.issued_date.desc(), Income.id.desc()).limit(5)
    )
    items = r2.scalars().all()
    recent = []
    for i in items:
        d = DashboardIncomeResponse.model_validate(i).model_dump()
        if i.client:
            d["client_name"] = i.client.name
        recent.append(DashboardIncomeResponse(**d))

    return DashboardStats(
        year_income=year_income,
        month_income=month_income,
        year_expenses=year_expenses,
        month_expenses=month_expenses,
        balance_month=balance_month,
        balance_year=balance_year,
        planned_expenses_until_month_end=planned_expenses_until_month_end,
        income_limit_status=IncomeLimitStatus(
            year_income=limit_status["year_income"],
            limit_6m=limit_status["limit_6m"],
            limit_8m=limit_status["limit_8m"],
            percent_6m=limit_status["percent_6m"],
            percent_8m=limit_status["percent_8m"],
            warning_6m=limit_status["warning_6m"],
            warning_8m=limit_status["warning_8m"],
            exceeded_6m=limit_status["exceeded_6m"],
            exceeded_8m=limit_status["exceeded_8m"],
        ),
        unpaid_payments_count=unpaid_payments_count,
        upcoming_payment_date=upcoming,
        upcoming_unpaid_obligations=upcoming_obligations,
        upcoming_planned_expenses=upcoming_planned,
        recent_incomes=recent,
    )


@router.get("/income-limits", response_model=IncomeLimitStatus)
async def get_income_limits(
    year: int = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Статус лимитов дохода."""
    y = year or date.today().year
    status = await get_income_limit_status(db, y)
    return IncomeLimitStatus(**status)
