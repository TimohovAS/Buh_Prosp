from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.auth import get_current_user_required, require_edit_access
from backend.cash_service import create_cash_transfer_from_transaction
from backend.database import get_db
from backend.decimal_utils import ZERO_DECIMAL, to_decimal
from backend.models import BankTransaction, CashEntry, Contract, Expense, Project, TransactionCategory, User
from backend.state_machine import initialize_expense_status
from backend.schemas import (
    CashAdjustmentCreate,
    CashBankWithdrawalCandidate,
    CashEntryResponse,
    CashExpenseCreate,
    CashEntryUpdate,
    CashSummaryResponse,
    CashWithdrawalCreate,
)

router = APIRouter(prefix="/cash", tags=["cash"])


async def _get_unassigned_project_id(db: AsyncSession) -> int | None:
    result = await db.execute(select(Project).where(Project.code == "INT-UNASSIGNED"))
    project = result.scalar_one_or_none()
    return project.id if project else None


async def _get_project_or_404(db: AsyncSession, project_id: int) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    if project.status == "archived":
        raise HTTPException(400, "Cannot use archived project")
    return project


async def _get_contract_or_404(db: AsyncSession, contract_id: int) -> Contract:
    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(404, "Contract not found")
    return contract


async def _get_category_or_none(db: AsyncSession, category_id: int | None) -> TransactionCategory | None:
    if category_id is None:
        return None
    result = await db.execute(select(TransactionCategory).where(TransactionCategory.id == category_id))
    return result.scalar_one_or_none()


async def _resolve_category_expense_links(
    db: AsyncSession,
    category_id: int | None,
    project_id: int | None,
    contract_id: int | None,
) -> tuple[int | None, int | None, bool]:
    category = await _get_category_or_none(db, category_id)
    if not category:
        return project_id, contract_id, False

    resolved_project_id = category.default_project_id or project_id
    resolved_contract_id = contract_id
    is_tax_related = category.category_group == "tax"

    if category.default_project_id and resolved_contract_id is not None:
        contract = await _get_contract_or_404(db, resolved_contract_id)
        if contract.project_id is not None and contract.project_id != category.default_project_id:
            resolved_contract_id = None

    return resolved_project_id, resolved_contract_id, is_tax_related


async def _resolve_expense_links(
    db: AsyncSession,
    project_id: int | None,
    contract_id: int | None,
) -> tuple[int | None, int | None]:
    resolved_project_id = project_id or await _get_unassigned_project_id(db)
    resolved_contract_id = contract_id

    if resolved_contract_id is not None:
        contract = await _get_contract_or_404(db, resolved_contract_id)
        if contract.project_id is None:
            if resolved_project_id is None:
                raise HTTPException(400, "Select a project before linking this contract")
            await _get_project_or_404(db, resolved_project_id)
            contract.project_id = resolved_project_id
            await db.flush()
        resolved_project_id = contract.project_id

    if resolved_project_id is not None:
        await _get_project_or_404(db, resolved_project_id)

    return resolved_project_id, resolved_contract_id


async def _get_cash_totals(db: AsyncSession):
    total_in = to_decimal(
        await db.scalar(
            select(func.coalesce(func.sum(CashEntry.amount), 0)).where(CashEntry.direction == "in")
        )
        or 0
    )
    total_out = to_decimal(
        await db.scalar(
            select(func.coalesce(func.sum(CashEntry.amount), 0)).where(CashEntry.direction == "out")
        )
        or 0
    )
    return total_in - total_out, total_in, total_out


def _build_withdrawal_description(transaction: BankTransaction) -> str:
    return (
        (transaction.purpose or "").strip()
        or (transaction.counterparty_name or "").strip()
        or (transaction.bank_reference or "").strip()
        or f"Cash withdrawal from bank transaction #{transaction.id}"
    )[:500]


def _serialize_cash_entry(entry: CashEntry, balance_after: float) -> CashEntryResponse:
    bank_transaction = getattr(entry, "bank_transaction", None)
    expense = getattr(entry, "expense", None)
    return CashEntryResponse(
        id=entry.id,
        date=entry.date,
        direction=entry.direction,
        amount=to_decimal(entry.amount or ZERO_DECIMAL),
        currency=entry.currency or "RSD",
        description=entry.description,
        entry_type=entry.entry_type,
        note=entry.note,
        bank_transaction_id=entry.bank_transaction_id,
        expense_id=entry.expense_id,
        bank_reference=getattr(bank_transaction, "bank_reference", None),
        counterparty_name=getattr(bank_transaction, "counterparty_name", None),
        purpose=getattr(bank_transaction, "purpose", None),
        expense_status=getattr(expense, "status", None),
        category_id=getattr(expense, "category_id", None),
        contract_id=getattr(expense, "contract_id", None),
        project_id=getattr(expense, "project_id", None) or getattr(bank_transaction, "project_id", None),
        balance_after=balance_after,
        created_at=entry.created_at,
    )


async def _get_entry_with_links(db: AsyncSession, entry_id: int) -> CashEntry:
    result = await db.execute(
        select(CashEntry)
        .options(
            selectinload(CashEntry.bank_transaction),
            selectinload(CashEntry.expense),
        )
        .where(CashEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Cash entry not found")
    return entry


def _signed_entry_amount(direction: str, amount):
    value = to_decimal(amount or ZERO_DECIMAL)
    return value if direction == "in" else -value


async def _get_balance_after_entry(db: AsyncSession, entry_id: int):
    result = await db.execute(
        select(CashEntry.id, CashEntry.direction, CashEntry.amount)
        .order_by(CashEntry.date.asc(), CashEntry.id.asc())
    )
    balance = ZERO_DECIMAL
    for current_id, direction, amount in result.fetchall():
        balance += _signed_entry_amount(str(direction), amount)
        if int(current_id) == int(entry_id):
            return balance
    return balance


async def _serialize_refreshed_entry(db: AsyncSession, entry_id: int) -> CashEntryResponse:
    entry = await _get_entry_with_links(db, entry_id)
    return _serialize_cash_entry(entry, await _get_balance_after_entry(db, entry_id))


async def _build_cash_summary(
    db: AsyncSession,
    year: Optional[int] = None,
    month: Optional[int] = None,
    limit: int = 200,
) -> CashSummaryResponse:
    current_balance, total_in, total_out = await _get_cash_totals(db)

    entries_query = (
        select(CashEntry)
        .options(
            selectinload(CashEntry.bank_transaction),
            selectinload(CashEntry.expense),
        )
        .order_by(CashEntry.date.asc(), CashEntry.id.asc())
    )
    if year:
        entries_query = entries_query.where(CashEntry.date >= date(year, 1, 1), CashEntry.date <= date(year, 12, 31))
    if month and year:
        import calendar

        last_day = calendar.monthrange(year, month)[1]
        entries_query = entries_query.where(CashEntry.date >= date(year, month, 1), CashEntry.date <= date(year, month, last_day))

    entries_result = await db.execute(entries_query)
    entries = list(entries_result.scalars().all())
    if limit:
        entries = entries[-limit:]

    running_balance = ZERO_DECIMAL
    entry_items: list[CashEntryResponse] = []
    for entry in entries:
        if entry.direction == "in":
            running_balance += to_decimal(entry.amount or ZERO_DECIMAL)
        else:
            running_balance -= to_decimal(entry.amount or ZERO_DECIMAL)
        entry_items.append(_serialize_cash_entry(entry, running_balance))
    entry_items.reverse()

    withdrawals_query = (
        select(BankTransaction)
        .where(
            BankTransaction.direction == "out",
            BankTransaction.status.in_(["unmatched", "ignored"]),
        )
        .order_by(BankTransaction.date.desc(), BankTransaction.id.desc())
        .limit(50)
    )
    available_withdrawals_result = await db.execute(withdrawals_query)
    available_withdrawals = [
        CashBankWithdrawalCandidate.model_validate(item)
        for item in available_withdrawals_result.scalars().all()
    ]

    return CashSummaryResponse(
        current_balance=current_balance,
        total_in=total_in,
        total_out=total_out,
        entries=entry_items,
        available_withdrawals=available_withdrawals,
    )


@router.get("", response_model=CashSummaryResponse)
async def get_cash_summary(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    limit: int = Query(200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    return await _build_cash_summary(db, year=year, month=month, limit=limit)


@router.patch("/{entry_id}", response_model=CashEntryResponse)
async def update_cash_entry(
    entry_id: int,
    data: CashEntryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    entry = await _get_entry_with_links(db, entry_id)
    payload = data.model_dump(exclude_unset=True)
    if not payload:
        return await _serialize_refreshed_entry(db, entry_id)

    if entry.entry_type == "adjustment":
        direction = payload.get("direction", entry.direction)
        if direction not in {"in", "out"}:
            raise HTTPException(400, "Direction must be in or out")
        amount = to_decimal(payload.get("amount", entry.amount) or ZERO_DECIMAL)
        description = payload.get("description", entry.description)
        if not (description or "").strip():
            raise HTTPException(400, "Description is required")

        entry.date = payload.get("date", entry.date)
        entry.direction = direction
        entry.amount = amount
        entry.currency = payload.get("currency", entry.currency) or "RSD"
        entry.description = description.strip()[:500]
        entry.note = payload.get("note", entry.note)

    elif entry.entry_type == "expense":
        expense = entry.expense
        if not expense:
            raise HTTPException(404, "Expense not found for this cash entry")

        amount = to_decimal(payload.get("amount", expense.amount) or ZERO_DECIMAL)
        description = payload.get("description", expense.description)
        if not (description or "").strip():
            raise HTTPException(400, "Description is required")

        desired_project_id = payload.get("project_id", expense.project_id)
        desired_contract_id = payload.get("contract_id", expense.contract_id)
        if not desired_project_id:
            desired_project_id = await _get_unassigned_project_id(db)
        desired_project_id, desired_contract_id, is_tax_related = await _resolve_category_expense_links(
            db,
            payload.get("category_id", expense.category_id),
            desired_project_id,
            desired_contract_id,
        )
        if desired_contract_id is None and expense.contract_id and "project_id" in payload:
            current_contract = await _get_contract_or_404(db, expense.contract_id)
            if current_contract.project_id != desired_project_id:
                desired_contract_id = None
        desired_project_id, desired_contract_id = await _resolve_expense_links(db, desired_project_id, desired_contract_id)

        category_id = payload.get("category_id", expense.category_id)
        category_name = expense.category
        if "category_id" in payload:
            category_name = None
            if category_id is not None:
                category_result = await db.execute(select(TransactionCategory).where(TransactionCategory.id == category_id))
                category = category_result.scalar_one_or_none()
                if not category:
                    raise HTTPException(404, "Category not found")
                category_name = category.name_ru

        date_value = payload.get("date", expense.date)
        currency = payload.get("currency", expense.currency) or "RSD"
        note = payload.get("note", expense.note)

        expense.date = date_value
        expense.paid_date = date_value
        expense.description = description.strip()[:500]
        expense.amount = amount
        expense.currency = currency
        expense.category_id = category_id
        expense.category = category_name
        expense.is_tax_related = is_tax_related
        expense.project_id = desired_project_id
        expense.contract_id = desired_contract_id
        expense.note = note

        entry.date = date_value
        entry.amount = amount
        entry.currency = currency
        entry.description = expense.description
        entry.note = note

    elif entry.entry_type == "withdrawal":
        forbidden_fields = {"date", "direction", "amount", "currency", "category_id"}
        invalid = sorted(field for field in forbidden_fields if field in payload)
        if invalid:
            raise HTTPException(400, "Withdrawal date, amount and category come from the bank transaction")

        description = payload.get("description", entry.description)
        if not (description or "").strip():
            raise HTTPException(400, "Description is required")

        expense = entry.expense
        desired_project_id = payload.get("project_id", getattr(expense, "project_id", None))
        desired_contract_id = payload.get("contract_id", getattr(expense, "contract_id", None))
        if not desired_project_id:
            desired_project_id = await _get_unassigned_project_id(db)
        desired_project_id, desired_contract_id = await _resolve_expense_links(db, desired_project_id, desired_contract_id)

        note = payload.get("note", getattr(expense, "note", entry.note))
        if expense:
            expense.description = description.strip()[:500]
            expense.project_id = desired_project_id
            expense.contract_id = desired_contract_id
            expense.note = note
        if entry.bank_transaction:
            entry.bank_transaction.project_id = desired_project_id

        entry.description = description.strip()[:500]
        entry.note = note

    else:
        raise HTTPException(400, "Unsupported cash entry type")

    await db.commit()
    return await _serialize_refreshed_entry(db, entry_id)


@router.post("/withdrawals", response_model=CashEntryResponse)
async def create_cash_withdrawal(
    data: CashWithdrawalCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    result = await db.execute(select(BankTransaction).where(BankTransaction.id == data.bank_transaction_id))
    transaction = result.scalar_one_or_none()
    if not transaction:
        raise HTTPException(404, "Transaction not found")
    try:
        _, entry = await create_cash_transfer_from_transaction(
            db,
            transaction,
            project_id=transaction.project_id,
            contract_id=None,
            description=_build_withdrawal_description(transaction),
            note=data.note,
            created_by=current_user.id,
        )
        await db.commit()
        return await _serialize_refreshed_entry(db, entry.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/adjustments", response_model=CashEntryResponse)
async def create_cash_adjustment(
    data: CashAdjustmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    if data.direction not in {"in", "out"}:
        raise HTTPException(400, "Direction must be in or out")

    entry = CashEntry(
        date=data.date,
        direction=data.direction,
        amount=to_decimal(data.amount or ZERO_DECIMAL),
        currency="RSD",
        description=(data.description or "").strip()[:500],
        entry_type="adjustment",
        note=data.note,
        created_by=current_user.id,
    )
    if not entry.description:
        raise HTTPException(400, "Description is required")

    db.add(entry)
    await db.commit()
    return await _serialize_refreshed_entry(db, entry.id)


@router.post("/expenses", response_model=CashEntryResponse)
async def create_cash_expense(
    data: CashExpenseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    project_id, contract_id, is_tax_related = await _resolve_category_expense_links(
        db,
        data.category_id,
        data.project_id,
        data.contract_id,
    )
    project_id, contract_id = await _resolve_expense_links(db, project_id, contract_id)

    category_name = (data.category or "").strip() or None
    if data.category_id is not None:
        category_result = await db.execute(select(TransactionCategory).where(TransactionCategory.id == data.category_id))
        category = category_result.scalar_one_or_none()
        if not category:
            raise HTTPException(404, "Category not found")
        category_name = category.name_ru

    description = (data.description or "").strip()
    if not description:
        raise HTTPException(400, "Description is required")

    expense = Expense(
        date=data.date,
        description=description[:500],
        amount=to_decimal(data.amount or ZERO_DECIMAL),
        currency=data.currency or "RSD",
        category=category_name,
        category_id=data.category_id,
        contract_id=contract_id,
        is_tax_related=is_tax_related,
        source="cash",
        note=data.note,
        project_id=project_id,
        created_by=current_user.id,
    )
    initialize_expense_status(expense, "paid", paid_date=data.date)
    db.add(expense)
    await db.flush()

    entry = CashEntry(
        date=data.date,
        direction="out",
        amount=to_decimal(data.amount or ZERO_DECIMAL),
        currency=data.currency or "RSD",
        description=description[:500],
        entry_type="expense",
        note=data.note,
        expense_id=expense.id,
        created_by=current_user.id,
    )
    db.add(entry)
    await db.commit()
    return await _serialize_refreshed_entry(db, entry.id)


