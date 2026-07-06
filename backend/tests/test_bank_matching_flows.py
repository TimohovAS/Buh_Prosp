from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from backend.bank_matching_service import (
    MATCH_TYPE_INCOME_ALLOCATION,
    detach_income_transaction_link,
    match_transaction,
    reconcile_income_payment_links,
    save_income_allocation,
    unmatch_transaction,
)
from backend.models import BankTransactionIncomeAllocation, Contract
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


@pytest.mark.asyncio
async def test_save_income_allocation_distributes_one_transaction_to_two_invoices(
    db_session,
    make_bank_tx,
    make_income,
    make_project,
):
    project = await make_project(db_session, code="PR-ALLOC")
    first_income = await make_income(
        db_session,
        amount=Decimal("70.00"),
        invoice_number="INV-ALLOC-1",
        project_id=project.id,
    )
    second_income = await make_income(
        db_session,
        amount=Decimal("50.00"),
        invoice_number="INV-ALLOC-2",
        project_id=project.id,
    )
    tx = await make_bank_tx(db_session, amount=Decimal("100.00"), direction="in", project_id=None)

    matched_tx = await save_income_allocation(
        db_session,
        tx.id,
        [
            {"income_id": first_income.id, "amount": Decimal("70.00")},
            {"income_id": second_income.id, "amount": Decimal("30.00")},
        ],
    )

    allocation_result = await db_session.execute(
        select(BankTransactionIncomeAllocation).order_by(BankTransactionIncomeAllocation.income_id.asc())
    )
    allocations = list(allocation_result.scalars().all())
    assert matched_tx.status == "matched"
    assert matched_tx.matched_type == MATCH_TYPE_INCOME_ALLOCATION
    assert matched_tx.matched_id is None
    assert matched_tx.project_id == project.id
    assert [(item.income_id, item.amount) for item in allocations] == [
        (first_income.id, Decimal("70.00")),
        (second_income.id, Decimal("30.00")),
    ]
    assert first_income.status == "paid"
    assert first_income.is_paid is True
    assert first_income.paid_amount == Decimal("70.00")
    assert first_income.paid_date == TEST_DATE
    assert second_income.status == "partial"
    assert second_income.is_paid is False
    assert second_income.paid_amount == Decimal("30.00")
    assert second_income.paid_date is None


@pytest.mark.asyncio
async def test_detach_income_transaction_link_removes_one_allocation_and_reconciles_invoices(
    db_session,
    make_bank_tx,
    make_income,
    make_project,
):
    project = await make_project(db_session, code="PR-DETACH")
    first_income = await make_income(
        db_session,
        amount=Decimal("70.00"),
        invoice_number="INV-DETACH-1",
        project_id=project.id,
    )
    second_income = await make_income(
        db_session,
        amount=Decimal("50.00"),
        invoice_number="INV-DETACH-2",
        project_id=project.id,
    )
    tx = await make_bank_tx(db_session, amount=Decimal("100.00"), direction="in")
    await save_income_allocation(
        db_session,
        tx.id,
        [
            {"income_id": first_income.id, "amount": Decimal("70.00")},
            {"income_id": second_income.id, "amount": Decimal("30.00")},
        ],
    )

    await detach_income_transaction_link(db_session, tx.id, first_income.id)

    allocation_result = await db_session.execute(select(BankTransactionIncomeAllocation))
    allocations = list(allocation_result.scalars().all())
    assert len(allocations) == 1
    assert allocations[0].income_id == second_income.id
    assert allocations[0].amount == Decimal("30.00")
    assert tx.status == "matched"
    assert tx.matched_type == MATCH_TYPE_INCOME_ALLOCATION
    assert tx.matched_id is None
    assert tx.project_id == project.id
    assert first_income.status == "issued"
    assert first_income.paid_amount == Decimal("0.00")
    assert first_income.paid_date is None
    assert second_income.status == "partial"
    assert second_income.paid_amount == Decimal("30.00")


@pytest.mark.asyncio
async def test_detach_income_transaction_link_unmatches_last_allocation(
    db_session,
    make_bank_tx,
    make_income,
):
    income = await make_income(db_session, amount=Decimal("100.00"), invoice_number="INV-DETACH-LAST")
    tx = await make_bank_tx(db_session, amount=Decimal("100.00"), direction="in")
    await save_income_allocation(
        db_session,
        tx.id,
        [{"income_id": income.id, "amount": Decimal("100.00")}],
    )

    await detach_income_transaction_link(db_session, tx.id, income.id)

    allocation_result = await db_session.execute(select(BankTransactionIncomeAllocation))
    assert list(allocation_result.scalars().all()) == []
    assert tx.status == "unmatched"
    assert tx.matched_type is None
    assert tx.matched_id is None
    assert tx.project_id is None
    assert income.status == "issued"
    assert income.is_paid is False
    assert income.paid_amount == Decimal("0.00")


@pytest.mark.asyncio
async def test_reconcile_income_payment_links_is_idempotent(
    db_session,
    make_bank_tx,
    make_income,
):
    income = await make_income(db_session, amount=Decimal("100.00"), invoice_number="INV-RECONCILE")
    tx = await make_bank_tx(db_session, amount=Decimal("40.00"), direction="in", bank_reference="RECONCILE-40")
    await save_income_allocation(
        db_session,
        tx.id,
        [{"income_id": income.id, "amount": Decimal("40.00")}],
    )

    first_snapshot = (
        income.status,
        income.is_paid,
        income.paid_amount,
        income.paid_date,
        income.bank_reference,
    )
    await reconcile_income_payment_links(db_session, {income.id})
    await reconcile_income_payment_links(db_session, {income.id})

    allocation_count = await db_session.scalar(select(func.count(BankTransactionIncomeAllocation.id)))
    assert (
        income.status,
        income.is_paid,
        income.paid_amount,
        income.paid_date,
        income.bank_reference,
    ) == first_snapshot
    assert allocation_count == 1
