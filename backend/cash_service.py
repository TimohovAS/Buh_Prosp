from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.decimal_utils import ZERO_DECIMAL, money_abs, money_eq, to_decimal

from backend.models import BankTransaction, CashEntry, Expense, Project
from backend.state_machine import initialize_expense_status, initialize_project_status, transition_project_status

CASH_CATEGORY = "cash"
CASH_TRANSFER_SOURCE = "cash_transfer"
CASH_PROJECT_CODE = "INT-CASH"
CASH_PROJECT_NAME = "Наличка / Касса"


def is_cash_transfer_expense(expense: Expense | None) -> bool:
    if not expense:
        return False
    return getattr(expense, "source", None) == CASH_TRANSFER_SOURCE


async def get_cash_balance(db: AsyncSession):
    total_in = await db.scalar(select(func.coalesce(func.sum(CashEntry.amount), 0)).where(CashEntry.direction == "in"))
    total_out = await db.scalar(select(func.coalesce(func.sum(CashEntry.amount), 0)).where(CashEntry.direction == "out"))
    return to_decimal(total_in or ZERO_DECIMAL) - to_decimal(total_out or ZERO_DECIMAL)


async def get_or_create_cash_project_id(db: AsyncSession) -> int:
    result = await db.execute(select(Project).where(Project.code == CASH_PROJECT_CODE))
    project = result.scalar_one_or_none()
    if project:
        if not project.is_internal:
            project.is_internal = True
        if project.status == "archived":
            transition_project_status(project, "active", allow_same=False, allow_system_reactivate=True)
        if not project.name:
            project.name = CASH_PROJECT_NAME
        await db.flush()
        return int(project.id)

    project = Project(
        code=CASH_PROJECT_CODE,
        name=CASH_PROJECT_NAME,
        is_internal=True,
    )
    initialize_project_status(project, "active")
    db.add(project)
    await db.flush()
    return int(project.id)


def build_cash_transfer_description(
    transaction: BankTransaction,
    description: str | None = None,
) -> str:
    return (
        (description or "").strip()
        or (transaction.purpose or "").strip()
        or (transaction.counterparty_name or "").strip()
        or (transaction.bank_reference or "").strip()
        or f"Cash withdrawal from bank transaction #{transaction.id}"
    )[:500]


async def get_cash_entry_by_bank_transaction(db: AsyncSession, transaction_id: int) -> CashEntry | None:
    result = await db.execute(select(CashEntry).where(CashEntry.bank_transaction_id == transaction_id))
    return result.scalar_one_or_none()


async def get_cash_entry_by_expense(db: AsyncSession, expense_id: int) -> CashEntry | None:
    result = await db.execute(select(CashEntry).where(CashEntry.expense_id == expense_id))
    return result.scalar_one_or_none()


async def create_cash_transfer_from_transaction(
    db: AsyncSession,
    transaction: BankTransaction,
    *,
    project_id: int | None,
    contract_id: int | None,
    description: str | None,
    note: str | None,
    created_by: int | None,
) -> tuple[Expense, CashEntry]:
    if transaction.direction != "out":
        raise ValueError("Only outgoing bank transactions can be transferred to cash")
    if transaction.status not in {"unmatched", "ignored"}:
        raise ValueError("Transaction is already matched")

    existing_entry = await get_cash_entry_by_bank_transaction(db, transaction.id)
    if existing_entry:
        raise ValueError("This bank transaction is already added to cash")

    cash_project_id = await get_or_create_cash_project_id(db)
    transfer_amount = money_abs(transaction.amount or ZERO_DECIMAL)

    expense = Expense(
        date=transaction.date,
        description=build_cash_transfer_description(transaction, description),
        amount=transfer_amount,
        currency=transaction.currency or "RSD",
        category=CASH_CATEGORY,
        category_id=None,
        contract_id=None,
        bank_reference=transaction.bank_reference,
        source=CASH_TRANSFER_SOURCE,
        note=note,
        project_id=cash_project_id,
        created_by=created_by,
    )
    initialize_expense_status(expense, "paid", paid_date=transaction.date)
    db.add(expense)
    await db.flush()

    entry = CashEntry(
        date=transaction.date,
        direction="in",
        amount=transfer_amount,
        currency=transaction.currency or "RSD",
        description=expense.description,
        entry_type="withdrawal",
        note=note,
        bank_transaction_id=transaction.id,
        expense_id=expense.id,
        created_by=created_by,
    )
    db.add(entry)
    await db.flush()

    transaction.status = "matched"
    transaction.matched_type = "expense"
    transaction.matched_id = expense.id
    transaction.project_id = cash_project_id

    return expense, entry


async def create_cash_transfer_from_pending_entry(
    db: AsyncSession,
    transaction: BankTransaction,
    pending_entry: CashEntry,
    *,
    description: str | None,
    note: str | None,
    created_by: int | None,
) -> tuple[Expense, CashEntry]:
    if transaction.direction != "out":
        raise ValueError("Only outgoing bank transactions can be transferred to cash")
    if transaction.status not in {"unmatched", "ignored"}:
        raise ValueError("Transaction is already matched")
    if pending_entry.entry_type != "pending_withdrawal":
        raise ValueError("Only pending cash withdrawals can be linked to a bank transaction")
    if pending_entry.direction != "in" or pending_entry.bank_transaction_id or pending_entry.expense_id:
        raise ValueError("This pending cash withdrawal is already linked")

    existing_entry = await get_cash_entry_by_bank_transaction(db, transaction.id)
    if existing_entry:
        raise ValueError("This bank transaction is already added to cash")

    transfer_amount = money_abs(transaction.amount or ZERO_DECIMAL)
    if not money_eq(transfer_amount, pending_entry.amount or ZERO_DECIMAL):
        raise ValueError("Bank transaction amount must match the pending cash withdrawal")
    if (transaction.currency or "RSD") != (pending_entry.currency or "RSD"):
        raise ValueError("Bank transaction currency must match the pending cash withdrawal")

    cash_project_id = await get_or_create_cash_project_id(db)
    resolved_description = build_cash_transfer_description(transaction, description or pending_entry.description)
    resolved_note = note if note is not None else pending_entry.note

    expense = Expense(
        date=transaction.date,
        description=resolved_description,
        amount=transfer_amount,
        currency=transaction.currency or "RSD",
        category=CASH_CATEGORY,
        category_id=None,
        contract_id=None,
        bank_reference=transaction.bank_reference,
        source=CASH_TRANSFER_SOURCE,
        note=resolved_note,
        project_id=cash_project_id,
        created_by=created_by,
    )
    initialize_expense_status(expense, "paid", paid_date=transaction.date)
    db.add(expense)
    await db.flush()

    pending_entry.entry_type = "withdrawal"
    pending_entry.direction = "in"
    pending_entry.amount = transfer_amount
    pending_entry.currency = transaction.currency or "RSD"
    pending_entry.description = resolved_description
    pending_entry.note = resolved_note
    pending_entry.bank_transaction_id = transaction.id
    pending_entry.expense_id = expense.id

    transaction.status = "matched"
    transaction.matched_type = "expense"
    transaction.matched_id = expense.id
    transaction.project_id = cash_project_id

    await db.flush()
    return expense, pending_entry


async def revert_cash_transfer(
    db: AsyncSession,
    transaction: BankTransaction,
    *,
    expense: Expense | None = None,
    cash_entry: CashEntry | None = None,
) -> None:
    entry = cash_entry
    if entry is None:
        entry = await get_cash_entry_by_bank_transaction(db, transaction.id)
        if entry is None and expense is not None:
            entry = await get_cash_entry_by_expense(db, expense.id)

    if entry is not None:
        await db.delete(entry)
    if expense is not None:
        await db.delete(expense)

    transaction.status = "unmatched"
    transaction.matched_type = None
    transaction.matched_id = None

