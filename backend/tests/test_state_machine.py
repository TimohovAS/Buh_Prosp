from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.state_machine import (
    InvalidStatusTransition,
    cancel_income,
    cancel_incoming_invoice,
    ensure_expense_can_reverse,
    initialize_income_status,
    mark_expense_paid,
    mark_obligation_paid_status,
    reconcile_income_payment_state,
    reconcile_incoming_invoice_status,
    refresh_obligation_due_status,
    reopen_expense_for_unmatch,
    restore_obligation_after_payment_reset,
    transition_income_status,
)

TEST_DATE = date(2026, 7, 6)


def entity(**fields):
    return SimpleNamespace(**fields)


def test_initialize_income_status_issued_defaults_to_unpaid():
    income = entity(amount_rsd=Decimal("100.00"))

    initialize_income_status(income, "issued")

    assert income.status == "issued"
    assert income.is_paid is False
    assert income.paid_amount == Decimal("0")
    assert income.paid_date is None


def test_initialize_income_status_paid_requires_date():
    income = entity(amount_rsd=Decimal("100.00"))

    with pytest.raises(InvalidStatusTransition, match="requires paid_date"):
        initialize_income_status(income, "paid")


def test_initialize_income_status_paid_sets_amount_and_date():
    income = entity(amount_rsd=Decimal("100.00"))

    initialize_income_status(income, "paid", paid_date=TEST_DATE)

    assert income.status == "paid"
    assert income.is_paid is True
    assert income.paid_amount == Decimal("100.00")
    assert income.paid_date == TEST_DATE


def test_initialize_income_status_rejects_unknown_status():
    with pytest.raises(InvalidStatusTransition, match="unknown status"):
        initialize_income_status(entity(), "draft")


def test_transition_income_status_allows_issued_partial_paid_path():
    income = entity(status="issued", paid_amount=Decimal("0"), amount_rsd=Decimal("100.00"))

    transition_income_status(income, "partial", paid_amount=Decimal("40.00"))
    assert income.status == "partial"
    assert income.is_paid is False
    assert income.paid_amount == Decimal("40.00")
    assert income.paid_date is None

    transition_income_status(income, "paid", paid_amount=Decimal("100.00"), paid_date=TEST_DATE)
    assert income.status == "paid"
    assert income.is_paid is True
    assert income.paid_amount == Decimal("100.00")
    assert income.paid_date == TEST_DATE


@pytest.mark.parametrize(
    ("current_status", "target_status"),
    [
        ("paid", "issued"),
        ("cancelled", "issued"),
        ("cancelled", "paid"),
    ],
)
def test_transition_income_status_rejects_terminal_or_backward_transitions(current_status, target_status):
    income = entity(status=current_status, paid_amount=Decimal("100.00"), paid_date=TEST_DATE)

    with pytest.raises(InvalidStatusTransition):
        transition_income_status(income, target_status, paid_amount=Decimal("0"), paid_date=TEST_DATE)


@pytest.mark.parametrize(
    ("paid_amount", "expected_status", "expected_paid_date"),
    [
        (Decimal("0"), "issued", None),
        (Decimal("40.00"), "partial", None),
        (Decimal("100.00"), "paid", TEST_DATE),
        (Decimal("120.00"), "paid", TEST_DATE),
    ],
)
def test_reconcile_income_payment_state_sets_status_from_amount(paid_amount, expected_status, expected_paid_date):
    income = entity(status="issued", is_paid=False, paid_amount=Decimal("0"), paid_date=None)

    reconcile_income_payment_state(
        income,
        total_amount=Decimal("100.00"),
        paid_amount=paid_amount,
        paid_date=TEST_DATE if paid_amount >= Decimal("100.00") else None,
    )

    assert income.status == expected_status
    assert income.paid_amount == paid_amount
    assert income.paid_date == expected_paid_date
    assert income.is_paid is (expected_status == "paid")


def test_reconcile_income_payment_state_paid_requires_paid_date():
    income = entity(status="issued")

    with pytest.raises(InvalidStatusTransition, match="requires paid_date"):
        reconcile_income_payment_state(income, total_amount=Decimal("100.00"), paid_amount=Decimal("100.00"))


def test_reconcile_income_payment_state_cancelled_is_terminal():
    income = entity(status="cancelled")

    with pytest.raises(InvalidStatusTransition, match="terminal"):
        reconcile_income_payment_state(
            income,
            total_amount=Decimal("100.00"),
            paid_amount=Decimal("0"),
        )


def test_reconcile_income_payment_state_paid_to_partial_clears_paid_date():
    income = entity(status="paid", is_paid=True, paid_amount=Decimal("100.00"), paid_date=TEST_DATE)

    reconcile_income_payment_state(
        income,
        total_amount=Decimal("100.00"),
        paid_amount=Decimal("25.00"),
    )

    assert income.status == "partial"
    assert income.is_paid is False
    assert income.paid_amount == Decimal("25.00")
    assert income.paid_date is None


def test_cancel_income_allows_issued_and_rejects_paid():
    income = entity(status="issued", paid_amount=Decimal("0"), paid_date=None)
    cancel_income(income)
    assert income.status == "cancelled"
    assert income.paid_amount == Decimal("0")

    with pytest.raises(InvalidStatusTransition):
        cancel_income(entity(status="paid", paid_amount=Decimal("100.00"), paid_date=TEST_DATE))


def test_mark_expense_paid_requires_date_and_allows_same_when_requested():
    expense = entity(status="planned", paid_date=None)

    with pytest.raises(InvalidStatusTransition, match="requires paid_date"):
        mark_expense_paid(expense, paid_date=None)

    mark_expense_paid(expense, paid_date=TEST_DATE)
    assert expense.status == "paid"
    assert expense.paid_date == TEST_DATE

    mark_expense_paid(expense, paid_date=TEST_DATE, allow_same=True)
    assert expense.status == "paid"


def test_reopen_expense_for_unmatch_returns_paid_expense_to_planned():
    expense = entity(status="paid", paid_date=TEST_DATE)

    reopen_expense_for_unmatch(expense)

    assert expense.status == "planned"
    assert expense.paid_date is None


@pytest.mark.parametrize(
    "expense",
    [
        entity(status="planned", source="manual", reversal_of_id=None, reversed_expense_id=None),
        entity(status="reversed", source="manual", reversal_of_id=None, reversed_expense_id=None),
        entity(status="paid", source="manual", reversal_of_id=None, reversed_expense_id=10),
        entity(status="paid", source="manual", reversal_of_id=9, reversed_expense_id=None),
        entity(status="paid", source="cash_transfer", reversal_of_id=None, reversed_expense_id=None),
    ],
)
def test_ensure_expense_can_reverse_rejects_non_reversible_expenses(expense):
    with pytest.raises(InvalidStatusTransition):
        ensure_expense_can_reverse(expense)


def test_ensure_expense_can_reverse_accepts_paid_manual_expense():
    ensure_expense_can_reverse(entity(status="paid", source="manual", reversal_of_id=None, reversed_expense_id=None))


def test_mark_obligation_paid_status_requires_valid_transition():
    obligation = entity(status="unpaid", paid_date=None)

    mark_obligation_paid_status(obligation, paid_date=TEST_DATE)

    assert obligation.status == "paid"
    assert obligation.paid_date == TEST_DATE

    with pytest.raises(InvalidStatusTransition):
        mark_obligation_paid_status(obligation, paid_date=TEST_DATE)


@pytest.mark.parametrize(
    ("deadline", "today", "expected"),
    [
        (date(2026, 7, 1), TEST_DATE, "overdue"),
        (date(2026, 7, 6), TEST_DATE, "unpaid"),
        (date(2026, 7, 7), TEST_DATE, "unpaid"),
    ],
)
def test_refresh_obligation_due_status_uses_fixed_today(deadline, today, expected):
    obligation = entity(status="unpaid", deadline=deadline, paid_date=None)

    assert refresh_obligation_due_status(obligation, today=today) == expected
    assert obligation.status == expected
    assert obligation.paid_date is None


def test_refresh_obligation_due_status_keeps_paid_obligation_unchanged():
    obligation = entity(status="paid", deadline=date(2026, 7, 1), paid_date=TEST_DATE)

    assert refresh_obligation_due_status(obligation, today=TEST_DATE) == "paid"
    assert obligation.paid_date == TEST_DATE


@pytest.mark.parametrize(
    ("deadline", "expected"),
    [
        (date(2026, 7, 1), "overdue"),
        (date(2026, 7, 7), "unpaid"),
    ],
)
def test_restore_obligation_after_payment_reset_reopens_paid_obligation(deadline, expected):
    obligation = entity(status="paid", deadline=deadline, paid_date=TEST_DATE)

    assert restore_obligation_after_payment_reset(obligation, today=TEST_DATE) == expected
    assert obligation.status == expected
    assert obligation.paid_date is None


def test_restore_obligation_after_payment_reset_rejects_non_paid_obligation():
    with pytest.raises(InvalidStatusTransition, match="only paid"):
        restore_obligation_after_payment_reset(entity(status="unpaid", deadline=TEST_DATE), today=TEST_DATE)


@pytest.mark.parametrize(
    ("settled_amount", "expected_status"),
    [
        (Decimal("0"), "unpaid"),
        (Decimal("40.00"), "partial"),
        (Decimal("100.00"), "paid"),
        (Decimal("120.00"), "paid"),
    ],
)
def test_reconcile_incoming_invoice_status_sets_status_from_settled_amount(settled_amount, expected_status):
    invoice = entity(status="unpaid", amount=Decimal("100.00"), settled_amount=settled_amount)

    reconcile_incoming_invoice_status(invoice)

    assert invoice.status == expected_status


def test_reconcile_incoming_invoice_status_treats_advance_link_as_paid():
    invoice = entity(status="cancelled", amount=Decimal("100.00"), settled_amount=Decimal("0"), advance_invoice_id=5)

    reconcile_incoming_invoice_status(invoice)

    assert invoice.status == "paid"


def test_reconcile_incoming_invoice_status_rejects_cancelled_invoice():
    invoice = entity(status="cancelled", amount=Decimal("100.00"), settled_amount=Decimal("0"))

    with pytest.raises(InvalidStatusTransition, match="cancelled status is terminal"):
        reconcile_incoming_invoice_status(invoice)


def test_cancel_incoming_invoice_allows_unpaid_and_rejects_paid():
    invoice = entity(status="unpaid")
    cancel_incoming_invoice(invoice)
    assert invoice.status == "cancelled"

    with pytest.raises(InvalidStatusTransition):
        cancel_incoming_invoice(entity(status="paid"))
