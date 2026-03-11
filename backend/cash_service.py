from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import BankTransaction, CashEntry, Expense

CASH_CATEGORY = "cash"
CASH_TRANSFER_SOURCE = "cash_transfer"


def is_cash_transfer_expense(expense: Expense | None) -> bool:
    if not expense:
        return False
    return getattr(expense, "source", None) == CASH_TRANSFER_SOURCE


async def get_cash_balance(db: AsyncSession) -> float:
    total_in = await db.scalar(select(func.coalesce(func.sum(CashEntry.amount), 0)).where(CashEntry.direction == "in"))
    total_out = await db.scalar(select(func.coalesce(func.sum(CashEntry.amount), 0)).where(CashEntry.direction == "out"))
    return float(total_in or 0) - float(total_out or 0)


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

    expense = Expense(
        date=transaction.date,
        description=build_cash_transfer_description(transaction, description),
        amount=float(transaction.amount or 0),
        currency=transaction.currency or "RSD",
        category=CASH_CATEGORY,
        category_id=None,
        contract_id=contract_id,
        bank_reference=transaction.bank_reference,
        paid_date=transaction.date,
        status="paid",
        source=CASH_TRANSFER_SOURCE,
        note=note,
        project_id=project_id,
        created_by=created_by,
    )
    db.add(expense)
    await db.flush()

    entry = CashEntry(
        date=transaction.date,
        direction="in",
        amount=float(transaction.amount or 0),
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
    transaction.project_id = project_id

    return expense, entry


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

    amount = float(
        (entry.amount if entry is not None else None)
        or (expense.amount if expense is not None else None)
        or transaction.amount
        or 0
    )
    current_balance = await get_cash_balance(db)
    if amount > current_balance:
        raise ValueError("Cannot unmatch cash withdrawal because cash from it is already used")

    if entry is not None:
        await db.delete(entry)
    if expense is not None:
        await db.delete(expense)

    transaction.status = "unmatched"
    transaction.matched_type = None
    transaction.matched_id = None
