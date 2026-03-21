from collections import defaultdict
from datetime import date
from typing import Optional
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user_required, require_edit_access
from backend.cash_service import CASH_TRANSFER_SOURCE, is_cash_transfer_expense
from backend.database import get_db
from backend.decimal_utils import ZERO_DECIMAL, money_gt, to_decimal
from backend.models import BankTransaction, CashEntry, Contract, Expense, MonthlyObligation, PlannedExpensePayment, Project, TransactionCategory, User
from backend.schemas import (
    BulkAssignProject,
    ExpenseCreate,
    ExpenseDuplicateGroup,
    ExpenseDuplicateItem,
    ExpenseMergeRequest,
    ExpenseResponse,
    ExpenseReverseRequest,
    ExpenseUpdate,
)
from backend.state_machine import InvalidStatusTransition, initialize_expense_status, mark_expense_paid
from backend.services import create_expense_reversal

router = APIRouter(prefix="/expenses", tags=["expenses"])
EFAKTURA_IMPORT_SOURCE = "efaktura_import"


def _visible_expense_condition():
    return or_(Expense.status != "planned", Expense.source == EFAKTURA_IMPORT_SOURCE)


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


async def _clear_contract_if_project_mismatch(db: AsyncSession, expense: Expense, project_id: int | None) -> None:
    if not expense.contract_id or project_id is None:
        return
    contract = await _get_contract_or_404(db, expense.contract_id)
    if contract.project_id != project_id:
        expense.contract_id = None


async def _sync_cash_entry_from_expense(db: AsyncSession, expense: Expense) -> None:
    result = await db.execute(select(CashEntry).where(CashEntry.expense_id == expense.id))
    cash_entry = result.scalar_one_or_none()
    if not cash_entry:
        return

    cash_entry.date = expense.paid_date or expense.date
    cash_entry.amount = to_decimal(expense.amount or ZERO_DECIMAL)
    cash_entry.currency = expense.currency or "RSD"
    cash_entry.description = (expense.description or "")[:500]
    cash_entry.note = expense.note


async def _sync_bank_transactions_from_expense(db: AsyncSession, expense: Expense) -> None:
    await db.execute(
        update(BankTransaction)
        .where(BankTransaction.matched_type == "expense", BankTransaction.matched_id == expense.id)
        .values(project_id=expense.project_id)
    )

    if not expense.bank_reference or _is_reversal_row(expense):
        return

    amount = abs(to_decimal(expense.amount or ZERO_DECIMAL))
    result = await db.execute(
        select(BankTransaction).where(
            BankTransaction.bank_reference == expense.bank_reference,
            BankTransaction.direction == "out",
        )
    )
    candidates = [
        tx
        for tx in result.scalars().all()
        if abs(to_decimal(tx.amount or ZERO_DECIMAL)) == amount
    ]
    if len(candidates) != 1:
        return

    tx = candidates[0]
    tx.status = "matched"
    tx.matched_type = "expense"
    tx.matched_id = expense.id
    tx.project_id = expense.project_id


def _normalize_duplicate_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _amount_key(value: float | int | None) -> str:
    return f"{abs(to_decimal(value or ZERO_DECIMAL)):.2f}"


def _is_reversal_row(expense: Expense) -> bool:
    return bool(expense.reversal_of_id) or getattr(expense, "status", None) == "reversed" or to_decimal(expense.amount or ZERO_DECIMAL) < ZERO_DECIMAL


def _is_active_duplicate_candidate(expense: Expense) -> bool:
    if _is_reversal_row(expense):
        return False
    if getattr(expense, "reversed_expense_id", None):
        return False
    if getattr(expense, "status", None) == "planned":
        return False
    return money_gt(expense.amount or ZERO_DECIMAL)


async def _load_expenses_for_period(
    db: AsyncSession,
    year: Optional[int],
    month: Optional[int],
) -> list[Expense]:
    query = (
        select(Expense)
        .where(
            Expense.source != CASH_TRANSFER_SOURCE,
            _visible_expense_condition(),
        )
        .order_by(Expense.date.desc(), Expense.id.desc())
    )
    if year:
        query = query.where(Expense.date >= date(year, 1, 1), Expense.date <= date(year, 12, 31))
    if month and year:
        import calendar

        last_day = calendar.monthrange(year, month)[1]
        query = query.where(Expense.date >= date(year, month, 1), Expense.date <= date(year, month, last_day))
    result = await db.execute(query)
    return list(result.scalars().all())


async def _find_duplicate_groups(
    db: AsyncSession,
    year: Optional[int],
    month: Optional[int],
) -> list[ExpenseDuplicateGroup]:
    items = [item for item in await _load_expenses_for_period(db, year, month) if _is_active_duplicate_candidate(item)]
    by_reference: dict[tuple[str, str], list[Expense]] = defaultdict(list)
    by_description: dict[tuple[str, str, date | None], list[Expense]] = defaultdict(list)

    for item in items:
        amount_key = _amount_key(item.amount)
        normalized_reference = _normalize_duplicate_text(item.bank_reference)
        normalized_description = _normalize_duplicate_text(item.description)
        if normalized_reference:
            by_reference[(normalized_reference, amount_key)].append(item)
        elif normalized_description:
            by_description[(normalized_description, amount_key, item.date)].append(item)

    groups: list[ExpenseDuplicateGroup] = []
    seen_ids: set[tuple[int, ...]] = set()

    def add_group(reason: str, expenses: list[Expense], payment_reference: str | None = None, description: str | None = None) -> None:
        ids = tuple(sorted(expense.id for expense in expenses))
        if len(ids) < 2 or ids in seen_ids:
            return
        seen_ids.add(ids)
        sorted_items = sorted(expenses, key=lambda expense: (expense.date, expense.id))
        groups.append(
            ExpenseDuplicateGroup(
                reason=reason,
                amount=to_decimal(sorted_items[0].amount or ZERO_DECIMAL),
                payment_reference=payment_reference,
                description=description,
                item_count=len(sorted_items),
                items=[ExpenseDuplicateItem.model_validate(item) for item in sorted_items],
            )
        )

    for (_, _), expenses in sorted(by_reference.items(), key=lambda item: item[0]):
        if len(expenses) > 1:
            add_group("payment_reference", expenses, payment_reference=expenses[0].bank_reference)

    for (_, _, _), expenses in sorted(by_description.items(), key=lambda item: item[0]):
        if len(expenses) > 1:
            add_group("description_amount", expenses, description=expenses[0].description)

    groups.sort(key=lambda group: (group.items[0].date if group.items else date.min, group.item_count), reverse=True)
    return groups


def _non_empty_payment_refs(expenses: list[Expense]) -> set[str]:
    refs: set[str] = set()
    for expense in expenses:
        normalized_reference = _normalize_duplicate_text(getattr(expense, "bank_reference", None))
        if normalized_reference:
            refs.add(normalized_reference)
    return refs


def _merge_notes(primary: str | None, secondary: str | None) -> str | None:
    left = (primary or "").strip()
    right = (secondary or "").strip()
    if not left:
        return right or None
    if not right or right in left:
        return left
    if left in right:
        return right
    return f"{left}\n{right}"


async def _merge_expense_links(
    db: AsyncSession,
    keep: Expense,
    duplicate: Expense,
) -> None:
    await db.execute(
        update(BankTransaction)
        .where(BankTransaction.matched_type == "expense", BankTransaction.matched_id == duplicate.id)
        .values(matched_id=keep.id)
    )
    await db.execute(
        update(MonthlyObligation)
        .where(MonthlyObligation.expense_id == duplicate.id)
        .values(expense_id=keep.id)
    )
    await db.execute(
        update(PlannedExpensePayment)
        .where(PlannedExpensePayment.expense_id == duplicate.id)
        .values(expense_id=keep.id)
    )


@router.get("", response_model=list[ExpenseResponse])
async def list_expenses(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    category_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    query = (
        select(Expense)
        .where(
            Expense.source != CASH_TRANSFER_SOURCE,
            _visible_expense_condition(),
        )
        .order_by(Expense.date.desc(), Expense.id.desc())
    )
    if year:
        query = query.where(Expense.date >= date(year, 1, 1), Expense.date <= date(year, 12, 31))
    if month and year:
        import calendar

        last_day = calendar.monthrange(year, month)[1]
        query = query.where(Expense.date >= date(year, month, 1), Expense.date <= date(year, month, last_day))
    if category:
        query = query.where(Expense.category == category)
    if category_id:
        query = query.where(Expense.category_id == category_id)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()
    return [ExpenseResponse.model_validate(item) for item in items]


@router.get("/years", response_model=list[int])
async def list_expense_years(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(Expense.date).where(
            Expense.source != CASH_TRANSFER_SOURCE,
            _visible_expense_condition(),
        )
    )
    years = {value.year for (value,) in result.fetchall() if value is not None}
    if not years:
        years.add(date.today().year)
    return sorted(years, reverse=True)


@router.get("/duplicates", response_model=list[ExpenseDuplicateGroup])
async def list_expense_duplicates(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    return await _find_duplicate_groups(db, year, month)


@router.post("/merge-duplicates", response_model=ExpenseResponse)
async def merge_expense_duplicates(
    data: ExpenseMergeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    merge_ids = [expense_id for expense_id in data.merge_ids if expense_id != data.keep_id]
    if not merge_ids:
        raise HTTPException(400, "No duplicate expenses selected for merge")

    result = await db.execute(select(Expense).where(Expense.id.in_([data.keep_id, *merge_ids])))
    items = {item.id: item for item in result.scalars().all()}
    keep = items.get(data.keep_id)
    if not keep:
        raise HTTPException(404, "Expense to keep was not found")
    if _is_reversal_row(keep) or getattr(keep, "reversed_expense_id", None):
        raise HTTPException(400, "Reversal expenses cannot be merged")

    duplicates: list[Expense] = []
    for expense_id in merge_ids:
        duplicate = items.get(expense_id)
        if not duplicate:
            raise HTTPException(404, f"Expense {expense_id} was not found")
        if _is_reversal_row(duplicate) or getattr(duplicate, "reversed_expense_id", None):
            raise HTTPException(400, "Reversal expenses cannot be merged")
        duplicates.append(duplicate)

    payment_refs = _non_empty_payment_refs([keep, *duplicates])
    if len(payment_refs) > 1:
        raise HTTPException(400, "Expenses with different payment references cannot be merged")

    unassigned_project_id = await _get_unassigned_project_id(db)
    for duplicate in duplicates:
        await _merge_expense_links(db, keep, duplicate)

        if not keep.bank_reference and duplicate.bank_reference:
            keep.bank_reference = duplicate.bank_reference
        if keep.category_id is None and duplicate.category_id is not None:
            keep.category_id = duplicate.category_id
        if not keep.category and duplicate.category:
            keep.category = duplicate.category
        if keep.contract_id is None and duplicate.contract_id is not None:
            keep.contract_id = duplicate.contract_id
        if keep.project_id in (None, unassigned_project_id) and duplicate.project_id not in (None, unassigned_project_id):
            keep.project_id = duplicate.project_id
        if keep.paid_date is None and duplicate.paid_date is not None:
            keep.paid_date = duplicate.paid_date
        if keep.status != "paid" and duplicate.status == "paid":
            try:
                mark_expense_paid(keep, paid_date=keep.paid_date, allow_same=True)
            except InvalidStatusTransition as exc:
                raise HTTPException(400, str(exc)) from exc
        keep.note = _merge_notes(keep.note, duplicate.note)

        await db.delete(duplicate)

    if keep.project_id is not None:
        await _clear_contract_if_project_mismatch(db, keep, keep.project_id)
        await db.execute(
            update(BankTransaction)
            .where(BankTransaction.matched_type == "expense", BankTransaction.matched_id == keep.id)
            .values(project_id=keep.project_id)
        )

    await db.commit()
    await db.refresh(keep)
    return ExpenseResponse.model_validate(keep)


@router.post("", response_model=ExpenseResponse)
async def create_expense(
    data: ExpenseCreate,
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
    expense = Expense(
        date=data.date,
        description=data.description,
        amount=data.amount,
        currency=data.currency,
        category=data.category,
        category_id=data.category_id,
        contract_id=contract_id,
        is_tax_related=is_tax_related,
        note=data.note,
        project_id=project_id,
        source="manual",
        created_by=current_user.id,
    )
    initialize_expense_status(expense, "paid", paid_date=data.paid_date or data.date)
    db.add(expense)
    await db.flush()
    await _sync_bank_transactions_from_expense(db, expense)
    await db.commit()
    await db.refresh(expense)
    return ExpenseResponse.model_validate(expense)


@router.post("/bulk-assign-project")
async def bulk_assign_project_expenses(
    data: BulkAssignProject,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    if not data.ids:
        return {"updated": 0}

    project_id = data.project_id
    if project_id is None:
        project_id = await _get_unassigned_project_id(db)
    if project_id is not None:
        await _get_project_or_404(db, project_id)

    result = await db.execute(select(Expense).where(Expense.id.in_(data.ids)))
    items = result.scalars().all()
    for item in items:
        item.project_id = project_id
        await _clear_contract_if_project_mismatch(db, item, project_id)
        await _sync_bank_transactions_from_expense(db, item)

    await db.commit()
    return {"updated": len(items)}


@router.get("/totals/summary")
async def get_expense_totals(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    today = date.today()
    selected_year = year or today.year
    selected_month = month or today.month

    result_year = await db.execute(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.source != CASH_TRANSFER_SOURCE,
            _visible_expense_condition(),
            Expense.date >= date(selected_year, 1, 1),
            Expense.date <= date(selected_year, 12, 31),
        )
    )
    year_total = to_decimal(result_year.scalar() or ZERO_DECIMAL)

    import calendar

    last_day = calendar.monthrange(selected_year, selected_month)[1]
    result_month = await db.execute(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.source != CASH_TRANSFER_SOURCE,
            _visible_expense_condition(),
            Expense.date >= date(selected_year, selected_month, 1),
            Expense.date <= date(selected_year, selected_month, last_day),
        )
    )
    month_total = to_decimal(result_month.scalar() or ZERO_DECIMAL)

    return {"year_expenses": year_total, "month_expenses": month_total}


@router.get("/{expense_id}", response_model=ExpenseResponse)
async def get_expense(
    expense_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    result = await db.execute(select(Expense).where(Expense.id == expense_id))
    expense = result.scalar_one_or_none()
    if not expense:
        raise HTTPException(404, "Expense not found")
    return ExpenseResponse.model_validate(expense)


@router.patch("/{expense_id}/reverse", response_model=ExpenseResponse)
async def reverse_expense(
    expense_id: int,
    data: ExpenseReverseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    result = await db.execute(select(Expense).where(Expense.id == expense_id))
    expense = result.scalar_one_or_none()
    if not expense:
        raise HTTPException(404, "Expense not found")
    if getattr(expense, "status", "paid") == "reversed":
        raise HTTPException(400, "Expense is already a reversal entry")
    if getattr(expense, "reversed_expense_id", None):
        raise HTTPException(400, "Expense is already reversed")
    if is_cash_transfer_expense(expense):
        raise HTTPException(400, "Cash transfer operations must be managed from bank or cash")
    if getattr(expense, "source", None) == "cash":
        raise HTTPException(400, "Cash expenses must be managed from the cash screen")

    reversal = await create_expense_reversal(
        db,
        expense,
        reverse_date=data.date if data.date else None,
        comment=data.comment,
        source="manual",
        created_by=current_user.id,
    )
    await db.commit()
    return ExpenseResponse.model_validate(reversal)


@router.patch("/{expense_id}", response_model=ExpenseResponse)
async def update_expense(
    expense_id: int,
    data: ExpenseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    result = await db.execute(select(Expense).where(Expense.id == expense_id))
    expense = result.scalar_one_or_none()
    if not expense:
        raise HTTPException(404, "Expense not found")
    if is_cash_transfer_expense(expense):
        raise HTTPException(400, "Cash transfer operations must be managed from bank or cash")

    dump = data.model_dump(exclude_unset=True)
    desired_project_id = dump.get("project_id", expense.project_id)
    desired_contract_id = dump.get("contract_id", expense.contract_id)
    desired_project_id, desired_contract_id, is_tax_related = await _resolve_category_expense_links(
        db,
        dump.get("category_id", expense.category_id),
        desired_project_id,
        desired_contract_id,
    )

    if not desired_project_id:
        desired_project_id = await _get_unassigned_project_id(db)

    if desired_contract_id is None and expense.contract_id and "project_id" in dump:
        contract = await _get_contract_or_404(db, expense.contract_id)
        if contract.project_id != desired_project_id:
            desired_contract_id = None

    desired_project_id, desired_contract_id = await _resolve_expense_links(db, desired_project_id, desired_contract_id)
    dump["project_id"] = desired_project_id
    dump["contract_id"] = desired_contract_id
    dump["is_tax_related"] = is_tax_related

    for key, value in dump.items():
        setattr(expense, key, value)

    if getattr(expense, "source", None) == "cash":
        await _sync_cash_entry_from_expense(db, expense)
    await _sync_bank_transactions_from_expense(db, expense)

    await db.flush()
    await db.commit()
    await db.refresh(expense)
    return ExpenseResponse.model_validate(expense)


@router.delete("/{expense_id}")
async def delete_expense(
    expense_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    result = await db.execute(select(Expense).where(Expense.id == expense_id))
    expense = result.scalar_one_or_none()
    if not expense:
        raise HTTPException(404, "Expense not found")
    if is_cash_transfer_expense(expense):
        raise HTTPException(400, "Cash transfer operations must be managed from bank or cash")
    if getattr(expense, "source", None) == "cash":
        raise HTTPException(400, "Cash expenses must be managed from the cash screen")

    if _is_reversal_row(expense):
        original_expense = None
        if expense.reversal_of_id:
            original_result = await db.execute(select(Expense).where(Expense.id == expense.reversal_of_id))
            original_expense = original_result.scalar_one_or_none()
            if original_expense and original_expense.reversed_expense_id == expense.id:
                original_expense.reversed_expense_id = None

        await db.execute(
            update(BankTransaction)
            .where(BankTransaction.matched_type == "expense", BankTransaction.matched_id == expense.id)
            .values(status="unmatched", matched_type=None, matched_id=None)
        )
        await db.execute(update(MonthlyObligation).where(MonthlyObligation.expense_id == expense.id).values(expense_id=None))
        await db.execute(update(PlannedExpensePayment).where(PlannedExpensePayment.expense_id == expense.id).values(expense_id=None))
        await db.delete(expense)
        await db.commit()
        return {"ok": True, "deleted": True, "restored_expense_id": original_expense.id if original_expense else None}

    if getattr(expense, "reversed_expense_id", None):
        raise HTTPException(400, "Delete the reversal entry to restore this expense")

    reversal = await create_expense_reversal(
        db,
        expense,
        source=getattr(expense, "source", None) or "manual",
        created_by=current_user.id,
    )
    await db.commit()
    return {"ok": True, "reversal_id": reversal.id}


