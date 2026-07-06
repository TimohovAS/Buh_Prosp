from datetime import date
from decimal import Decimal

import pytest

from backend.bank_matching_service import match_transaction, unmatch_transaction
from backend.models import Contract
from backend.tests.conftest import TEST_DATE, TEST_NOW

pytestmark = pytest.mark.filterwarnings("ignore:datetime.datetime.utcnow\\(\\) is deprecated:DeprecationWarning")


@pytest.mark.asyncio
async def test_match_transaction_links_partial_income_payment(
    db_session,
    make_bank_tx,
    make_income,
    make_project,
):
    project = await make_project(db_session, code="PR-INCOME")
    income = await make_income(db_session, amount=Decimal("100.00"))
    tx = await make_bank_tx(
        db_session,
        amount=Decimal("40.00"),
        direction="in",
        bank_reference="BANK-40",
        project_id=project.id,
    )

    matched_tx = await match_transaction(db_session, tx.id, "income", income.id)

    assert matched_tx.status == "matched"
    assert matched_tx.matched_type == "income"
    assert matched_tx.matched_id == income.id
    assert matched_tx.project_id == project.id
    assert income.project_id == project.id
    assert income.status == "partial"
    assert income.is_paid is False
    assert income.paid_amount == Decimal("40.00")
    assert income.paid_date is None
    assert income.bank_reference == "BANK-40"


@pytest.mark.asyncio
async def test_unmatch_transaction_reopens_direct_income_payment(
    db_session,
    make_bank_tx,
    make_income,
    make_project,
):
    project = await make_project(db_session, code="PR-INCOME")
    income = await make_income(db_session, amount=Decimal("100.00"))
    tx = await make_bank_tx(
        db_session,
        amount=Decimal("100.00"),
        direction="in",
        bank_reference="BANK-100",
        project_id=project.id,
    )
    await match_transaction(db_session, tx.id, "income", income.id)

    unmatched_tx = await unmatch_transaction(db_session, tx.id)

    assert unmatched_tx.status == "unmatched"
    assert unmatched_tx.matched_type is None
    assert unmatched_tx.matched_id is None
    assert unmatched_tx.project_id is None
    assert income.status == "issued"
    assert income.is_paid is False
    assert income.paid_amount == Decimal("0.00")
    assert income.paid_date is None
    assert income.bank_reference is None


@pytest.mark.asyncio
async def test_match_transaction_marks_expense_paid_and_clears_mismatched_contract(
    db_session,
    make_bank_tx,
    make_expense,
    make_project,
):
    contract_project = await make_project(db_session, code="PR-CONTRACT")
    tx_project = await make_project(db_session, code="PR-TX")
    contract = Contract(
        number="C-001",
        date=date(2026, 1, 10),
        client_id=1,
        project_id=contract_project.id,
        amount=Decimal("100.00"),
        currency="RSD",
        status="active",
        created_at=TEST_NOW,
        updated_at=TEST_NOW,
    )
    db_session.add(contract)
    await db_session.flush()
    expense = await make_expense(
        db_session,
        amount=Decimal("100.00"),
        status="planned",
        project_id=contract_project.id,
        contract_id=contract.id,
    )
    tx = await make_bank_tx(
        db_session,
        amount=Decimal("100.00"),
        direction="out",
        bank_reference="EXP-REF",
        project_id=tx_project.id,
    )

    matched_tx = await match_transaction(db_session, tx.id, "expense", expense.id)

    assert matched_tx.status == "matched"
    assert matched_tx.matched_type == "expense"
    assert matched_tx.matched_id == expense.id
    assert expense.status == "paid"
    assert expense.paid_date == TEST_DATE
    assert expense.bank_reference == "EXP-REF"
    assert expense.project_id == tx_project.id
    assert expense.contract_id is None


@pytest.mark.asyncio
async def test_unmatch_transaction_reopens_expense_payment(
    db_session,
    make_bank_tx,
    make_expense,
):
    expense = await make_expense(db_session, amount=Decimal("100.00"), status="planned")
    tx = await make_bank_tx(db_session, amount=Decimal("100.00"), direction="out")
    await match_transaction(db_session, tx.id, "expense", expense.id)

    unmatched_tx = await unmatch_transaction(db_session, tx.id)

    assert unmatched_tx.status == "unmatched"
    assert unmatched_tx.matched_type is None
    assert unmatched_tx.matched_id is None
    assert expense.status == "planned"
    assert expense.paid_date is None


@pytest.mark.asyncio
async def test_match_transaction_rejects_already_matched_transaction(
    db_session,
    make_bank_tx,
    make_income,
):
    first_income = await make_income(db_session, amount=Decimal("100.00"), invoice_number="INV-001")
    second_income = await make_income(db_session, amount=Decimal("100.00"), invoice_number="INV-002")
    tx = await make_bank_tx(db_session, amount=Decimal("100.00"), direction="in")
    await match_transaction(db_session, tx.id, "income", first_income.id)

    with pytest.raises(ValueError, match="Transaction is already matched"):
        await match_transaction(db_session, tx.id, "income", second_income.id)
