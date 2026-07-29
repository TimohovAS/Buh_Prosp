from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.auth import get_current_user_required, require_admin, require_edit_access
from backend.cash_service import CASH_TRANSFER_SOURCE, is_cash_transfer_expense
from backend.database import get_db
from backend.db_utils import (
    get_contract_or_404,
    get_project_or_404,
    get_unassigned_project_id,
    resolve_category_expense_links,
)
from backend.decimal_utils import ZERO_DECIMAL, to_decimal
from backend.expense_service import (
    NotFoundError,
    build_expense_item_models,
    clear_contract_if_project_mismatch,
    expense_amount_from_items,
    expense_description_from_items,
    find_expense_duplicate_groups,
    is_reversal_row,
    merge_duplicate_expenses,
    normalize_expense_items,
    resolve_expense_links,
    sync_bank_transactions_from_expense,
    sync_cash_entry_from_expense,
)
from backend.receipt_service import sync_receipt_project_from_expense
from backend.models import (
    BankTransaction,
    CashEntry,
    Expense,
    ExpenseItem,
    IncomingInvoice,
    MonthlyObligation,
    PurchaseReceipt,
    User,
)
from backend.schemas import (
    BulkAssignProject,
    ExpenseCreate,
    ExpenseDetailResponse,
    ExpenseDuplicateGroup,
    ExpenseHardDeleteRequest,
    ExpenseMergeRequest,
    ExpenseResponse,
    ExpenseReverseRequest,
    ExpenseUpdate,
    PurchaseReceiptDetailResponse,
)
from backend.state_machine import initialize_expense_status
from backend.services import create_expense_reversal

router = APIRouter(prefix="/expenses", tags=["expenses"])
EFAKTURA_IMPORT_SOURCE = "efaktura_import"
RECEIPT_SOURCE = "receipt"


def _visible_expense_condition():
    return or_(Expense.status != "planned", Expense.source.in_([EFAKTURA_IMPORT_SOURCE, RECEIPT_SOURCE]))


async def _resolve_expense_links_or_400(
    db: AsyncSession,
    project_id: int | None,
    contract_id: int | None,
    *,
    allow_completed: bool = False,
) -> tuple[int | None, int | None]:
    try:
        return await resolve_expense_links(
            db,
            project_id,
            contract_id,
            allow_completed=allow_completed,
        )
    except NotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


async def _clear_contract_if_project_mismatch_or_400(
    db: AsyncSession, expense: Expense, project_id: int | None
) -> None:
    try:
        await clear_contract_if_project_mismatch(db, expense, project_id)
    except NotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _is_reversal_row(expense: Expense) -> bool:
    return is_reversal_row(expense)


@router.get("", response_model=list[ExpenseResponse])
async def list_expenses(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    category_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: Optional[int] = Query(None, ge=1, le=5000),
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
    if skip:
        query = query.offset(skip)
    if limit is not None:
        query = query.limit(limit)
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
    return await find_expense_duplicate_groups(db, year, month)


@router.post("/merge-duplicates", response_model=ExpenseResponse)
async def merge_expense_duplicates(
    data: ExpenseMergeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    try:
        keep = await merge_duplicate_expenses(db, data.keep_id, data.merge_ids)
    except NotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    await db.commit()
    await db.refresh(keep)
    return ExpenseResponse.model_validate(keep)


@router.post("", response_model=ExpenseResponse)
async def create_expense(
    data: ExpenseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    project_id, contract_id, is_tax_related = await resolve_category_expense_links(
        db,
        data.category_id,
        data.project_id,
        data.contract_id,
    )
    project_id, contract_id = await _resolve_expense_links_or_400(db, project_id, contract_id)
    try:
        expense_items = normalize_expense_items(data.items)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    expense = Expense(
        date=data.date,
        description=expense_description_from_items(expense_items, data.description),
        amount=expense_amount_from_items(expense_items, data.amount),
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
    expense.items = build_expense_item_models(expense_items)
    initialize_expense_status(expense, "paid", paid_date=data.paid_date or data.date)
    db.add(expense)
    await db.flush()
    await sync_bank_transactions_from_expense(db, expense)
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
        project_id = await get_unassigned_project_id(db)
    if project_id is not None:
        await get_project_or_404(db, project_id)

    result = await db.execute(select(Expense).where(Expense.id.in_(data.ids)))
    items = result.scalars().all()
    for item in items:
        item.project_id = project_id
        await _clear_contract_if_project_mismatch_or_400(db, item, project_id)
        await sync_bank_transactions_from_expense(db, item)
        await sync_receipt_project_from_expense(db, item)

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


@router.get("/{expense_id}", response_model=ExpenseDetailResponse)
async def get_expense(
    expense_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(Expense)
        .options(
            selectinload(Expense.items),
            selectinload(Expense.purchase_receipt).selectinload(PurchaseReceipt.items),
        )
        .where(Expense.id == expense_id)
    )
    expense = result.scalar_one_or_none()
    if not expense:
        raise HTTPException(404, "Expense not found")
    response = ExpenseDetailResponse.model_validate(expense)
    if expense.purchase_receipt:
        response.receipt = PurchaseReceiptDetailResponse.model_validate(expense.purchase_receipt)
    return response


@router.patch("/{expense_id}/reverse", response_model=ExpenseResponse)
async def reverse_expense(
    expense_id: int,
    data: ExpenseReverseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    result = await db.execute(select(Expense).options(selectinload(Expense.items)).where(Expense.id == expense_id))
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
    result = await db.execute(select(Expense).options(selectinload(Expense.items)).where(Expense.id == expense_id))
    expense = result.scalar_one_or_none()
    if not expense:
        raise HTTPException(404, "Expense not found")
    if is_cash_transfer_expense(expense):
        raise HTTPException(400, "Cash transfer operations must be managed from bank or cash")

    dump = data.model_dump(exclude_unset=True)
    item_payload = dump.pop("items", None)
    desired_project_id = dump.get("project_id", expense.project_id)
    desired_contract_id = dump.get("contract_id", expense.contract_id)
    desired_project_id, desired_contract_id, is_tax_related = await resolve_category_expense_links(
        db,
        dump.get("category_id", expense.category_id),
        desired_project_id,
        desired_contract_id,
    )

    if not desired_project_id:
        desired_project_id = await get_unassigned_project_id(db)

    if desired_contract_id is None and expense.contract_id and "project_id" in dump:
        contract = await get_contract_or_404(db, expense.contract_id)
        if contract.project_id != desired_project_id:
            desired_contract_id = None

    desired_project_id, desired_contract_id = await _resolve_expense_links_or_400(
        db,
        desired_project_id,
        desired_contract_id,
        allow_completed=desired_project_id == expense.project_id,
    )
    dump["project_id"] = desired_project_id
    dump["contract_id"] = desired_contract_id
    dump["is_tax_related"] = is_tax_related

    if item_payload is not None:
        try:
            expense_items = normalize_expense_items(item_payload)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        dump["amount"] = expense_amount_from_items(expense_items, dump.get("amount", expense.amount))
        dump["description"] = expense_description_from_items(
            expense_items, dump.get("description", expense.description)
        )
        expense.items = build_expense_item_models(expense_items)

    for key, value in dump.items():
        setattr(expense, key, value)

    if getattr(expense, "source", None) == "cash":
        await sync_cash_entry_from_expense(db, expense)
    await sync_bank_transactions_from_expense(db, expense)
    await sync_receipt_project_from_expense(db, expense)

    await db.flush()
    await db.commit()
    await db.refresh(expense)
    return ExpenseResponse.model_validate(expense)


async def _admin_clear_expense_links(db: AsyncSession, expense_ids: list[int]) -> None:
    await db.execute(delete(ExpenseItem).where(ExpenseItem.expense_id.in_(expense_ids)))
    await db.execute(
        update(Expense).where(Expense.reversed_expense_id.in_(expense_ids)).values(reversed_expense_id=None)
    )
    await db.execute(update(Expense).where(Expense.reversal_of_id.in_(expense_ids)).values(reversal_of_id=None))
    await db.execute(
        update(BankTransaction)
        .where(BankTransaction.matched_type == "expense", BankTransaction.matched_id.in_(expense_ids))
        .values(status="unmatched", matched_type=None, matched_id=None)
    )
    await db.execute(update(CashEntry).where(CashEntry.expense_id.in_(expense_ids)).values(expense_id=None))
    await db.execute(
        update(MonthlyObligation).where(MonthlyObligation.expense_id.in_(expense_ids)).values(expense_id=None)
    )

    invoice_result = await db.execute(select(IncomingInvoice).where(IncomingInvoice.expense_id.in_(expense_ids)))
    for invoice in invoice_result.scalars().all():
        invoice.expense_id = None
        if invoice.status != "cancelled":
            invoice.settled_amount = ZERO_DECIMAL
            invoice.status = "unpaid"

    receipt_result = await db.execute(select(PurchaseReceipt).where(PurchaseReceipt.expense_id.in_(expense_ids)))
    for receipt in receipt_result.scalars().all():
        receipt.expense_id = None
        if receipt.bank_transaction_id:
            receipt.status = "matched_bank"
        elif receipt.cash_entry_id:
            receipt.status = "cash_expense"
        else:
            receipt.status = "new"


@router.post("/admin-hard-delete")
async def admin_hard_delete_expenses(
    data: ExpenseHardDeleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    expense_ids = sorted({expense_id for expense_id in data.ids if expense_id > 0})
    if not expense_ids:
        return {"ok": True, "deleted": 0, "ids": []}

    result = await db.execute(select(Expense).where(Expense.id.in_(expense_ids)))
    expenses = result.scalars().all()
    found_ids = {expense.id for expense in expenses}
    missing_ids = [expense_id for expense_id in expense_ids if expense_id not in found_ids]
    if missing_ids:
        raise HTTPException(404, f"Expense rows not found: {missing_ids}")
    if any(is_cash_transfer_expense(expense) for expense in expenses):
        raise HTTPException(400, "Cash transfer operations must be managed from bank or cash")

    await _admin_clear_expense_links(db, expense_ids)
    for expense in expenses:
        await db.delete(expense)

    await db.commit()
    return {"ok": True, "deleted": len(expenses), "ids": expense_ids}


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
        await db.execute(
            update(MonthlyObligation).where(MonthlyObligation.expense_id == expense.id).values(expense_id=None)
        )
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
