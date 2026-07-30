from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from backend.bank_matching_service import (
    MATCH_TYPE_INCOME_ALLOCATION,
    MATCH_TYPE_OWNER_FUNDS,
    classify_transaction_as_owner_funds,
    detach_income_transaction_link,
    match_transaction,
    reconcile_income_payment_links,
    save_income_allocation,
    suggest_matches,
    unmatch_transaction,
)
from backend.incoming_invoice_service import create_incoming_invoice
from backend.models import BankTransactionIncomeAllocation, Contract, Expense, MonthlyObligation, PaymentType
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
async def test_match_transaction_marks_obligation_paid_and_matches_transaction(
    db_session,
    make_bank_tx,
):
    payment_type = PaymentType(code="tax", name_sr="Porez", sort_order=1)
    db_session.add(payment_type)
    await db_session.flush()
    obligation = MonthlyObligation(
        year=2026,
        month=6,
        payment_type_id=payment_type.id,
        amount=Decimal("123.45"),
        deadline=date(2026, 7, 15),
        status="unpaid",
        created_at=TEST_NOW,
    )
    db_session.add(obligation)
    await db_session.flush()
    tx = await make_bank_tx(
        db_session,
        amount=Decimal("123.45"),
        direction="out",
        bank_reference="OBL-REF",
    )

    matched_tx = await match_transaction(db_session, tx.id, "obligation", obligation.id)

    expense = await db_session.get(Expense, obligation.expense_id)
    assert matched_tx.status == "matched"
    assert matched_tx.matched_type == "obligation"
    assert matched_tx.matched_id == obligation.id
    assert obligation.status == "paid"
    assert obligation.paid_date == TEST_DATE
    assert obligation.payment_method == "bank_import"
    assert obligation.payment_reference == "OBL-REF"
    assert expense is not None
    assert expense.status == "paid"
    assert expense.source == "obligation"
    assert expense.bank_reference == "OBL-REF"


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
async def test_match_transaction_rejects_missing_transaction(db_session):
    with pytest.raises(ValueError, match="BankTransaction not found"):
        await match_transaction(db_session, 999, "income", 1)


@pytest.mark.asyncio
async def test_match_transaction_rejects_missing_income(db_session, make_bank_tx):
    tx = await make_bank_tx(db_session, direction="in")

    with pytest.raises(ValueError, match="Income not found"):
        await match_transaction(db_session, tx.id, "income", 999)


@pytest.mark.asyncio
async def test_match_transaction_rejects_missing_expense(db_session, make_bank_tx):
    tx = await make_bank_tx(db_session, direction="out")

    with pytest.raises(ValueError, match="Expense not found"):
        await match_transaction(db_session, tx.id, "expense", 999)


@pytest.mark.asyncio
async def test_match_transaction_rejects_missing_obligation(db_session, make_bank_tx):
    tx = await make_bank_tx(db_session, direction="out")

    with pytest.raises(ValueError, match="MonthlyObligation not found"):
        await match_transaction(db_session, tx.id, "obligation", 999)


@pytest.mark.asyncio
async def test_match_transaction_rejects_unknown_match_type(db_session, make_bank_tx):
    tx = await make_bank_tx(db_session, direction="in")

    with pytest.raises(ValueError, match="Unknown match type"):
        await match_transaction(db_session, tx.id, "unknown", 1)


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


@pytest.mark.asyncio
async def test_owner_funds_classification_can_be_unmatched(
    db_session,
    make_bank_tx,
    make_project,
):
    project = await make_project(db_session, code="PR-OWNER")
    tx = await make_bank_tx(db_session, amount=Decimal("100.00"), direction="in", project_id=project.id)

    classified_tx = await classify_transaction_as_owner_funds(db_session, tx.id)

    assert classified_tx.status == "matched"
    assert classified_tx.matched_type == MATCH_TYPE_OWNER_FUNDS
    assert classified_tx.matched_id is None
    assert classified_tx.project_id is None

    unmatched_tx = await unmatch_transaction(db_session, tx.id)

    assert unmatched_tx.status == "unmatched"
    assert unmatched_tx.matched_type is None
    assert unmatched_tx.matched_id is None
    assert unmatched_tx.project_id is None


@pytest.mark.asyncio
async def test_suggest_matches_returns_income_candidate_without_fixing_score(
    db_session,
    make_bank_tx,
    make_income,
):
    income = await make_income(
        db_session,
        amount=Decimal("100.00"),
        invoice_number="INV-2026-001",
        client_name="Acme Doo",
    )
    tx = await make_bank_tx(
        db_session,
        amount=Decimal("100.00"),
        direction="in",
        counterparty_name="Acme Doo Beograd",
        purpose="Payment for INV-2026-001",
    )

    suggestions = await suggest_matches(db_session, tx)

    assert suggestions
    assert suggestions[0]["id"] == income.id
    assert suggestions[0]["type"] == "income"
    assert suggestions[0]["section"] == "suggested"


@pytest.mark.asyncio
async def test_suggest_matches_returns_open_incoming_invoice_expense(
    db_session,
    make_bank_tx,
):
    invoice = await create_incoming_invoice(
        db_session,
        invoice_number="PP-260729-1424654",
        invoice_date=date(2026, 7, 29),
        client_id=None,
        counterparty_name="Alta banka",
        project_id=None,
        amount=Decimal("80.00"),
        description="Naknada za domace platne transakcije",
    )
    tx = await make_bank_tx(
        db_session,
        amount=Decimal("80.00"),
        direction="out",
        tx_date=date(2026, 7, 23),
        counterparty_name="ALTA BANKA AD-racun provizije",
        purpose="Obracun provizije za dan 2026.07.23",
    )

    suggestions = await suggest_matches(db_session, tx)

    assert suggestions
    assert suggestions[0] == {
        "id": invoice.expense_id,
        "type": "expense",
        "invoice_number": "PP-260729-1424654",
        "client_name": "Alta banka",
        "description": "Naknada za domace platne transakcije",
        "amount": Decimal("80.00"),
        "amount_full": None,
        "amount_paid": None,
        "date": "2026-07-29",
        "status": "unpaid",
        "score": 94,
        "section": "suggested",
    }

    matched_tx = await match_transaction(db_session, tx.id, suggestions[0]["type"], suggestions[0]["id"])
    linked_expense = await db_session.get(Expense, invoice.expense_id)

    assert matched_tx.status == "matched"
    assert matched_tx.matched_type == "expense"
    assert matched_tx.matched_id == invoice.expense_id
    assert invoice.status == "paid"
    assert invoice.settled_amount == Decimal("80.00")
    assert linked_expense.status == "paid"


@pytest.mark.asyncio
async def test_suggest_matches_excludes_incoming_invoice_with_different_remaining_amount(
    db_session,
    make_bank_tx,
):
    await create_incoming_invoice(
        db_session,
        invoice_number="PP-OTHER-AMOUNT",
        invoice_date=TEST_DATE,
        client_id=None,
        counterparty_name="Alta banka",
        project_id=None,
        amount=Decimal("120.00"),
    )
    tx = await make_bank_tx(
        db_session,
        amount=Decimal("80.00"),
        direction="out",
        counterparty_name="Alta banka",
    )

    assert await suggest_matches(db_session, tx) == []


@pytest.mark.asyncio
async def test_suggest_matches_excludes_incoming_invoice_with_negative_remaining_amount(
    db_session,
    make_bank_tx,
):
    invoice = await create_incoming_invoice(
        db_session,
        invoice_number="PP-OVERSETTLED",
        invoice_date=TEST_DATE,
        client_id=None,
        counterparty_name="Alta banka",
        project_id=None,
        amount=Decimal("100.00"),
    )
    invoice.settled_amount = Decimal("180.00")
    tx = await make_bank_tx(
        db_session,
        amount=Decimal("80.00"),
        direction="out",
        counterparty_name="Alta banka",
    )

    assert await suggest_matches(db_session, tx) == []


@pytest.mark.asyncio
async def test_suggest_matches_keeps_old_open_incoming_invoice_available(
    db_session,
    make_bank_tx,
):
    invoice = await create_incoming_invoice(
        db_session,
        invoice_number="PP-OLD-OPEN",
        invoice_date=date(2026, 1, 10),
        client_id=None,
        counterparty_name="Alta banka",
        project_id=None,
        amount=Decimal("80.00"),
    )
    tx = await make_bank_tx(
        db_session,
        amount=Decimal("80.00"),
        direction="out",
        tx_date=date(2026, 7, 23),
        counterparty_name="Alta banka",
    )

    suggestions = await suggest_matches(db_session, tx)

    assert len(suggestions) == 1
    assert suggestions[0]["id"] == invoice.expense_id
    assert suggestions[0]["section"] == "suggested"


@pytest.mark.asyncio
async def test_suggest_matches_ignores_owner_funds_transaction(
    db_session,
    make_bank_tx,
):
    tx = await make_bank_tx(db_session, amount=Decimal("100.00"), direction="in")
    await classify_transaction_as_owner_funds(db_session, tx.id)

    assert await suggest_matches(db_session, tx) == []
