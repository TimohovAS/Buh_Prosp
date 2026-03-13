"""Централизованные правила переходов статусов для активного runtime."""
from __future__ import annotations

from datetime import date
from typing import Any


class InvalidStatusTransition(ValueError):
    """Недопустимый переход статуса или нарушение инвариантов."""


INCOME_STATUSES = {"issued", "partial", "paid", "cancelled"}
EXPENSE_STATUSES = {"planned", "paid", "reversed"}
OBLIGATION_STATUSES = {"unpaid", "overdue", "paid", "reversed"}
PROJECT_STATUSES = {"lead", "active", "completed", "archived"}

INCOME_TRANSITIONS = {
    "issued": {"partial", "paid", "cancelled"},
    "partial": {"paid", "cancelled"},
    "paid": set(),
    "cancelled": set(),
}

EXPENSE_TRANSITIONS = {
    "planned": {"paid"},
    "paid": {"reversed"},
    "reversed": set(),
}

OBLIGATION_TRANSITIONS = {
    "unpaid": {"paid", "overdue"},
    "overdue": {"paid"},
    "paid": {"reversed"},
    "reversed": set(),
}

PROJECT_TRANSITIONS = {
    "lead": {"active", "archived"},
    "active": {"completed", "archived"},
    "completed": {"archived"},
    "archived": set(),
}


def _ensure_known_status(entity_name: str, status: str | None, known_statuses: set[str]) -> str:
    normalized = (status or "").strip()
    if normalized not in known_statuses:
        allowed = ", ".join(sorted(known_statuses))
        raise InvalidStatusTransition(f"{entity_name}: unknown status '{status}'. Allowed: {allowed}.")
    return normalized


def _ensure_transition(
    entity_name: str,
    current_status: str | None,
    target_status: str | None,
    *,
    known_statuses: set[str],
    transitions: dict[str, set[str]],
    allow_same: bool = True,
    extra_transitions: dict[str, set[str]] | None = None,
) -> tuple[str, str]:
    current = _ensure_known_status(entity_name, current_status, known_statuses)
    target = _ensure_known_status(entity_name, target_status, known_statuses)
    if current == target:
        if allow_same:
            return current, target
        raise InvalidStatusTransition(f"{entity_name}: status is already '{target}'.")

    allowed_targets = set(transitions.get(current, set()))
    if extra_transitions:
        allowed_targets.update(extra_transitions.get(current, set()))
    if target not in allowed_targets:
        allowed = ", ".join(sorted(allowed_targets)) or "terminal"
        raise InvalidStatusTransition(
            f"{entity_name}: transition '{current}' -> '{target}' is not allowed. Allowed: {allowed}."
        )
    return current, target


def _require_date(entity_name: str, target_status: str, paid_date: date | None) -> None:
    if target_status in {"paid", "reversed"} and paid_date is None:
        raise InvalidStatusTransition(f"{entity_name}: status '{target_status}' requires paid_date.")


def _set_income_fields(income: Any, target_status: str, *, paid_date: date | None, paid_amount: float) -> None:
    if target_status == "paid":
        _require_date("Income", target_status, paid_date)
    income.status = target_status
    income.paid_amount = float(paid_amount or 0)
    if target_status == "paid":
        income.is_paid = True
        income.paid_date = paid_date
        return
    income.is_paid = False
    income.paid_date = None


def initialize_income_status(
    income: Any,
    target_status: str,
    *,
    paid_date: date | None = None,
    paid_amount: float | None = None,
) -> None:
    target = _ensure_known_status("Income", target_status, INCOME_STATUSES)
    if target == "paid":
        _require_date("Income", target, paid_date)
        resolved_paid_amount = float(paid_amount if paid_amount is not None else getattr(income, "amount_rsd", 0) or 0)
    else:
        resolved_paid_amount = float(paid_amount or 0)
    _set_income_fields(income, target, paid_date=paid_date, paid_amount=resolved_paid_amount)


def transition_income_status(
    income: Any,
    target_status: str,
    *,
    paid_date: date | None = None,
    paid_amount: float | None = None,
    allow_same: bool = True,
) -> None:
    _ensure_transition(
        "Income",
        getattr(income, "status", None),
        target_status,
        known_statuses=INCOME_STATUSES,
        transitions=INCOME_TRANSITIONS,
        allow_same=allow_same,
    )
    resolved_paid_amount = float(paid_amount if paid_amount is not None else getattr(income, "paid_amount", 0) or 0)
    _set_income_fields(income, target_status, paid_date=paid_date, paid_amount=resolved_paid_amount)


def reconcile_income_payment_state(
    income: Any,
    *,
    total_amount: float,
    paid_amount: float,
    paid_date: date | None = None,
) -> None:
    current = _ensure_known_status("Income", getattr(income, "status", None), INCOME_STATUSES)
    if current == "cancelled":
        raise InvalidStatusTransition("Income: cancelled status is terminal and cannot be reconciled.")

    resolved_paid_amount = float(paid_amount or 0)
    resolved_total_amount = float(total_amount or 0)
    if resolved_paid_amount >= resolved_total_amount and resolved_paid_amount > 0:
        _require_date("Income", "paid", paid_date)
        _set_income_fields(income, "paid", paid_date=paid_date, paid_amount=resolved_paid_amount)
    elif resolved_paid_amount > 0:
        _set_income_fields(income, "partial", paid_date=None, paid_amount=resolved_paid_amount)
    else:
        _set_income_fields(income, "issued", paid_date=None, paid_amount=0.0)


def cancel_income(income: Any) -> None:
    transition_income_status(income, "cancelled", paid_amount=0.0, allow_same=False)


def initialize_expense_status(expense: Any, target_status: str, *, paid_date: date | None = None) -> None:
    target = _ensure_known_status("Expense", target_status, EXPENSE_STATUSES)
    if target in {"paid", "reversed"}:
        _require_date("Expense", target, paid_date)
    expense.status = target
    expense.paid_date = paid_date if target in {"paid", "reversed"} else None


def mark_expense_paid(expense: Any, *, paid_date: date | None, allow_same: bool = True) -> None:
    _ensure_transition(
        "Expense",
        getattr(expense, "status", None),
        "paid",
        known_statuses=EXPENSE_STATUSES,
        transitions=EXPENSE_TRANSITIONS,
        allow_same=allow_same,
    )
    _require_date("Expense", "paid", paid_date)
    expense.status = "paid"
    expense.paid_date = paid_date


def reopen_expense_for_unmatch(expense: Any) -> None:
    _ensure_transition(
        "Expense",
        getattr(expense, "status", None),
        "planned",
        known_statuses=EXPENSE_STATUSES,
        transitions=EXPENSE_TRANSITIONS,
        allow_same=False,
        extra_transitions={"paid": {"planned"}},
    )
    expense.status = "planned"
    expense.paid_date = None


def ensure_expense_can_reverse(expense: Any) -> None:
    status = _ensure_known_status("Expense", getattr(expense, "status", None), EXPENSE_STATUSES)
    if getattr(expense, "reversal_of_id", None):
        raise InvalidStatusTransition("Expense: reversal entry cannot be reversed again.")
    if getattr(expense, "reversed_expense_id", None):
        raise InvalidStatusTransition("Expense: expense is already reversed.")
    _ensure_transition(
        "Expense",
        status,
        "reversed",
        known_statuses=EXPENSE_STATUSES,
        transitions=EXPENSE_TRANSITIONS,
        allow_same=False,
    )


def initialize_obligation_status(obligation: Any, target_status: str, *, paid_date: date | None = None) -> None:
    target = _ensure_known_status("MonthlyObligation", target_status, OBLIGATION_STATUSES)
    if target == "paid":
        _require_date("MonthlyObligation", target, paid_date)
    obligation.status = target
    obligation.paid_date = paid_date if target == "paid" else None


def mark_obligation_paid_status(obligation: Any, *, paid_date: date) -> None:
    _ensure_transition(
        "MonthlyObligation",
        getattr(obligation, "status", None),
        "paid",
        known_statuses=OBLIGATION_STATUSES,
        transitions=OBLIGATION_TRANSITIONS,
        allow_same=False,
    )
    _require_date("MonthlyObligation", "paid", paid_date)
    obligation.status = "paid"
    obligation.paid_date = paid_date


def refresh_obligation_due_status(obligation: Any, *, today: date | None = None) -> str:
    current = _ensure_known_status("MonthlyObligation", getattr(obligation, "status", None), OBLIGATION_STATUSES)
    if current in {"paid", "reversed"}:
        return current
    resolved_today = today or date.today()
    target = "overdue" if getattr(obligation, "deadline", None) and obligation.deadline < resolved_today else "unpaid"
    obligation.status = target
    obligation.paid_date = None
    return target


def restore_obligation_after_payment_reset(obligation: Any, *, today: date | None = None) -> str:
    current = _ensure_known_status("MonthlyObligation", getattr(obligation, "status", None), OBLIGATION_STATUSES)
    if current != "paid":
        raise InvalidStatusTransition("MonthlyObligation: only paid obligations can be reset via the payment-reset service.")
    resolved_today = today or date.today()
    target = "overdue" if getattr(obligation, "deadline", None) and obligation.deadline < resolved_today else "unpaid"
    obligation.status = target
    obligation.paid_date = None
    return target


def initialize_project_status(project: Any, target_status: str) -> None:
    target = _ensure_known_status("Project", target_status, PROJECT_STATUSES)
    project.status = target


def transition_project_status(
    project: Any,
    target_status: str,
    *,
    allow_same: bool = True,
    allow_system_reactivate: bool = False,
) -> None:
    extra_transitions = {"archived": {"active"}} if allow_system_reactivate else None
    _ensure_transition(
        "Project",
        getattr(project, "status", None),
        target_status,
        known_statuses=PROJECT_STATUSES,
        transitions=PROJECT_TRANSITIONS,
        allow_same=allow_same,
        extra_transitions=extra_transitions,
    )
    project.status = target_status
