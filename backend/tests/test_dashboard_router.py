from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from backend.models import PlannedExpense
from backend.routers.dashboard_router import get_dashboard


async def test_dashboard_includes_planned_receipt_but_not_ordinary_planned_expense(
    db_session,
    make_expense,
):
    today = date.today()
    expense_date = date(today.year, today.month, 1)
    await make_expense(
        db_session,
        amount=Decimal("1487.08"),
        status="planned",
        expense_date=expense_date,
        source="receipt",
    )
    await make_expense(
        db_session,
        amount=Decimal("500.00"),
        status="planned",
        expense_date=expense_date,
        source="manual",
    )

    dashboard = await get_dashboard(
        year=today.year,
        db=db_session,
        current_user=SimpleNamespace(id=1),
    )

    assert dashboard.year_expenses == Decimal("1487.08")
    assert dashboard.month_expenses == Decimal("1487.08")
    assert dashboard.financial_result_all_time == Decimal("-1487.08")


async def test_dashboard_exposes_planned_expenses_as_separate_reference_total(db_session):
    today = date.today()
    planned = PlannedExpense(
        name="Equipment purchase",
        amount=Decimal("24500.00"),
        currency="RSD",
        period="once",
        start_date=today,
        reminder_days=3,
        is_active=True,
    )
    db_session.add(planned)
    await db_session.flush()

    dashboard = await get_dashboard(
        year=today.year,
        db=db_session,
        current_user=SimpleNamespace(id=1),
    )

    assert dashboard.planned_expenses_only_until_month_end == Decimal("24500.00")
    assert dashboard.planned_expenses_until_month_end >= dashboard.planned_expenses_only_until_month_end
