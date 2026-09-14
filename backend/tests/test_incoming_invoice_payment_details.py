from decimal import Decimal

import pytest

from backend.incoming_invoice_service import create_incoming_invoice, link_advance_invoice
from backend.models import IncomingInvoice
from backend.routers.incoming_invoices_router import _load_payment_details
from backend.tests.conftest import TEST_DATE


async def test_zero_closing_invoice_paid_by_advance_needs_no_bank_link(db_session, make_expense):
    advance_expense = await make_expense(db_session, amount=Decimal("912.00"), status="paid")
    advance = IncomingInvoice(
        invoice_number="26-370-000875",
        date=TEST_DATE,
        counterparty_name="MIKRO PRINC",
        amount=Decimal("912.00"),
        settled_amount=Decimal("912.00"),
        status="paid",
        expense_id=advance_expense.id,
        settlements=[],
    )
    db_session.add(advance)
    await db_session.flush()
    closing = await create_incoming_invoice(
        db_session,
        invoice_number="26-30B-003696",
        invoice_date=TEST_DATE,
        client_id=None,
        counterparty_name="MIKRO PRINC",
        project_id=None,
        amount=Decimal("0.00"),
    )
    await link_advance_invoice(db_session, closing_invoice=closing, advance_invoice_id=advance.id)
    await db_session.flush()
    await db_session.refresh(closing, ["settlements"])

    details = await _load_payment_details(db_session, closing)

    assert closing.status == "paid"
    assert closing.remaining_amount == Decimal("0.00")
    assert details["expense"]["amount"] == Decimal("0.00")
    assert details["expense"]["status"] == "planned"
    assert details["bank_transaction"] is None
    assert details["settlements"] == []
    assert details["warning"] is None
    # The advance still needs its own payment evidence.
    advance_details = await _load_payment_details(db_session, advance)
    assert advance_details["warning"] == "linked_expense_without_bank_transaction"


@pytest.mark.parametrize("amount", [Decimal("0.00"), Decimal("912.00")])
async def test_missing_expense_warning_is_preserved(db_session, amount):
    invoice = IncomingInvoice(
        invoice_number="MISSING-EXPENSE",
        date=TEST_DATE,
        amount=amount,
        status="paid",
        expense_id=999999,
        settlements=[],
    )

    details = await _load_payment_details(db_session, invoice)

    assert details["warning"] == "missing_linked_expense"
