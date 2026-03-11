from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.auth import get_current_user_required, require_edit_access
from backend.database import get_db
from backend.models import BankTransaction, CashEntry, Contract, Expense, Project, TransactionCategory, User
from backend.schemas import (
    CashAdjustmentCreate,
    CashBankWithdrawalCandidate,
    CashEntryResponse,
    CashExpenseCreate,
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


async def _get_cash_totals(db: AsyncSession) -> tuple[float, float, float]:
    total_in = float(
        await db.scalar(
            select(func.coalesce(func.sum(CashEntry.amount), 0)).where(CashEntry.direction == "in")
        )
        or 0
    )
    total_out = float(
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
        amount=float(entry.amount or 0),
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

    running_balance = 0.0
    entry_items: list[CashEntryResponse] = []
    for entry in entries:
        if entry.direction == "in":
            running_balance += float(entry.amount or 0)
        else:
            running_balance -= float(entry.amount or 0)
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
    if transaction.direction != "out":
        raise HTTPException(400, "Only outgoing bank transactions can be transferred to cash")
    if transaction.status not in {"unmatched", "ignored"}:
        raise HTTPException(400, "Transaction is already matched")

    existing_result = await db.execute(
        select(CashEntry)
        .options(selectinload(CashEntry.bank_transaction), selectinload(CashEntry.expense))
        .where(CashEntry.bank_transaction_id == transaction.id)
    )
    existing_entry = existing_result.scalar_one_or_none()
    if existing_entry:
        raise HTTPException(400, "This bank transaction is already added to cash")

    entry = CashEntry(
        date=transaction.date,
        direction="in",
        amount=float(transaction.amount or 0),
        currency=transaction.currency or "RSD",
        description=_build_withdrawal_description(transaction),
        entry_type="withdrawal",
        note=data.note,
        bank_transaction_id=transaction.id,
        created_by=current_user.id,
    )
    db.add(entry)
    await db.flush()

    transaction.status = "matched"
    transaction.matched_type = "cash"
    transaction.matched_id = entry.id

    await db.commit()
    entry = await _get_entry_with_links(db, entry.id)
    current_balance, _, _ = await _get_cash_totals(db)
    return _serialize_cash_entry(entry, current_balance)


@router.post("/adjustments", response_model=CashEntryResponse)
async def create_cash_adjustment(
    data: CashAdjustmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    if data.direction not in {"in", "out"}:
        raise HTTPException(400, "Direction must be in or out")

    current_balance, _, _ = await _get_cash_totals(db)
    if data.direction == "out" and float(data.amount or 0) > current_balance:
        raise HTTPException(400, "Insufficient cash balance")

    entry = CashEntry(
        date=data.date,
        direction=data.direction,
        amount=float(data.amount or 0),
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
    entry = await _get_entry_with_links(db, entry.id)
    current_balance, _, _ = await _get_cash_totals(db)
    return _serialize_cash_entry(entry, current_balance)


@router.post("/expenses", response_model=CashEntryResponse)
async def create_cash_expense(
    data: CashExpenseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    current_balance, _, _ = await _get_cash_totals(db)
    if float(data.amount or 0) > current_balance:
        raise HTTPException(400, "Insufficient cash balance")

    project_id, contract_id = await _resolve_expense_links(db, data.project_id, data.contract_id)

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
        amount=float(data.amount or 0),
        currency=data.currency or "RSD",
        category=category_name,
        category_id=data.category_id,
        contract_id=contract_id,
        paid_date=data.date,
        status="paid",
        source="cash",
        note=data.note,
        project_id=project_id,
        created_by=current_user.id,
    )
    db.add(expense)
    await db.flush()

    entry = CashEntry(
        date=data.date,
        direction="out",
        amount=float(data.amount or 0),
        currency=data.currency or "RSD",
        description=description[:500],
        entry_type="expense",
        note=data.note,
        expense_id=expense.id,
        created_by=current_user.id,
    )
    db.add(entry)
    await db.commit()
    entry = await _get_entry_with_links(db, entry.id)
    current_balance, _, _ = await _get_cash_totals(db)
    return _serialize_cash_entry(entry, current_balance)
