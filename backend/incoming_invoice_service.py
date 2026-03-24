"""Сервис входящих фактур: создание, закрытие (банк/наличка/взаимозачёт), баланс контрагентов."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.decimal_utils import ZERO_DECIMAL, to_decimal
from backend.models import (
    BankTransaction,
    CashEntry,
    Client,
    EfakturaImportRecord,
    Expense,
    Income,
    IncomingInvoice,
    IncomingInvoiceSettlement,
    Project,
)
from backend.state_machine import (
    InvalidStatusTransition,
    initialize_expense_status,
    initialize_incoming_invoice_status,
    mark_expense_paid,
    reconcile_income_payment_state,
    reconcile_incoming_invoice_status,
    reopen_expense_for_unmatch,
)

INCOMING_INVOICE_SOURCE = "incoming_invoice"


async def _get_unassigned_project_id(db: AsyncSession) -> int | None:
    result = await db.execute(select(Project).where(Project.code == "INT-UNASSIGNED"))
    project = result.scalar_one_or_none()
    return project.id if project else None


async def create_incoming_invoice(
    db: AsyncSession,
    *,
    invoice_number: str,
    invoice_date: date,
    client_id: int | None,
    counterparty_name: str,
    project_id: int | None,
    amount: Decimal,
    currency: str = "RSD",
    description: str | None = None,
    note: str | None = None,
    source: str = "manual",
    efaktura_record_id: int | None = None,
    created_by: int | None = None,
) -> IncomingInvoice:
    resolved_project_id = project_id or await _get_unassigned_project_id(db)

    expense = Expense(
        date=invoice_date,
        description=f"Вх.ф. {invoice_number}: {counterparty_name}" + (f" — {description}" if description else ""),
        amount=to_decimal(amount),
        currency=currency,
        category=None,
        is_tax_related=False,
        source=INCOMING_INVOICE_SOURCE,
        project_id=resolved_project_id,
        note=note,
        created_by=created_by,
    )
    initialize_expense_status(expense, "planned")
    db.add(expense)
    await db.flush()

    invoice = IncomingInvoice(
        invoice_number=invoice_number,
        date=invoice_date,
        client_id=client_id,
        counterparty_name=counterparty_name,
        project_id=resolved_project_id,
        amount=to_decimal(amount),
        currency=currency,
        description=description,
        note=note,
        source=source,
        efaktura_record_id=efaktura_record_id,
        expense_id=expense.id,
        created_by=created_by,
    )
    initialize_incoming_invoice_status(invoice, "unpaid")
    db.add(invoice)
    await db.flush()
    return invoice


async def update_incoming_invoice(
    db: AsyncSession,
    invoice: IncomingInvoice,
    **fields,
) -> IncomingInvoice:
    if invoice.status in {"paid", "cancelled"}:
        raise InvalidStatusTransition(
            f"IncomingInvoice: cannot edit invoice in status '{invoice.status}'."
        )
    for key, value in fields.items():
        if value is not None:
            setattr(invoice, key, value)
    if invoice.expense_id:
        expense = await db.get(Expense, invoice.expense_id)
        if expense and expense.status == "planned":
            expense.description = (
                f"Вх.ф. {invoice.invoice_number}: {invoice.counterparty_name}"
                + (f" — {invoice.description}" if invoice.description else "")
            )
            expense.amount = to_decimal(invoice.amount)
            expense.date = invoice.date
            if "project_id" in fields:
                expense.project_id = invoice.project_id
    return invoice


def _recalc_settled(invoice: IncomingInvoice, settlements: list[IncomingInvoiceSettlement]) -> None:
    total = sum((to_decimal(s.amount) for s in settlements), ZERO_DECIMAL)
    invoice.settled_amount = total
    reconcile_incoming_invoice_status(invoice)


async def _load_settlements(db: AsyncSession, invoice_id: int) -> list[IncomingInvoiceSettlement]:
    result = await db.execute(
        select(IncomingInvoiceSettlement).where(
            IncomingInvoiceSettlement.incoming_invoice_id == invoice_id
        )
    )
    return list(result.scalars().all())


async def _sync_expense_status(db: AsyncSession, invoice: IncomingInvoice) -> None:
    """Синхронизировать статус linked Expense с IncomingInvoice."""
    if not invoice.expense_id:
        return
    expense = await db.get(Expense, invoice.expense_id)
    if not expense:
        return
    if invoice.status == "paid" and expense.status == "planned":
        mark_expense_paid(expense, paid_date=invoice.date, allow_same=True)
    elif invoice.status in {"unpaid", "partial"} and expense.status == "paid":
        reopen_expense_for_unmatch(expense)


async def attach_existing_expense(
    db: AsyncSession,
    invoice: IncomingInvoice,
    expense_id: int,
) -> IncomingInvoice:
    if invoice.status in {"paid", "cancelled"}:
        raise InvalidStatusTransition(
            f"IncomingInvoice: cannot attach expense in status '{invoice.status}'."
        )

    settlements = await _load_settlements(db, invoice.id)
    if settlements:
        raise ValueError("Cannot attach an expense after settlements already exist.")

    expense = await db.get(Expense, expense_id)
    if not expense:
        raise ValueError("Expense not found.")
    if expense.status != "paid":
        raise ValueError("Only paid expenses can be attached.")
    if getattr(expense, "reversal_of_id", None) or getattr(expense, "reversed_expense_id", None):
        raise ValueError("Reversed expenses cannot be attached.")

    linked_invoice_result = await db.execute(
        select(IncomingInvoice.id)
        .where(IncomingInvoice.expense_id == expense.id, IncomingInvoice.id != invoice.id)
        .limit(1)
    )
    if linked_invoice_result.scalar_one_or_none() is not None:
        raise ValueError("Expense is already linked to another incoming invoice.")

    expense_amount = abs(to_decimal(expense.amount or ZERO_DECIMAL))
    invoice_amount = abs(to_decimal(invoice.amount or ZERO_DECIMAL))
    if expense_amount != invoice_amount:
        raise ValueError("Expense amount must match the incoming invoice amount.")

    previous_expense = await db.get(Expense, invoice.expense_id) if invoice.expense_id else None
    invoice.expense_id = expense.id

    unassigned_project_id = await _get_unassigned_project_id(db)
    if expense.project_id and invoice.project_id in {None, unassigned_project_id}:
        invoice.project_id = expense.project_id

    invoice.settled_amount = to_decimal(invoice.amount or ZERO_DECIMAL)
    reconcile_incoming_invoice_status(invoice)

    if invoice.efaktura_record_id:
        import_record = await db.get(EfakturaImportRecord, invoice.efaktura_record_id)
        if import_record and import_record.imported_as == "expense":
            import_record.imported_record_id = expense.id

    if (
        previous_expense
        and previous_expense.id != expense.id
        and previous_expense.source == INCOMING_INVOICE_SOURCE
        and previous_expense.status == "planned"
    ):
        linked_bank_result = await db.execute(
            select(BankTransaction.id)
            .where(
                BankTransaction.matched_type == "expense",
                BankTransaction.matched_id == previous_expense.id,
            )
            .limit(1)
        )
        linked_cash_result = await db.execute(
            select(CashEntry.id).where(CashEntry.expense_id == previous_expense.id).limit(1)
        )
        if (
            linked_bank_result.scalar_one_or_none() is None
            and linked_cash_result.scalar_one_or_none() is None
        ):
            await db.delete(previous_expense)

    return invoice


async def settle_via_bank(
    db: AsyncSession,
    invoice: IncomingInvoice,
    bank_transaction_id: int,
    amount: Decimal,
    settlement_date: date,
    *,
    note: str | None = None,
    created_by: int | None = None,
) -> IncomingInvoiceSettlement:
    if invoice.status in {"paid", "cancelled"}:
        raise InvalidStatusTransition(
            f"IncomingInvoice: cannot settle invoice in status '{invoice.status}'."
        )
    tx = await db.get(BankTransaction, bank_transaction_id)
    if not tx:
        raise ValueError("BankTransaction not found.")
    if tx.status == "matched":
        raise ValueError("BankTransaction is already matched.")
    if tx.direction != "out":
        raise ValueError("Only outgoing bank transactions can settle incoming invoices.")

    remaining = invoice.remaining_amount
    settle_amount = to_decimal(amount)
    if settle_amount > remaining:
        raise ValueError(f"Settlement amount {settle_amount} exceeds remaining {remaining}.")

    settlement = IncomingInvoiceSettlement(
        incoming_invoice_id=invoice.id,
        settlement_type="bank",
        amount=settle_amount,
        date=settlement_date,
        note=note,
        bank_transaction_id=tx.id,
        created_by=created_by,
    )
    db.add(settlement)

    tx.status = "matched"
    tx.matched_type = "expense"
    tx.matched_id = invoice.expense_id

    if invoice.expense_id:
        expense = await db.get(Expense, invoice.expense_id)
        if expense and expense.status == "planned":
            expense.bank_reference = tx.bank_reference

    await db.flush()
    all_settlements = await _load_settlements(db, invoice.id)
    _recalc_settled(invoice, all_settlements)
    await _sync_expense_status(db, invoice)
    return settlement


async def settle_via_cash(
    db: AsyncSession,
    invoice: IncomingInvoice,
    amount: Decimal,
    settlement_date: date,
    *,
    note: str | None = None,
    created_by: int | None = None,
) -> IncomingInvoiceSettlement:
    if invoice.status in {"paid", "cancelled"}:
        raise InvalidStatusTransition(
            f"IncomingInvoice: cannot settle invoice in status '{invoice.status}'."
        )

    remaining = invoice.remaining_amount
    settle_amount = to_decimal(amount)
    if settle_amount > remaining:
        raise ValueError(f"Settlement amount {settle_amount} exceeds remaining {remaining}.")

    cash_entry = CashEntry(
        date=settlement_date,
        direction="out",
        amount=settle_amount,
        currency=invoice.currency,
        description=f"Оплата вх.ф. {invoice.invoice_number}: {invoice.counterparty_name}",
        entry_type="payment",
        note=note,
        created_by=created_by,
    )
    db.add(cash_entry)
    await db.flush()

    settlement = IncomingInvoiceSettlement(
        incoming_invoice_id=invoice.id,
        settlement_type="cash",
        amount=settle_amount,
        date=settlement_date,
        note=note,
        cash_entry_id=cash_entry.id,
        created_by=created_by,
    )
    db.add(settlement)
    await db.flush()

    all_settlements = await _load_settlements(db, invoice.id)
    _recalc_settled(invoice, all_settlements)
    await _sync_expense_status(db, invoice)
    return settlement


async def settle_via_offset(
    db: AsyncSession,
    invoice: IncomingInvoice,
    income_id: int,
    amount: Decimal,
    settlement_date: date,
    *,
    note: str | None = None,
    created_by: int | None = None,
) -> IncomingInvoiceSettlement:
    if invoice.status in {"paid", "cancelled"}:
        raise InvalidStatusTransition(
            f"IncomingInvoice: cannot settle invoice in status '{invoice.status}'."
        )

    income = await db.get(Income, income_id)
    if not income:
        raise ValueError("Income not found.")
    if income.status == "cancelled":
        raise ValueError("Cannot offset against cancelled income.")

    if not invoice.client_id:
        raise ValueError("Offset requires incoming invoice client_id to be set.")
    if not income.client_id:
        raise ValueError("Offset requires income client_id to be set.")
    if invoice.client_id != income.client_id:
        raise ValueError("Offset requires the same counterparty (invoice.client_id must equal income.client_id).")

    inv_remaining = invoice.remaining_amount
    inc_remaining = to_decimal(income.amount_rsd or ZERO_DECIMAL) - to_decimal(income.paid_amount or ZERO_DECIMAL)
    settle_amount = min(to_decimal(amount), inv_remaining, inc_remaining)
    if settle_amount <= ZERO_DECIMAL:
        raise ValueError("No remaining balance to offset.")

    settlement = IncomingInvoiceSettlement(
        incoming_invoice_id=invoice.id,
        settlement_type="offset",
        amount=settle_amount,
        date=settlement_date,
        note=note,
        income_id=income.id,
        created_by=created_by,
    )
    db.add(settlement)
    await db.flush()

    new_paid_amount = to_decimal(income.paid_amount or ZERO_DECIMAL) + settle_amount
    reconcile_income_payment_state(
        income,
        total_amount=to_decimal(income.amount_rsd or ZERO_DECIMAL),
        paid_amount=new_paid_amount,
        paid_date=settlement_date if new_paid_amount >= to_decimal(income.amount_rsd or ZERO_DECIMAL) else None,
    )

    all_settlements = await _load_settlements(db, invoice.id)
    _recalc_settled(invoice, all_settlements)
    await _sync_expense_status(db, invoice)
    return settlement


async def reverse_settlement(
    db: AsyncSession,
    settlement_id: int,
) -> IncomingInvoice:
    settlement = await db.get(IncomingInvoiceSettlement, settlement_id)
    if not settlement:
        raise ValueError("Settlement not found.")

    invoice = await db.get(IncomingInvoice, settlement.incoming_invoice_id)
    if not invoice:
        raise ValueError("IncomingInvoice not found.")

    if settlement.settlement_type == "bank" and settlement.bank_transaction_id:
        tx = await db.get(BankTransaction, settlement.bank_transaction_id)
        if tx and tx.status == "matched":
            tx.status = "unmatched"
            tx.matched_type = None
            tx.matched_id = None

    elif settlement.settlement_type == "cash" and settlement.cash_entry_id:
        cash_entry = await db.get(CashEntry, settlement.cash_entry_id)
        if cash_entry:
            await db.delete(cash_entry)

    elif settlement.settlement_type == "offset" and settlement.income_id:
        income = await db.get(Income, settlement.income_id)
        if income and income.status != "cancelled":
            new_paid_amount = to_decimal(income.paid_amount or ZERO_DECIMAL) - to_decimal(settlement.amount)
            if new_paid_amount < ZERO_DECIMAL:
                new_paid_amount = ZERO_DECIMAL
            reconcile_income_payment_state(
                income,
                total_amount=to_decimal(income.amount_rsd or ZERO_DECIMAL),
                paid_amount=new_paid_amount,
                paid_date=None,
            )

    await db.delete(settlement)
    await db.flush()

    all_settlements = await _load_settlements(db, invoice.id)
    _recalc_settled(invoice, all_settlements)
    await _sync_expense_status(db, invoice)
    return invoice


async def get_counterparty_balances(db: AsyncSession) -> list[dict]:
    receivables_q = (
        select(
            Income.client_id,
            func.coalesce(Income.client_name, "").label("client_name_fallback"),
            func.sum(Income.amount_rsd - Income.paid_amount).label("receivable"),
        )
        .where(Income.status.in_(["issued", "partial"]))
        .group_by(Income.client_id, Income.client_name)
    )
    receivables_result = await db.execute(receivables_q)
    receivables_rows = receivables_result.all()

    payables_q = (
        select(
            IncomingInvoice.client_id,
            IncomingInvoice.counterparty_name,
            func.sum(IncomingInvoice.amount - IncomingInvoice.settled_amount).label("payable"),
        )
        .where(IncomingInvoice.status.in_(["unpaid", "partial"]))
        .group_by(IncomingInvoice.client_id, IncomingInvoice.counterparty_name)
    )
    payables_result = await db.execute(payables_q)
    payables_rows = payables_result.all()

    client_ids = set()
    for row in receivables_rows:
        if row.client_id:
            client_ids.add(row.client_id)
    for row in payables_rows:
        if row.client_id:
            client_ids.add(row.client_id)

    client_names: dict[int, str] = {}
    if client_ids:
        clients_result = await db.execute(
            select(Client.id, Client.name).where(Client.id.in_(client_ids))
        )
        for cid, cname in clients_result.all():
            client_names[cid] = cname

    balances: dict[int | str, dict] = {}

    for row in receivables_rows:
        key = row.client_id or f"_unknown_{row.client_name_fallback}"
        name = client_names.get(row.client_id, row.client_name_fallback) if row.client_id else row.client_name_fallback
        entry = balances.setdefault(key, {
            "client_id": row.client_id,
            "client_name": name or "—",
            "receivables": ZERO_DECIMAL,
            "payables": ZERO_DECIMAL,
        })
        entry["receivables"] += to_decimal(row.receivable or ZERO_DECIMAL)

    for row in payables_rows:
        key = row.client_id or f"_unknown_{row.counterparty_name}"
        name = client_names.get(row.client_id, row.counterparty_name) if row.client_id else row.counterparty_name
        entry = balances.setdefault(key, {
            "client_id": row.client_id,
            "client_name": name or "—",
            "receivables": ZERO_DECIMAL,
            "payables": ZERO_DECIMAL,
        })
        entry["payables"] += to_decimal(row.payable or ZERO_DECIMAL)

    result = []
    for entry in balances.values():
        entry["net_balance"] = entry["receivables"] - entry["payables"]
        result.append(entry)

    result.sort(key=lambda x: abs(x["net_balance"]), reverse=True)
    return result
