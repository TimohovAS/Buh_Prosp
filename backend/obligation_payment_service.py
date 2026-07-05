"""Логика оплаты и отмены оплаты обязательных платежей."""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.decimal_utils import ZERO_DECIMAL, to_decimal

from backend.models import BankTransaction, Expense, MonthlyObligation, PaymentType
from backend.services import create_expense_reversal
from backend.state_machine import (
    initialize_expense_status,
    mark_expense_paid,
    mark_obligation_paid_status,
    restore_obligation_after_payment_reset,
)


async def _get_payment_type_name(db: AsyncSession, obligation: MonthlyObligation) -> str:
    payment_type = await db.get(PaymentType, obligation.payment_type_id) if obligation.payment_type_id else None
    return payment_type.name_sr if payment_type else "Плаћање"


def _build_payment_reference(
    payment_reference: str | None,
    bank_transaction: BankTransaction | None,
) -> str | None:
    return payment_reference or getattr(bank_transaction, "bank_reference", None) or None


async def mark_obligation_paid(
    db: AsyncSession,
    obligation: MonthlyObligation,
    paid_date: date,
    *,
    payment_reference: str | None = None,
    created_by: int | None = None,
    payment_method: str = "manual",
    bank_transaction: BankTransaction | None = None,
) -> Expense:
    """Отметить обязательство как оплаченное и синхронно создать/обновить расход."""
    payment_type_name = await _get_payment_type_name(db, obligation)
    description = f"{payment_type_name} {obligation.month:02d}/{obligation.year}"
    resolved_reference = _build_payment_reference(payment_reference, bank_transaction)

    expense = await db.get(Expense, obligation.expense_id) if obligation.expense_id else None
    if expense and (getattr(expense, "status", None) == "reversed" or getattr(expense, "reversal_of_id", None)):
        expense = None

    if expense is None:
        expense = Expense(
            date=paid_date,
            description=description,
            amount=to_decimal(obligation.amount or ZERO_DECIMAL),
            currency="RSD",
            category="tax",
            note=resolved_reference,
            source="obligation",
            is_tax_related=True,
            bank_reference=getattr(bank_transaction, "bank_reference", None),
            created_by=created_by,
        )
        initialize_expense_status(expense, "paid", paid_date=paid_date)
        db.add(expense)
        await db.flush()
    else:
        expense.date = paid_date
        expense.description = description
        expense.amount = to_decimal(obligation.amount or ZERO_DECIMAL)
        expense.currency = "RSD"
        expense.category = "tax"
        expense.note = resolved_reference
        mark_expense_paid(expense, paid_date=paid_date, allow_same=True)
        expense.source = "obligation"
        expense.is_tax_related = True
        if bank_transaction and bank_transaction.bank_reference:
            expense.bank_reference = bank_transaction.bank_reference

    mark_obligation_paid_status(obligation, paid_date=paid_date)
    obligation.payment_reference = resolved_reference
    obligation.payment_method = payment_method
    obligation.expense_id = expense.id

    if bank_transaction is not None:
        bank_transaction.status = "matched"
        bank_transaction.matched_type = "obligation"
        bank_transaction.matched_id = obligation.id

    await db.flush()
    return expense


async def reset_obligation_payment(
    db: AsyncSession,
    obligation: MonthlyObligation,
    *,
    created_by: Optional[int] = None,
) -> None:
    """Снять оплату с обязательства и сторнировать связанный расход."""
    bank_tx_result = await db.execute(
        select(BankTransaction).where(
            BankTransaction.matched_type == "obligation",
            BankTransaction.matched_id == obligation.id,
        )
    )
    for bank_tx in bank_tx_result.scalars().all():
        bank_tx.status = "unmatched"
        bank_tx.matched_type = None
        bank_tx.matched_id = None

    if obligation.expense_id:
        expense = await db.get(Expense, obligation.expense_id)
        if expense:
            expense_status = getattr(expense, "status", None)
            if (
                expense_status == "paid"
                and not getattr(expense, "reversed_expense_id", None)
                and not getattr(expense, "reversal_of_id", None)
            ):
                await create_expense_reversal(
                    db,
                    expense,
                    reverse_date=obligation.paid_date,
                    source="obligation",
                    created_by=created_by,
                )
            elif expense_status == "planned" and getattr(expense, "source", None) == "obligation":
                await db.delete(expense)
        obligation.expense_id = None

    restore_obligation_after_payment_reset(obligation, today=date.today())
    obligation.payment_reference = None
    obligation.payment_method = "manual"
    await db.flush()
