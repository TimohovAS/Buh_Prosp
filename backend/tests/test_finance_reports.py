from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException

from backend.finance_service import get_accounts_receivable, get_finance_pnl, get_finance_summary
from backend.models import BankTransactionIncomeAllocation
from backend.routers.finance_router import finance_summary
from backend.schemas import FinancePnlResponse
from backend.services import get_finance_limits_overview


async def test_historical_receivables_include_invoices_paid_later(db_session, make_income, make_bank_tx):
    invoice = await make_income(
        db_session, amount="1000.13", paid_amount="1000.13", status="paid", issued_date=date(2025, 1, 1)
    )
    invoice.due_date = date(2025, 1, 31)
    invoice.paid_date = date(2025, 3, 5)
    first = await make_bank_tx(
        db_session, amount="400.01", tx_date=date(2025, 1, 31), status="matched", bank_reference="FIRST"
    )
    first.matched_type, first.matched_id = "income", invoice.id
    last = await make_bank_tx(
        db_session, amount="600.12", tx_date=date(2025, 3, 5), status="matched", bank_reference="LAST"
    )
    last.matched_type = "income_allocation"
    db_session.add(
        BankTransactionIncomeAllocation(bank_transaction_id=last.id, income_id=invoice.id, amount=Decimal("600.12"))
    )
    await db_session.flush()
    before = await get_accounts_receivable(db_session, date(2025, 1, 30))
    on_due = await get_accounts_receivable(db_session, date(2025, 1, 31))
    february = await get_accounts_receivable(db_session, date(2025, 2, 28))
    paid = await get_accounts_receivable(db_session, date(2025, 3, 5))
    assert before["totals"]["ar_total"] == Decimal("1000.13")
    assert on_due["totals"]["ar_total"] == Decimal("600.12")
    assert on_due["totals"]["ar_overdue"] == 0
    assert february["items"][0]["amount_paid"] == Decimal("400.01")
    assert february["items"][0]["status"] == "partial"
    assert february["items"][0]["days_overdue"] == 28
    assert february["totals"]["ar_overdue"] == Decimal("600.12")
    assert paid["items"] == []


async def test_manual_payment_date_and_bank_amount_are_not_double_counted(db_session, make_income, make_bank_tx):
    invoice = await make_income(
        db_session, amount="1000", paid_amount="700", status="partial", issued_date=date(2025, 1, 1)
    )
    invoice.paid_date = date(2025, 2, 1)
    bank = await make_bank_tx(db_session, amount="400", tx_date=date(2025, 1, 15), status="matched")
    bank.matched_type, bank.matched_id = "income", invoice.id
    await db_session.flush()
    january = await get_accounts_receivable(db_session, date(2025, 1, 31))
    february = await get_accounts_receivable(db_session, date(2025, 2, 1))
    assert january["totals"]["ar_total"] == Decimal("600")
    assert february["totals"]["ar_total"] == Decimal("300")


async def test_undated_manual_payments_are_flagged_in_historical_snapshot(db_session, make_income):
    await make_income(db_session, amount="100", paid_amount="100", status="paid", issued_date=date(2025, 1, 1))
    historical = await get_accounts_receivable(db_session, date(2025, 1, 31))
    current = await get_accounts_receivable(db_session)
    assert historical["totals"]["ar_total"] == Decimal("100")
    assert historical["missing_payment_dates"] == 1
    assert current["totals"]["ar_total"] == 0


async def test_unknown_due_date_is_not_an_invented_overdue_debt(db_session, make_income):
    await make_income(db_session, amount="10.01", issued_date=date(2025, 1, 1))
    report = await get_accounts_receivable(db_session, date(2025, 12, 31))
    assert report["items"][0]["due_date"] is None
    assert report["items"][0]["days_overdue"] is None
    assert report["totals"]["ar_overdue"] == 0
    assert report["totals"]["ar_without_due_date"] == Decimal("10.01")


async def test_aging_buckets_partition_the_balance(db_session, make_income):
    cutoff = date(2025, 12, 31)
    for index, days in enumerate((0, 1, 30, 31, 60, 61, 90, 91)):
        invoice = await make_income(
            db_session, amount="10.01", invoice_number=f"AGE-{index}", issued_date=date(2025, 1, 1)
        )
        invoice.due_date = cutoff - timedelta(days=days)
    await make_income(
        db_session, amount="999", status="cancelled", invoice_number="CANCELLED", issued_date=date(2025, 1, 1)
    )
    await make_income(db_session, amount="999", invoice_number="FUTURE", issued_date=date(2026, 1, 1))
    await db_session.flush()
    report = await get_accounts_receivable(db_session, cutoff)
    counts = {bucket["key"]: bucket["count"] for bucket in report["aging"]}
    assert counts == {"not_due": 1, "1_30": 2, "31_60": 2, "61_90": 2, "over_90": 1, "no_due": 0}
    assert sum(bucket["amount"] for bucket in report["aging"]) == report["totals"]["ar_total"] == Decimal("80.08")
    assert report["totals"]["overdue_count"] == 7


async def test_limits_respect_historical_cutoff(db_session, make_income):
    await make_income(db_session, amount="100.01", invoice_number="BEFORE", issued_date=date(2025, 1, 31))
    await make_income(db_session, amount="900", invoice_number="AFTER", issued_date=date(2025, 2, 1))
    report = await get_finance_limits_overview(db_session, date(2025, 1, 31))
    assert report["annual_total"] == Decimal("100.01")
    assert report["rolling_12_total"] == Decimal("100.01")
    assert report["forecast_year_end"] == Decimal("1200.12")


async def test_pnl_and_overview_agree_with_tax_subset_and_reversals(db_session, make_income, make_expense):
    day = date(2025, 2, 5)
    await make_income(db_session, amount="1000.13", issued_date=day)
    await make_expense(db_session, amount="200.12", status="paid", expense_date=day)
    tax = await make_expense(db_session, amount="50.01", status="paid", expense_date=day)
    tax.is_tax_related = True
    await make_expense(db_session, amount="-20.01", status="reversed", expense_date=day)
    await make_expense(db_session, amount="30.05", status="planned", source="receipt", expense_date=day)
    await make_expense(db_session, amount="999", status="planned", expense_date=day)
    await make_expense(db_session, amount="999", status="paid", source="cash_transfer", expense_date=day)
    await db_session.flush()
    pnl = await get_finance_pnl(db_session, 2025)
    overview = await get_finance_summary(db_session, date(2025, 1, 1), date(2025, 12, 31), "month", "accrual")
    assert pnl["totals"]["expenses"] == Decimal("210.16")
    assert pnl["totals"]["taxes"] == Decimal("50.01")
    assert pnl["totals"]["profit"] == overview["totals"]["net_profit_accrual"] == Decimal("739.96")
    assert pnl["totals"]["expenses"] + pnl["totals"]["taxes"] == overview["totals"]["expense_accrual"]
    assert len(pnl["items"]) == 12
    assert FinancePnlResponse(**pnl).date_to == date(2025, 12, 31)


async def test_pnl_does_not_present_future_documents_as_current_results(db_session, make_income):
    today = date.today()
    await make_income(db_session, amount="10", invoice_number="TODAY", issued_date=today)
    await make_income(db_session, amount="1000", invoice_number="TOMORROW", issued_date=today + timedelta(days=1))
    report = await get_finance_pnl(db_session, today.year)
    assert report["date_to"] == today
    assert len(report["items"]) == today.month
    assert report["totals"]["revenue"] == Decimal("10")


async def test_finance_summary_rejects_reversed_range(db_session):
    with pytest.raises(HTTPException) as exc:
        await finance_summary(
            from_=date(2025, 2, 2),
            to=date(2025, 2, 1),
            group_by="month",
            mode="both",
            client_id=None,
            contract_id=None,
            project_id=None,
            category=None,
            is_tax_related=None,
            db=db_session,
            current_user=None,
        )
    assert exc.value.status_code == 422
