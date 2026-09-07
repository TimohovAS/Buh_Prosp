from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException

from backend.finance_service import get_cashflow
from backend.models import BankTransactionIncomeAllocation, Enterprise
from backend.routers.finance_router import finance_cashflow


async def test_month_year_and_day_balances_use_same_movements(db_session, make_bank_tx, make_income, make_expense):
    jan, feb = date(2025, 1, 15), date(2025, 2, 1)
    income = await make_income(db_session, amount="1000.13", issued_date=jan)
    payment = await make_bank_tx(db_session, amount="1000.13", status="matched", tx_date=jan)
    payment.matched_type, payment.matched_id = "income", income.id
    # Partial allocations, cash payments, loan principal and tax payments all
    # affect the opening exactly as they affect the preceding report's closing.
    allocated = await make_bank_tx(db_session, amount="200.11", status="matched", tx_date=jan, bank_reference="ALLOC")
    allocated.matched_type = "income_allocation"
    db_session.add(
        BankTransactionIncomeAllocation(bank_transaction_id=allocated.id, income_id=income.id, amount=Decimal("200.11"))
    )
    await make_expense(db_session, amount="125.17", status="paid", source="cash", expense_date=jan)
    await make_expense(db_session, amount="50.03", status="paid", source="cash", expense_date=feb)
    loan_in = await make_bank_tx(db_session, amount="300.00", status="matched", tx_date=jan, bank_reference="LOAN-IN")
    loan_in.matched_type = "loan_movement"
    loan_out = await make_bank_tx(
        db_session, amount="-40.01", direction="out", status="matched", tx_date=feb, bank_reference="LOAN-OUT"
    )
    loan_out.matched_type = "loan_movement"
    tax = await make_bank_tx(
        db_session, amount="-20.04", direction="out", status="matched", tx_date=jan, bank_reference="TAX"
    )
    tax.matched_type = "obligation"
    # Neither unmatched/ignored bank movements nor withdrawals to cash should
    # create a different balance just because the range starts later.
    await make_bank_tx(db_session, amount="999.00", tx_date=jan, bank_reference="UNMATCHED")
    await make_bank_tx(db_session, amount="999.00", status="ignored", tx_date=jan, bank_reference="IGNORED")
    transfer = await make_expense(db_session, amount="500", status="paid", source="cash_transfer", expense_date=jan)
    withdrawal = await make_bank_tx(
        db_session, amount="-500", direction="out", status="matched", tx_date=jan, bank_reference="WITHDRAWAL"
    )
    withdrawal.matched_type, withdrawal.matched_id = "expense", transfer.id
    await db_session.flush()

    year = await get_cashflow(db_session, date(2025, 1, 1), date(2025, 12, 31), "month")
    month = await get_cashflow(db_session, feb, date(2025, 2, 28), "day")
    day = await get_cashflow(db_session, feb, feb, "day")

    assert year["series"][0]["closing"] == Decimal("1355.03")
    assert month["opening_cash_balance"] == year["series"][1]["opening"] == Decimal("1355.03")
    assert month["closing_cash_balance"] == year["series"][1]["closing"] == Decimal("1264.99")
    assert day["closing_cash_balance"] == month["series"][0]["closing"]
    assert year["totals"]["inflow"] == Decimal("1200.24")
    assert year["totals"]["financing_inflow"] == Decimal("300.00")
    assert month["unmatched_bank_count"] == 1
    assert year["opening_cash_balance"] + year["totals"]["net"] == year["closing_cash_balance"]
    assert all(a["closing"] == b["opening"] for a, b in zip(month["series"], month["series"][1:], strict=False))


@pytest.mark.parametrize(
    "reference_date, reference_balance", [(date(2025, 1, 1), "1000.00"), (date(2025, 3, 1), "920.00")]
)
async def test_opening_reference_works_before_and_after_range(
    db_session, make_expense, reference_date, reference_balance
):
    db_session.add(
        Enterprise(name="Test", opening_cash_date=reference_date, opening_cash_balance=Decimal(reference_balance))
    )
    await make_expense(db_session, amount="50", status="paid", source="cash", expense_date=date(2025, 1, 31))
    await make_expense(db_session, amount="30", status="paid", source="cash", expense_date=date(2025, 2, 1))
    await db_session.flush()
    report = await get_cashflow(db_session, date(2025, 2, 1), date(2025, 2, 28), "month")
    assert report["opening_cash_balance"] == Decimal("950.00")
    assert report["closing_cash_balance"] == Decimal("920.00")


async def test_cash_reversal_changes_history_on_its_payment_date(db_session, make_expense):
    await make_expense(db_session, amount="40.12", status="paid", source="cash", expense_date=date(2025, 1, 10))
    reversal = await make_expense(
        db_session, amount="-40.12", status="reversed", source="cash", expense_date=date(2025, 2, 10)
    )
    reversal.paid_date = date(2025, 2, 10)
    await db_session.flush()
    report = await get_cashflow(db_session, date(2025, 2, 1), date(2025, 2, 28), "month")
    after = await get_cashflow(db_session, date(2025, 3, 1), date(2025, 3, 31), "month")
    assert report["opening_cash_balance"] == Decimal("-40.12")
    assert report["totals"]["outflow"] == Decimal("-40.12")
    assert report["closing_cash_balance"] == after["opening_cash_balance"] == Decimal("0.00")


async def test_future_periods_and_payments_are_not_displayed_as_facts(db_session, make_expense):
    today = date.today()
    tomorrow = today + timedelta(days=1)
    await make_expense(db_session, amount="10", status="paid", source="cash", expense_date=today)
    await make_expense(db_session, amount="99", status="paid", source="cash", expense_date=tomorrow)
    report = await get_cashflow(db_session, today, tomorrow, "day")
    assert report["range"]["to"] == today.isoformat()
    assert report["requested_range"]["to"] == tomorrow.isoformat()
    assert len(report["series"]) == 1
    assert report["totals"]["outflow"] == Decimal("10.00")


async def test_empty_report_carries_configured_balance(db_session):
    db_session.add(Enterprise(name="Test", opening_cash_date=date(2025, 1, 1), opening_cash_balance=Decimal("123.45")))
    await db_session.flush()
    report = await get_cashflow(db_session, date(2025, 2, 1), date(2025, 2, 28), "month")
    assert report["opening_cash_balance"] == report["closing_cash_balance"] == Decimal("123.45")
    assert report["totals"]["net"] == 0


@pytest.mark.parametrize(
    "start, end, group",
    [
        (date(2025, 2, 2), date(2025, 2, 1), "month"),
        (date.today() + timedelta(days=1), date.today() + timedelta(days=2), "day"),
        (date(2024, 1, 1), date(2025, 1, 1), "day"),
    ],
)
async def test_invalid_cashflow_ranges_return_422(db_session, start, end, group):
    with pytest.raises(HTTPException) as exc:
        await finance_cashflow(from_=start, to=end, group_by=group, db=db_session, current_user=None)
    assert exc.value.status_code == 422
