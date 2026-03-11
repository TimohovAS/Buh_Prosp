"""Dashboard summary endpoints."""

import calendar
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.auth import get_current_user_required
from backend.cash_service import CASH_TRANSFER_SOURCE
from backend.config import get_settings
from backend.database import get_db
from backend.models import BankTransaction, Expense, Income, MonthlyObligation, PaymentType, PlannedExpense, PlannedExpensePayment, User
from backend.payments_service import get_or_create_obligations
from backend.planned_expenses_service import payment_dates_in_range, planned_expenses_sum_until_including_overdue
from backend.schemas import DashboardIncomeResponse, DashboardStats, IncomeLimitStatus, UpcomingObligationItem, UpcomingPlannedItem
from backend.services import get_income_limit_status, get_income_total

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
settings = get_settings()


@router.get("", response_model=DashboardStats)
async def get_dashboard(
    year: int = Query(None, description="Year, defaults to current year"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Return dashboard summary data."""
    today = date.today()
    selected_year = year or today.year

    year_income = await get_income_total(db, year=selected_year)
    month_income = await get_income_total(db, year=selected_year, month=today.month)
    income_all_time = await get_income_total(db)
    limit_status = await get_income_limit_status(db, selected_year)

    year_expenses_result = await db.execute(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.source != CASH_TRANSFER_SOURCE,
            Expense.status != "planned",
            Expense.date >= date(selected_year, 1, 1),
            Expense.date <= date(selected_year, 12, 31),
        )
    )
    year_expenses = float(year_expenses_result.scalar() or 0)

    last_day = calendar.monthrange(selected_year, today.month)[1]
    month_expenses_result = await db.execute(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.source != CASH_TRANSFER_SOURCE,
            Expense.status != "planned",
            Expense.date >= date(selected_year, today.month, 1),
            Expense.date <= date(selected_year, today.month, last_day),
        )
    )
    month_expenses = float(month_expenses_result.scalar() or 0)

    all_time_expenses_result = await db.execute(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.source != CASH_TRANSFER_SOURCE,
            Expense.status != "planned",
        )
    )
    all_time_expenses = float(all_time_expenses_result.scalar() or 0)

    cash_in_all_time_result = await db.execute(
        select(func.coalesce(func.sum(BankTransaction.amount), 0)).where(
            BankTransaction.direction == "in",
        )
    )
    cash_in_all_time = float(cash_in_all_time_result.scalar() or 0)

    cash_out_all_time_result = await db.execute(
        select(func.coalesce(func.sum(BankTransaction.amount), 0)).where(
            BankTransaction.direction == "out",
        )
    )
    cash_out_all_time = float(cash_out_all_time_result.scalar() or 0)

    balance_month = month_income - month_expenses
    balance_year = year_income - year_expenses
    financial_result_all_time = income_all_time - all_time_expenses
    balance_all_time = cash_in_all_time - cash_out_all_time

    month_end = date(selected_year, today.month, last_day)
    range_start = date(selected_year, 1, 1)
    planned_result = await db.execute(select(PlannedExpense).where(PlannedExpense.is_active == True))
    planned_items = planned_result.scalars().all()

    paid_pairs = set()
    if planned_items:
        paid_result = await db.execute(
            select(PlannedExpensePayment.planned_expense_id, PlannedExpensePayment.due_date).where(
                PlannedExpensePayment.planned_expense_id.in_([item.id for item in planned_items])
            )
        )
        paid_pairs = {(row[0], row[1]) for row in paid_result.fetchall()}

    planned_expenses_until_month_end = planned_expenses_sum_until_including_overdue(
        planned_items,
        range_start,
        month_end,
        paid_pairs,
    )

    await get_or_create_obligations(db, selected_year)
    obligations_result = await db.execute(
        select(MonthlyObligation).where(
            MonthlyObligation.year == selected_year,
            MonthlyObligation.status.in_(["unpaid", "overdue"]),
        )
    )
    unpaid_obligations = obligations_result.scalars().all()

    payment_type_ids = list({item.payment_type_id for item in unpaid_obligations})
    payment_type_map = {}
    if payment_type_ids:
        payment_types_result = await db.execute(select(PaymentType).where(PaymentType.id.in_(payment_type_ids)))
        for payment_type in payment_types_result.scalars().all():
            payment_type_map[payment_type.id] = payment_type

    obligations_sum_until_month_end = sum(
        item.amount for item in unpaid_obligations if item.deadline <= month_end
    )
    planned_expenses_until_month_end += obligations_sum_until_month_end

    approaching_days = 14
    upcoming_obligations = []
    for obligation in sorted(unpaid_obligations, key=lambda item: item.deadline):
        days_until = (obligation.deadline - today).days
        if days_until > approaching_days:
            continue
        payment_type = payment_type_map.get(obligation.payment_type_id)
        upcoming_obligations.append(
            UpcomingObligationItem(
                id=obligation.id,
                payment_type_name=payment_type.name_sr if payment_type else "Payment",
                amount=obligation.amount,
                deadline=obligation.deadline.isoformat(),
                status="overdue" if obligation.deadline < today else "upcoming",
                days_until=days_until,
            )
        )

    unpaid_payments_count = len(unpaid_obligations)
    next_deadline = next((item.deadline for item in unpaid_obligations if item.deadline >= today), None) if unpaid_obligations else None
    upcoming_payment_date = next_deadline.strftime("%d.%m.%Y") if next_deadline else (
        f"15.{(today.month % 12) + 1:02d}.{today.year}" if today.day >= 15 else f"15.{today.month:02d}.{today.year}"
    )

    range_start_planned = today - timedelta(days=approaching_days)
    range_end_planned = today + timedelta(days=approaching_days)
    upcoming_planned = []
    for planned_expense in planned_items:
        due_dates = payment_dates_in_range(planned_expense, range_start_planned, range_end_planned, limit=12)
        for due_date in due_dates:
            if (planned_expense.id, due_date) in paid_pairs:
                continue
            days_until = (due_date - today).days
            upcoming_planned.append(
                UpcomingPlannedItem(
                    planned_expense_id=planned_expense.id,
                    name=planned_expense.name,
                    amount=planned_expense.amount,
                    currency=planned_expense.currency or "RSD",
                    due_date=due_date.isoformat(),
                    status="overdue" if due_date < today else "upcoming",
                    days_until=days_until,
                )
            )
    upcoming_planned.sort(key=lambda item: item.due_date)

    recent_result = await db.execute(
        select(Income)
        .options(selectinload(Income.client))
        .order_by(Income.issued_date.desc(), Income.id.desc())
        .limit(5)
    )
    recent_items = recent_result.scalars().all()
    recent_incomes = []
    for income in recent_items:
        payload = DashboardIncomeResponse.model_validate(income).model_dump()
        if income.client:
            payload["client_name"] = income.client.name
        recent_incomes.append(DashboardIncomeResponse(**payload))

    return DashboardStats(
        year_income=year_income,
        month_income=month_income,
        year_expenses=year_expenses,
        month_expenses=month_expenses,
        balance_month=balance_month,
        balance_year=balance_year,
        balance_all_time=balance_all_time,
        financial_result_all_time=financial_result_all_time,
        planned_expenses_until_month_end=planned_expenses_until_month_end,
        income_limit_status=IncomeLimitStatus(
            year_income=limit_status["year_income"],
            income_12m=limit_status["income_12m"],
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
        upcoming_payment_date=upcoming_payment_date,
        upcoming_unpaid_obligations=upcoming_obligations,
        upcoming_planned_expenses=upcoming_planned,
        recent_incomes=recent_incomes,
    )


@router.get("/income-limits", response_model=IncomeLimitStatus)
async def get_income_limits(
    year: int = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Return income limit status."""
    selected_year = year or date.today().year
    status = await get_income_limit_status(db, selected_year)
    return IncomeLimitStatus(**status)
