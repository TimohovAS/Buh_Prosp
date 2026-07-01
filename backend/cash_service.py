from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.decimal_utils import ZERO_DECIMAL, money_abs, money_eq, to_decimal

from backend.models import BankTransaction, CashEntry, Expense, Project
from backend.state_machine import initialize_expense_status, initialize_project_status, transition_project_status

CASH_CATEGORY = "cash"
CASH_TRANSFER_SOURCE = "cash_transfer"
CASH_PROJECT_CODE = "INT-CASH"
AUTO_LINK_PENDING_WITHDRAWAL_DAYS = 14
_CASH_WITHDRAWAL_TEXT_MARKERS = ("atm", "bankomat", "gotovin", "cash", "isplata", "podiz")
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


def _pending_entry_matches_manual_cash_transfer(
    entry: CashEntry,
    transaction: BankTransaction,
    max_days: int = AUTO_LINK_PENDING_WITHDRAWAL_DAYS,
) -> bool:
    if entry.entry_type != "pending_withdrawal" or entry.direction != "in":
        return False
    if entry.bank_transaction_id or entry.expense_id:
        return False
    if transaction.direction != "out" or transaction.status not in {"unmatched", "ignored"}:
        return False
    if (entry.currency or "RSD") != (transaction.currency or "RSD"):
        return False
    if not money_eq(entry.amount or ZERO_DECIMAL, money_abs(transaction.amount or ZERO_DECIMAL)):
        return False
    if transaction.date < entry.date:
        return False
    return transaction.date <= entry.date + timedelta(days=max_days)


def _select_unambiguous_pending_withdrawal(candidates: list[CashEntry]) -> CashEntry | None:
    if len(candidates) != 1:
        return None
    return candidates[0]


async def _find_pending_withdrawal_for_manual_cash_transfer(
    db: AsyncSession,
    transaction: BankTransaction,
    max_days: int = AUTO_LINK_PENDING_WITHDRAWAL_DAYS,
) -> CashEntry | None:
    currency = transaction.currency or "RSD"
    currency_filter = CashEntry.currency == currency
    if currency == "RSD":
        currency_filter = or_(currency_filter, CashEntry.currency.is_(None))

    result = await db.execute(
        select(CashEntry)
        .where(
            CashEntry.entry_type == "pending_withdrawal",
            CashEntry.direction == "in",
            CashEntry.bank_transaction_id.is_(None),
            CashEntry.expense_id.is_(None),
            CashEntry.date >= transaction.date - timedelta(days=max_days),
            CashEntry.date <= transaction.date,
            CashEntry.amount == money_abs(transaction.amount or ZERO_DECIMAL),
            currency_filter,
        )
        .order_by(CashEntry.date.desc(), CashEntry.id.asc())
    )
    candidates = [
        entry
        for entry in result.scalars().all()
        if _pending_entry_matches_manual_cash_transfer(entry, transaction, max_days)
    ]
    return _select_unambiguous_pending_withdrawal(candidates)


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
    pending_entry = await _find_pending_withdrawal_for_manual_cash_transfer(db, transaction)
    resolved_note = note if note is not None else getattr(pending_entry, "note", None)

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
        note=resolved_note,
        project_id=cash_project_id,
        created_by=created_by,
    )
    initialize_expense_status(expense, "paid", paid_date=transaction.date)
    db.add(expense)
    await db.flush()

    if pending_entry:
        entry = pending_entry
        entry.direction = "in"
        entry.amount = transfer_amount
        entry.currency = transaction.currency or "RSD"
        entry.description = expense.description
        entry.entry_type = "withdrawal"
        entry.note = resolved_note
        entry.bank_transaction_id = transaction.id
        entry.expense_id = expense.id
    else:
        entry = CashEntry(
            date=transaction.date,
            direction="in",
            amount=transfer_amount,
            currency=transaction.currency or "RSD",
            description=expense.description,
            entry_type="withdrawal",
            note=resolved_note,
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


def _looks_like_cash_withdrawal_transaction(transaction: BankTransaction) -> bool:
    text = " ".join(
        str(value or "").lower()
        for value in (
            transaction.purpose,
            transaction.counterparty_name,
            transaction.bank_reference,
        )
    )
    return any(marker in text for marker in _CASH_WITHDRAWAL_TEXT_MARKERS)


def _pending_entry_matches_transaction(
    entry: CashEntry,
    transaction: BankTransaction,
    max_days: int,
) -> bool:
    if entry.entry_type != "pending_withdrawal" or entry.direction != "in":
        return False
    if entry.bank_transaction_id or entry.expense_id:
        return False
    if transaction.direction != "out" or transaction.status not in {"unmatched", "ignored"}:
        return False
    if not _looks_like_cash_withdrawal_transaction(transaction):
        return False
    if (entry.currency or "RSD") != (transaction.currency or "RSD"):
        return False
    if not money_eq(entry.amount or ZERO_DECIMAL, money_abs(transaction.amount or ZERO_DECIMAL)):
        return False
    if transaction.date < entry.date:
        return False
    return transaction.date <= entry.date + timedelta(days=max_days)


def _pending_entry_matches_matched_cash_expense_transaction(
    entry: CashEntry,
    transaction: BankTransaction,
    max_days: int,
) -> bool:
    if entry.entry_type != "pending_withdrawal" or entry.direction != "in":
        return False
    if entry.bank_transaction_id or entry.expense_id:
        return False
    if transaction.direction != "out" or transaction.status != "matched" or transaction.matched_type != "expense":
        return False
    if not _looks_like_cash_withdrawal_transaction(transaction):
        return False
    if (entry.currency or "RSD") != (transaction.currency or "RSD"):
        return False
    if not money_eq(entry.amount or ZERO_DECIMAL, money_abs(transaction.amount or ZERO_DECIMAL)):
        return False
    if transaction.date < entry.date:
        return False
    return transaction.date <= entry.date + timedelta(days=max_days)


async def _get_linkable_matched_cash_expense(
    db: AsyncSession,
    transaction: BankTransaction,
) -> Expense | None:
    if transaction.status != "matched" or transaction.matched_type != "expense" or not transaction.matched_id:
        return None
    if await get_cash_entry_by_bank_transaction(db, transaction.id):
        return None

    result = await db.execute(select(Expense).where(Expense.id == transaction.matched_id))
    expense = result.scalar_one_or_none()
    if not expense:
        return None
    if await get_cash_entry_by_expense(db, expense.id):
        return None
    if getattr(expense, "source", None) not in {"bank_import", CASH_TRANSFER_SOURCE}:
        return None

    cash_project_id = await get_or_create_cash_project_id(db)
    if (
        getattr(expense, "source", None) != CASH_TRANSFER_SOURCE
        and getattr(expense, "category", None) != CASH_CATEGORY
        and getattr(expense, "project_id", None) != cash_project_id
        and getattr(transaction, "project_id", None) != cash_project_id
    ):
        return None
    return expense


async def _link_pending_entry_to_matched_cash_expense(
    db: AsyncSession,
    transaction: BankTransaction,
    pending_entry: CashEntry,
    expense: Expense,
    *,
    note: str | None,
) -> CashEntry:
    transfer_amount = money_abs(transaction.amount or ZERO_DECIMAL)
    if not money_eq(transfer_amount, pending_entry.amount or ZERO_DECIMAL):
        raise ValueError("Bank transaction amount must match the pending cash withdrawal")
    if (transaction.currency or "RSD") != (pending_entry.currency or "RSD"):
        raise ValueError("Bank transaction currency must match the pending cash withdrawal")

    cash_project_id = await get_or_create_cash_project_id(db)
    resolved_description = build_cash_transfer_description(transaction, pending_entry.description)
    resolved_note = note if note is not None else pending_entry.note

    expense.date = transaction.date
    expense.description = resolved_description
    expense.amount = transfer_amount
    expense.currency = transaction.currency or "RSD"
    expense.category = CASH_CATEGORY
    expense.category_id = None
    expense.contract_id = None
    expense.bank_reference = transaction.bank_reference
    expense.paid_date = transaction.date
    expense.status = "paid"
    expense.is_tax_related = False
    expense.source = CASH_TRANSFER_SOURCE
    expense.note = resolved_note
    expense.project_id = cash_project_id

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
    return pending_entry


async def auto_link_pending_cash_withdrawals(
    db: AsyncSession,
    *,
    created_by: int | None = None,
    max_days: int = AUTO_LINK_PENDING_WITHDRAWAL_DAYS,
) -> int:
    pending_result = await db.execute(
        select(CashEntry)
        .where(
            CashEntry.entry_type == "pending_withdrawal",
            CashEntry.direction == "in",
            CashEntry.bank_transaction_id.is_(None),
            CashEntry.expense_id.is_(None),
        )
        .order_by(CashEntry.date.asc(), CashEntry.id.asc())
    )
    pending_entries = list(pending_result.scalars().all())
    if not pending_entries:
        return 0

    first_pending_date = min(entry.date for entry in pending_entries)
    last_pending_date = max(entry.date for entry in pending_entries)
    pending_amounts = {entry.amount for entry in pending_entries}
    pending_currencies = {entry.currency or "RSD" for entry in pending_entries}
    currency_filter = BankTransaction.currency.in_(pending_currencies)
    if "RSD" in pending_currencies:
        currency_filter = or_(currency_filter, BankTransaction.currency.is_(None))

    transactions_result = await db.execute(
        select(BankTransaction)
        .where(
            BankTransaction.direction == "out",
            BankTransaction.status.in_(["unmatched", "ignored"]),
            BankTransaction.date >= first_pending_date,
            BankTransaction.date <= last_pending_date + timedelta(days=max_days),
            currency_filter,
            func.abs(BankTransaction.amount).in_(pending_amounts),
        )
        .order_by(BankTransaction.date.asc(), BankTransaction.id.asc())
    )
    transactions = [
        transaction
        for transaction in transactions_result.scalars().all()
        if _looks_like_cash_withdrawal_transaction(transaction)
    ]

    linked_count = 0
    used_pending_ids: set[int] = set()
    for transaction in transactions:
        candidates = [
            entry
            for entry in pending_entries
            if int(entry.id) not in used_pending_ids
            and _pending_entry_matches_transaction(entry, transaction, max_days)
        ]
        entry = _select_unambiguous_pending_withdrawal(candidates)
        if not entry:
            continue

        try:
            await create_cash_transfer_from_pending_entry(
                db,
                transaction,
                entry,
                description=build_cash_transfer_description(transaction),
                note=entry.note,
                created_by=created_by,
            )
        except ValueError:
            continue
        used_pending_ids.add(int(entry.id))
        linked_count += 1

    remaining_pending_entries = [
        entry
        for entry in pending_entries
        if int(entry.id) not in used_pending_ids
    ]
    if not remaining_pending_entries:
        return linked_count

    matched_transactions_result = await db.execute(
        select(BankTransaction)
        .where(
            BankTransaction.direction == "out",
            BankTransaction.status == "matched",
            BankTransaction.matched_type == "expense",
            BankTransaction.matched_id.is_not(None),
            BankTransaction.date >= first_pending_date,
            BankTransaction.date <= last_pending_date + timedelta(days=max_days),
            currency_filter,
            func.abs(BankTransaction.amount).in_(pending_amounts),
        )
        .order_by(BankTransaction.date.asc(), BankTransaction.id.asc())
    )
    matched_transactions = [
        transaction
        for transaction in matched_transactions_result.scalars().all()
        if _looks_like_cash_withdrawal_transaction(transaction)
    ]
    for transaction in matched_transactions:
        expense = await _get_linkable_matched_cash_expense(db, transaction)
        if not expense:
            continue
        candidates = [
            entry
            for entry in remaining_pending_entries
            if int(entry.id) not in used_pending_ids
            and _pending_entry_matches_matched_cash_expense_transaction(entry, transaction, max_days)
        ]
        entry = _select_unambiguous_pending_withdrawal(candidates)
        if not entry:
            continue

        try:
            await _link_pending_entry_to_matched_cash_expense(
                db,
                transaction,
                entry,
                expense,
                note=entry.note,
            )
        except ValueError:
            continue
        used_pending_ids.add(int(entry.id))
        linked_count += 1

    return linked_count


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
