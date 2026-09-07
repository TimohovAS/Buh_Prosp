from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from backend.bank_matching_service import match_transaction, suggest_matches, unmatch_transaction
from backend.models import Expense, MonthlyObligation, PaymentType, YearDecision
from backend.obligation_payment_service import mark_obligation_paid, reset_obligation_payment
from backend.schemas import MatchCandidate
from backend.tests.conftest import TEST_NOW


PAYMENT_DATE = date(2026, 9, 3)
TAXES = {
    "tax": ("5122.16", "840-711122843-32", "840000071112284332", "87000121738629", "Порез на приход"),
    "pio": ("12311.28", "840-721419843-40", "840000072141984340", "87000121738662", "Допринос за ПИО"),
}
pytestmark = pytest.mark.filterwarnings("ignore:datetime.datetime.utcnow\\(\\) is deprecated:DeprecationWarning")


@pytest.fixture(params=TAXES)
async def tax_case(request, db_session, make_bank_tx):
    code = request.param
    amount, account, bank_account, reference, name = TAXES[code]
    payment_type = PaymentType(code=code, name_sr=name, sort_order=1)
    db_session.add(payment_type)
    await db_session.flush()
    decision = YearDecision(
        year=2026,
        payment_type_id=payment_type.id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        monthly_amount=Decimal(amount),
        recipient_account=account,
        poziv_na_broj="2624190000007887475",
        payment_purpose="Payment for YYYY",
    )
    db_session.add(decision)
    await db_session.flush()

    async def obligation(month=8, paid=True, payment_reference=reference, paid_date=PAYMENT_DATE):
        item = MonthlyObligation(
            year=2026,
            month=month,
            payment_type_id=payment_type.id,
            decision_id=decision.id,
            amount=Decimal(amount),
            deadline=date(2026, month + 1, 15) if month < 12 else date(2027, 1, 15),
            status="unpaid",
            created_at=TEST_NOW,
        )
        db_session.add(item)
        await db_session.flush()
        if paid:
            await mark_obligation_paid(db_session, item, paid_date, payment_reference=payment_reference)
        return item

    async def transaction(**kwargs):
        values = dict(
            amount=-Decimal(amount),
            direction="out",
            tx_date=PAYMENT_DATE,
            bank_reference=reference,
            counterparty_name=f"Poreska uprava Republike Srbije NOTPROVIDED {bank_account}",
            purpose="Payment",  # Account/reference must work independently of tax/PIO wording.
        )
        values.update(kwargs)
        return await make_bank_tx(db_session, **values)

    return obligation, transaction


async def test_recorded_tax_payment_is_first_and_survives_candidate_serialization(db_session, tax_case):
    make_obligation, make_transaction = tax_case
    paid = await make_obligation()
    await make_obligation(month=7, paid_date=date(2026, 8, 4), payment_reference="OLDER-PAYMENT")
    nearby_open = await make_obligation(month=7, paid=False)
    future = await make_obligation(month=9, paid=False)
    tx = await make_transaction()

    candidates = await suggest_matches(db_session, tx)
    assert [item["id"] for item in candidates if item["section"] == "suggested"] == [paid.id]
    top = MatchCandidate.model_validate(candidates[0]).model_dump(mode="json")
    assert top["id"] == paid.id
    assert top["payment_reference"] == tx.bank_reference
    assert top["date"] == "2026-09-03"
    assert top["status"] == "paid"
    assert top["score"] == 100
    assert top["match_reason"] == "obligation_payment_reference"
    assert {item["id"] for item in candidates if item["section"] == "all"} == {future.id, nearby_open.id}


async def test_link_and_unlink_manual_tax_preserve_expense_and_manual_payment(db_session, tax_case):
    make_obligation, make_transaction = tax_case
    paid = await make_obligation(paid_date=PAYMENT_DATE - timedelta(days=1))
    tx = await make_transaction()
    expense = await db_session.get(Expense, paid.expense_id)
    original_expense = {column.name: getattr(expense, column.name) for column in Expense.__table__.columns}
    original_payment = {column.name: getattr(paid, column.name) for column in MonthlyObligation.__table__.columns}

    await match_transaction(db_session, tx.id, "obligation", paid.id)
    await db_session.commit()
    assert tx.status == "matched"
    assert tx.matched_type == "obligation"
    assert tx.matched_id == paid.id
    assert await db_session.scalar(select(func.count(Expense.id))) == 1
    assert await suggest_matches(db_session, tx) == []
    await db_session.refresh(expense)
    assert {key: getattr(expense, key) for key in original_expense} == original_expense
    assert {key: getattr(paid, key) for key in original_payment} == original_payment

    await unmatch_transaction(db_session, tx.id)
    await db_session.commit()
    await db_session.refresh(expense)
    assert tx.status == "unmatched"
    assert tx.matched_id is None
    assert await db_session.scalar(select(func.count(Expense.id))) == 1
    assert {key: getattr(expense, key) for key in original_expense} == original_expense
    assert {key: getattr(paid, key) for key in original_payment} == original_payment
    assert (await suggest_matches(db_session, tx))[0]["id"] == paid.id


@pytest.mark.parametrize("link_type", ["obligation", "expense"])
async def test_already_linked_tax_is_excluded_and_cannot_be_linked_again(db_session, tax_case, link_type):
    make_obligation, make_transaction = tax_case
    paid = await make_obligation()
    first = await make_transaction()
    first.status, first.matched_type = "matched", link_type
    first.matched_id = paid.id if link_type == "obligation" else paid.expense_id
    await db_session.flush()
    second = await make_transaction(bank_reference=None)
    assert await suggest_matches(db_session, second) == []
    with pytest.raises(ValueError, match="already linked"):
        await match_transaction(db_session, second.id, "obligation", paid.id)
    assert second.status == "unmatched"
    assert await db_session.scalar(select(func.count(Expense.id))) == 1


@pytest.mark.parametrize("days_apart, suggested", [(0, True), (7, True), (8, False)])
async def test_missing_reference_uses_real_payment_date_and_padded_account(db_session, tax_case, days_apart, suggested):
    make_obligation, make_transaction = tax_case
    paid = await make_obligation(month=12, payment_reference=None, paid_date=PAYMENT_DATE - timedelta(days=days_apart))
    candidates = await suggest_matches(db_session, await make_transaction())
    assert len(candidates) == 1
    assert candidates[0]["id"] == paid.id
    assert (candidates[0]["section"] == "suggested") == suggested
    if suggested:
        assert candidates[0]["match_reason"] == "obligation_payment_date"


async def test_exact_reference_works_without_recipient_terms_and_with_a_distant_deadline(db_session, tax_case):
    make_obligation, make_transaction = tax_case
    paid = await make_obligation(month=12)
    tx = await make_transaction(counterparty_name="NOTPROVIDED", purpose="NOTPROVIDED")
    candidates = await suggest_matches(db_session, tx)
    assert candidates[0]["id"] == paid.id
    assert candidates[0]["score"] == 100


async def test_different_transaction_number_is_not_a_match_even_with_same_amount_and_date(db_session, tax_case):
    make_obligation, make_transaction = tax_case
    paid = await make_obligation(payment_reference="OTHER-TRANSACTION")
    tx = await make_transaction()
    assert await suggest_matches(db_session, tx) == []
    with pytest.raises(ValueError, match="number does not match"):
        await match_transaction(db_session, tx.id, "obligation", paid.id)
    assert tx.status == "unmatched"


@pytest.mark.parametrize("invalid", ["amount", "currency", "direction"])
async def test_link_rejects_incompatible_statement_without_changing_payment(db_session, tax_case, invalid):
    make_obligation, make_transaction = tax_case
    paid = await make_obligation()
    tx = await make_transaction()
    if invalid == "amount":
        tx.amount -= Decimal("0.01")
    elif invalid == "currency":
        tx.currency = "EUR"
    else:
        tx.direction = "in"
    with pytest.raises(ValueError):
        await match_transaction(db_session, tx.id, "obligation", paid.id)
    assert tx.status == "unmatched"
    assert paid.status == "paid"
    assert await db_session.scalar(select(func.count(Expense.id))) == 1
    if invalid != "direction":
        assert await suggest_matches(db_session, tx) == []


@pytest.mark.parametrize("invalid", ["missing", "reversed", "bank_import"])
async def test_paid_tax_with_invalid_expense_or_payment_source_is_not_linkable(db_session, tax_case, invalid):
    make_obligation, make_transaction = tax_case
    paid = await make_obligation()
    if invalid == "missing":
        paid.expense_id = None
    elif invalid == "reversed":
        expense = await db_session.get(Expense, paid.expense_id)
        expense.status = "reversed"
    else:
        paid.payment_method = "bank_import"
    await db_session.flush()
    tx = await make_transaction()
    assert await suggest_matches(db_session, tx) == []
    with pytest.raises(ValueError):
        await match_transaction(db_session, tx.id, "obligation", paid.id)
    assert tx.status == "unmatched"
    assert await db_session.scalar(select(func.count(Expense.id))) == 1


async def test_future_months_are_not_suggested_from_repeated_tax_reference(db_session, tax_case):
    make_obligation, make_transaction = tax_case
    nearby = await make_obligation(paid=False)
    future = [await make_obligation(month=month, paid=False) for month in (9, 10, 11, 12)]
    tx = await make_transaction(purpose="2624190000007887475")
    candidates = await suggest_matches(db_session, tx)
    assert [item["id"] for item in candidates if item["section"] == "suggested"] == [nearby.id]
    assert {item["id"] for item in candidates if item["section"] == "all"} == {item.id for item in future}


async def test_new_bank_payment_still_creates_expense_and_unlink_reverses_it(db_session, tax_case):
    make_obligation, make_transaction = tax_case
    item = await make_obligation(paid=False)
    tx = await make_transaction()
    await match_transaction(db_session, tx.id, "obligation", item.id)
    assert item.payment_method == "bank_import"
    expense = await db_session.get(Expense, item.expense_id)
    assert expense.status == "paid"
    await unmatch_transaction(db_session, tx.id)
    assert tx.status == "unmatched"
    assert item.status != "paid"
    assert item.expense_id is None
    reversal = await db_session.get(Expense, expense.reversed_expense_id)
    assert reversal.status == "reversed"
    assert reversal.reversal_of_id == expense.id
    assert reversal.amount == -expense.amount


async def test_explicit_payment_reset_still_cancels_manual_payment_and_detaches_statement(db_session, tax_case):
    make_obligation, make_transaction = tax_case
    item = await make_obligation()
    tx = await make_transaction()
    await match_transaction(db_session, tx.id, "obligation", item.id)
    expense = await db_session.get(Expense, item.expense_id)
    await reset_obligation_payment(db_session, item)
    assert tx.status == "unmatched"
    assert tx.matched_id is None
    assert item.status != "paid"
    reversal = await db_session.get(Expense, expense.reversed_expense_id)
    assert reversal.status == "reversed"
    assert reversal.reversal_of_id == expense.id
    assert reversal.amount == -expense.amount
