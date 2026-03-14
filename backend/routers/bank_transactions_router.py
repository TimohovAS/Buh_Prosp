from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user_required, require_edit_access
from backend.bank_matching_service import match_transaction, suggest_matches, unmatch_transaction
from backend.cash_service import (
    CASH_CATEGORY,
    create_cash_transfer_from_transaction,
    get_or_create_cash_project_id,
    is_cash_transfer_expense,
)
from backend.database import get_db
from backend.decimal_utils import ZERO_DECIMAL, money_eq, to_decimal
from backend.models import BankTransaction, Contract, Expense, Income, Project, TransactionCategory, User
from backend.schemas import (
    BankTransactionBulkAssignProject,
    BankTransactionCreate,
    BankTransactionCreateExpenseRequest,
    BankTransactionResponse,
    BankTransactionUpdate,
    MatchCandidate,
    MatchRequest,
)
from backend.state_machine import InvalidStatusTransition, initialize_expense_status, mark_expense_paid

router = APIRouter(prefix="/bank-transactions", tags=["bank-transactions"])
_PROJECT_OVERRIDE_UNSET = object()


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


async def _get_category_or_404(db: AsyncSession, category_id: int) -> TransactionCategory:
    category_result = await db.execute(select(TransactionCategory).where(TransactionCategory.id == category_id))
    category = category_result.scalar_one_or_none()
    if not category:
        raise HTTPException(404, "Category not found")
    return category


async def _resolve_category_expense_links(
    db: AsyncSession,
    category_id: int | None,
    project_id: int | None,
    contract_id: int | None,
) -> tuple[int | None, int | None, bool]:
    if category_id is None:
        return project_id, contract_id, False

    category = await _get_category_or_404(db, category_id)
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


async def _sync_expense_project(db: AsyncSession, expense: Expense, project_id: int | None) -> None:
    expense.project_id = project_id
    if expense.contract_id is None or project_id is None:
        return
    contract = await _get_contract_or_404(db, expense.contract_id)
    if contract.project_id != project_id:
        expense.contract_id = None


async def _sync_income_project(db: AsyncSession, income: Income, project_id: int | None) -> None:
    income.project_id = project_id
    if income.contract_id is None or project_id is None:
        return

    contract = await _get_contract_or_404(db, income.contract_id)
    if contract.project_id is None:
        await _get_project_or_404(db, project_id)
        contract.project_id = project_id
        await db.flush()
        return

    if contract.project_id != project_id:
        income.contract_id = None
        income.contract_payment_type = None


async def _find_reusable_bank_import_expense(db: AsyncSession, transaction: BankTransaction) -> Expense | None:
    if not transaction.bank_reference:
        return None

    result = await db.execute(
        select(Expense)
        .where(
            Expense.source == "bank_import",
            Expense.status == "planned",
            Expense.bank_reference == transaction.bank_reference,
            Expense.reversal_of_id.is_(None),
        )
        .order_by(Expense.id.desc())
    )
    for expense in result.scalars().all():
        if getattr(expense, "reversed_expense_id", None):
            continue
        if not money_eq(expense.amount or ZERO_DECIMAL, transaction.amount or ZERO_DECIMAL):
            continue
        return expense
    return None


def _serialize_bank_transaction(
    transaction: BankTransaction,
    project_id: object = _PROJECT_OVERRIDE_UNSET,
) -> BankTransactionResponse:
    payload = BankTransactionResponse.model_validate(transaction).model_dump()
    if project_id is not _PROJECT_OVERRIDE_UNSET:
        payload["project_id"] = project_id
    return BankTransactionResponse.model_validate(payload)


async def _resolve_effective_project_ids(
    db: AsyncSession,
    transactions: list[BankTransaction],
) -> dict[int, int | None]:
    expense_ids = [tx.matched_id for tx in transactions if tx.matched_type == "expense" and tx.matched_id]
    income_ids = [tx.matched_id for tx in transactions if tx.matched_type == "income" and tx.matched_id]

    expense_projects: dict[int, int | None] = {}
    income_projects: dict[int, int | None] = {}

    if expense_ids:
        result = await db.execute(select(Expense.id, Expense.project_id).where(Expense.id.in_(expense_ids)))
        expense_projects = {int(expense_id): project_id for expense_id, project_id in result.fetchall()}

    if income_ids:
        result = await db.execute(select(Income.id, Income.project_id).where(Income.id.in_(income_ids)))
        income_projects = {int(income_id): project_id for income_id, project_id in result.fetchall()}

    resolved: dict[int, int | None] = {}
    for tx in transactions:
        project_id = tx.project_id
        if tx.matched_type == "expense" and tx.matched_id:
            project_id = expense_projects.get(int(tx.matched_id), project_id)
        elif tx.matched_type == "income" and tx.matched_id:
            project_id = income_projects.get(int(tx.matched_id), project_id)
        resolved[int(tx.id)] = project_id
    return resolved


async def _serialize_bank_transactions(
    db: AsyncSession,
    transactions: list[BankTransaction],
) -> list[BankTransactionResponse]:
    resolved_projects = await _resolve_effective_project_ids(db, transactions)
    return [
        _serialize_bank_transaction(transaction, resolved_projects.get(int(transaction.id), transaction.project_id))
        for transaction in transactions
    ]


async def _serialize_single_bank_transaction(
    db: AsyncSession,
    transaction: BankTransaction,
) -> BankTransactionResponse:
    resolved_projects = await _resolve_effective_project_ids(db, [transaction])
    return _serialize_bank_transaction(
        transaction,
        resolved_projects.get(int(transaction.id), transaction.project_id),
    )


@router.get("", response_model=list[BankTransactionResponse])
async def list_bank_transactions(
    status: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    query = select(BankTransaction)
    if status == "unmatched":
        query = query.where(BankTransaction.status.in_(["unmatched", "ignored"]))
    elif status:
        query = query.where(BankTransaction.status == status)
    if direction:
        query = query.where(BankTransaction.direction == direction)
    if year:
        query = query.where(BankTransaction.date >= date(year, 1, 1), BankTransaction.date <= date(year, 12, 31))
    if month and year:
        import calendar

        last_day = calendar.monthrange(year, month)[1]
        query = query.where(BankTransaction.date >= date(year, month, 1), BankTransaction.date <= date(year, month, last_day))
    query = query.order_by(desc(BankTransaction.date), desc(BankTransaction.id))
    result = await db.execute(query)
    items = list(result.scalars().all())
    return await _serialize_bank_transactions(db, items)


@router.get("/years", response_model=list[int])
async def list_bank_transaction_years(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    result = await db.execute(select(BankTransaction.date))
    years = {value.year for (value,) in result.fetchall() if value is not None}
    if not years:
        years.add(date.today().year)
    return sorted(years, reverse=True)


@router.post("", response_model=BankTransactionResponse)
async def create_bank_transaction(
    data: BankTransactionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    transaction = BankTransaction(**data.model_dump())
    db.add(transaction)
    await db.commit()
    await db.refresh(transaction)
    return BankTransactionResponse.model_validate(transaction)


@router.get("/{tx_id}", response_model=BankTransactionResponse)
async def get_bank_transaction(
    tx_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    result = await db.execute(select(BankTransaction).where(BankTransaction.id == tx_id))
    transaction = result.scalar_one_or_none()
    if not transaction:
        raise HTTPException(404, "Transaction not found")
    return await _serialize_single_bank_transaction(db, transaction)


@router.patch("/{tx_id}", response_model=BankTransactionResponse)
async def update_bank_transaction(
    tx_id: int,
    data: BankTransactionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    result = await db.execute(select(BankTransaction).where(BankTransaction.id == tx_id))
    transaction = result.scalar_one_or_none()
    if not transaction:
        raise HTTPException(404, "Transaction not found")

    payload = data.model_dump(exclude_unset=True)
    if "project_id" in payload and not payload["project_id"]:
        payload["project_id"] = await _get_unassigned_project_id(db)
    if payload.get("project_id") is not None:
        await _get_project_or_404(db, payload["project_id"])

    for key, value in payload.items():
        setattr(transaction, key, value)

    if "project_id" in payload and transaction.matched_id:
        if transaction.matched_type == "expense":
            expense_result = await db.execute(select(Expense).where(Expense.id == transaction.matched_id))
            expense = expense_result.scalar_one_or_none()
            if expense:
                if is_cash_transfer_expense(expense):
                    cash_project_id = await get_or_create_cash_project_id(db)
                    payload["project_id"] = cash_project_id
                    transaction.project_id = cash_project_id
                    expense.contract_id = None
                    await _sync_expense_project(db, expense, cash_project_id)
                else:
                    await _sync_expense_project(db, expense, payload["project_id"])
        elif transaction.matched_type == "income":
            income_result = await db.execute(select(Income).where(Income.id == transaction.matched_id))
            income = income_result.scalar_one_or_none()
            if income:
                await _sync_income_project(db, income, payload["project_id"])

    await db.commit()
    await db.refresh(transaction)
    return await _serialize_single_bank_transaction(db, transaction)


@router.get("/{tx_id}/suggest", response_model=list[MatchCandidate])
async def get_suggested_matches(
    tx_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    result = await db.execute(select(BankTransaction).where(BankTransaction.id == tx_id))
    transaction = result.scalar_one_or_none()
    if not transaction:
        raise HTTPException(404, "Transaction not found")
    return await suggest_matches(db, transaction)


@router.post("/{tx_id}/match", response_model=BankTransactionResponse)
async def apply_match(
    tx_id: int,
    body: MatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    try:
        transaction = await match_transaction(db, tx_id, body.type, body.id)
        await db.commit()
        await db.refresh(transaction)
        return await _serialize_single_bank_transaction(db, transaction)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/{tx_id}/create-expense")
async def create_expense_from_transaction(
    tx_id: int,
    data: BankTransactionCreateExpenseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    result = await db.execute(select(BankTransaction).where(BankTransaction.id == tx_id))
    transaction = result.scalar_one_or_none()
    if not transaction:
        raise HTTPException(404, "Transaction not found")
    if transaction.direction != "out":
        raise HTTPException(400, "Expense can only be created from an outgoing transaction")
    if transaction.status not in {"unmatched", "ignored"}:
        raise HTTPException(400, "Transaction is already matched")

    category_name = None
    is_cash_transfer = data.category == CASH_CATEGORY
    project_id: int | None = None
    contract_id: int | None = None
    selected_category: TransactionCategory | None = None
    is_tax_related = False
    if data.category_id is not None:
        selected_category = await _get_category_or_404(db, data.category_id)
        category_name = selected_category.name_ru

    if not is_cash_transfer:
        project_id, contract_id, is_tax_related = await _resolve_category_expense_links(
            db,
            data.category_id,
            data.project_id or transaction.project_id,
            data.contract_id,
        )
        project_id, contract_id = await _resolve_expense_links(
            db,
            project_id,
            contract_id,
        )

    description = (
        data.description
        or transaction.purpose
        or transaction.counterparty_name
        or transaction.bank_reference
        or f"Bank transaction #{transaction.id}"
    ).strip()
    if not description:
        description = f"Bank transaction #{transaction.id}"

    if is_cash_transfer:
        try:
            expense, _ = await create_cash_transfer_from_transaction(
                db,
                transaction,
                project_id=None,
                contract_id=None,
                description=description,
                note=data.note,
                created_by=current_user.id,
            )
            await db.commit()
            await db.refresh(transaction)
            return {
                "expense_id": expense.id,
                "transaction": (await _serialize_single_bank_transaction(db, transaction)).model_dump(),
            }
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    expense = await _find_reusable_bank_import_expense(db, transaction)
    if expense:
        expense.date = data.date or transaction.date
        expense.description = description[:500]
        expense.amount = to_decimal(transaction.amount or ZERO_DECIMAL)
        expense.currency = transaction.currency or "RSD"
        expense.category = category_name
        expense.category_id = data.category_id
        expense.contract_id = contract_id
        expense.is_tax_related = is_tax_related
        expense.bank_reference = transaction.bank_reference
        try:
            mark_expense_paid(expense, paid_date=transaction.date, allow_same=True)
        except InvalidStatusTransition as exc:
            raise HTTPException(400, str(exc)) from exc
        expense.note = data.note
        expense.project_id = project_id
    else:
        expense = Expense(
            date=data.date or transaction.date,
            description=description[:500],
            amount=to_decimal(transaction.amount or ZERO_DECIMAL),
            currency=transaction.currency or "RSD",
            category=category_name,
            category_id=data.category_id,
            contract_id=contract_id,
            bank_reference=transaction.bank_reference,
            is_tax_related=is_tax_related,
            source="bank_import",
            note=data.note,
            project_id=project_id,
            created_by=current_user.id,
        )
        try:
            initialize_expense_status(expense, "paid", paid_date=transaction.date)
        except InvalidStatusTransition as exc:
            raise HTTPException(400, str(exc)) from exc
        db.add(expense)
    await db.flush()

    transaction.status = "matched"
    transaction.matched_type = "expense"
    transaction.matched_id = expense.id
    transaction.project_id = project_id

    await db.commit()
    await db.refresh(transaction)
    return {
        "expense_id": expense.id,
        "transaction": (await _serialize_single_bank_transaction(db, transaction)).model_dump(),
    }


@router.post("/{tx_id}/unmatch", response_model=BankTransactionResponse)
async def revert_match(
    tx_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    try:
        transaction = await unmatch_transaction(db, tx_id, current_user.id)
        await db.commit()
        await db.refresh(transaction)
        return await _serialize_single_bank_transaction(db, transaction)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/bulk-assign-project")
async def bulk_assign_project(
    data: BankTransactionBulkAssignProject,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    project_id = data.project_id
    if project_id is None:
        project_id = await _get_unassigned_project_id(db)
    if project_id is not None:
        await _get_project_or_404(db, project_id)

    result = await db.execute(select(BankTransaction).where(BankTransaction.id.in_(data.ids)))
    items = result.scalars().all()
    for item in items:
        if item.matched_type == "expense" and item.matched_id:
            expense_result = await db.execute(select(Expense).where(Expense.id == item.matched_id))
            expense = expense_result.scalar_one_or_none()
            if expense:
                if is_cash_transfer_expense(expense):
                    cash_project_id = await get_or_create_cash_project_id(db)
                    item.project_id = cash_project_id
                    expense.contract_id = None
                    await _sync_expense_project(db, expense, cash_project_id)
                else:
                    item.project_id = project_id
                    await _sync_expense_project(db, expense, project_id)
        elif item.matched_type == "income" and item.matched_id:
            item.project_id = project_id
            income_result = await db.execute(select(Income).where(Income.id == item.matched_id))
            income = income_result.scalar_one_or_none()
            if income:
                await _sync_income_project(db, income, project_id)
        else:
            item.project_id = project_id

    await db.commit()
    return {"message": f"Project assigned to {len(items)} transactions"}


