from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from backend.planned_expenses_service import (
    AUTO_WORKER_SALARY_NOTE,
    next_payment_dates,
    payment_dates_in_range,
    planned_expenses_sum_until_including_overdue,
    sync_worker_salary_plan,
)
from backend.models import PlannedExpense, Worker
from backend.routers.planned_expenses_router import get_upcoming_payments, list_planned_expenses
from sqlalchemy import func, select


def make_planned_expense(**overrides):
    values = {
        "id": 1,
        "is_active": True,
        "period": "once",
        "start_date": date(2026, 9, 18),
        "end_date": None,
        "payment_day": None,
        "payment_day_of_week": None,
        "amount": Decimal("12500.00"),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_one_time_planned_expense_has_exactly_one_due_date():
    expense = make_planned_expense()

    assert next_payment_dates(expense, date(2026, 9, 2)) == [date(2026, 9, 18)]
    assert payment_dates_in_range(expense, date(2026, 9, 1), date(2026, 9, 30)) == [date(2026, 9, 18)]
    assert payment_dates_in_range(expense, date(2026, 10, 1), date(2026, 10, 31)) == []


def test_one_time_planned_expense_is_removed_from_forecast_after_payment():
    expense = make_planned_expense()

    unpaid_total = planned_expenses_sum_until_including_overdue(
        [expense],
        date(2026, 1, 1),
        date(2026, 9, 30),
    )
    paid_total = planned_expenses_sum_until_including_overdue(
        [expense],
        date(2026, 1, 1),
        date(2026, 9, 30),
        {(expense.id, expense.start_date)},
    )

    assert unpaid_total == Decimal("12500.00")
    assert paid_total == Decimal("0.00")


def test_future_recurring_expense_can_generate_payment_dates():
    expense = make_planned_expense(
        period="monthly",
        start_date=date(2026, 10, 1),
        payment_day=5,
    )

    assert next_payment_dates(expense, date(2026, 9, 2), limit=2) == [date(2026, 10, 5), date(2026, 11, 5)]


async def test_worker_salary_plan_is_created_and_kept_in_sync(db_session):
    worker = Worker(
        name="Ana",
        worker_type="permanent",
        pay_scheme="monthly",
        monthly_rate=Decimal("84000.00"),
        is_active=True,
    )
    db_session.add(worker)
    await db_session.flush()

    plan = await sync_worker_salary_plan(db_session, worker, today=date(2026, 9, 2))

    assert plan is not None
    assert plan.worker_id == worker.id
    assert plan.amount == Decimal("84000.00")
    assert plan.period == "monthly"
    assert plan.start_date == date(2026, 9, 1)
    assert plan.payment_day == 5
    assert plan.note == AUTO_WORKER_SALARY_NOTE

    worker.monthly_rate = Decimal("91000.00")
    updated = await sync_worker_salary_plan(db_session, worker, today=date(2026, 9, 2))
    plan_count = await db_session.scalar(
        select(func.count(PlannedExpense.id)).where(PlannedExpense.worker_id == worker.id)
    )

    assert updated is plan
    assert updated.amount == Decimal("91000.00")
    assert plan_count == 1

    worker.is_active = False
    assert await sync_worker_salary_plan(db_session, worker, today=date(2026, 9, 2)) is None
    assert plan.is_active is False


async def test_per_day_worker_does_not_get_fixed_salary_plan(db_session):
    worker = Worker(
        name="Boris",
        worker_type="temporary",
        pay_scheme="per_day",
        regular_day_rate=Decimal("5000.00"),
        is_active=True,
    )
    db_session.add(worker)
    await db_session.flush()

    assert await sync_worker_salary_plan(db_session, worker, today=date(2026, 9, 2)) is None


async def test_manual_planned_expense_list_hides_worker_salary_plans(db_session):
    worker = Worker(
        name="Ana",
        worker_type="permanent",
        pay_scheme="monthly",
        monthly_rate=Decimal("84000.00"),
        is_active=True,
    )
    manual_plan = PlannedExpense(
        name="Equipment",
        amount=Decimal("12000.00"),
        currency="RSD",
        period="once",
        start_date=date(2026, 9, 15),
        is_active=True,
    )
    db_session.add_all([worker, manual_plan])
    await db_session.flush()
    salary_plan = await sync_worker_salary_plan(db_session, worker, today=date(2026, 9, 2))

    items = await list_planned_expenses(
        is_active=None,
        category=None,
        category_id=None,
        db=db_session,
        current_user=SimpleNamespace(id=1),
    )

    assert salary_plan is not None
    assert [item.id for item in items] == [manual_plan.id]


async def test_upcoming_payments_keeps_generated_worker_salary(db_session):
    today = date.today()
    worker = Worker(
        name="Ana",
        worker_type="permanent",
        pay_scheme="monthly",
        monthly_rate=Decimal("84000.00"),
        is_active=True,
    )
    db_session.add(worker)
    await db_session.flush()
    salary_plan = await sync_worker_salary_plan(db_session, worker, today=today)

    items = await get_upcoming_payments(days=60, db=db_session, current_user=SimpleNamespace(id=1))

    assert salary_plan is not None
    salary_items = [item for item in items if item.worker_id == worker.id]
    assert salary_items
    assert all(item.amount == Decimal("84000.00") for item in salary_items)
