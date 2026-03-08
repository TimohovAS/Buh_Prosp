from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user_required, require_edit_access
from backend.bank_matching_service import match_transaction, suggest_matches, unmatch_transaction
from backend.database import get_db
from backend.models import BankTransaction, Expense, Project, TransactionCategory, User
from backend.schemas import (
    BankTransactionBulkAssignProject,
    BankTransactionCreate,
    BankTransactionCreateExpenseRequest,
    BankTransactionResponse,
    BankTransactionUpdate,
    MatchCandidate,
    MatchRequest,
)

router = APIRouter(prefix='/bank-transactions', tags=['bank-transactions'])


async def _get_unassigned_project_id(db: AsyncSession) -> int | None:
    response = await db.execute(select(Project).where(Project.code == 'INT-UNASSIGNED'))
    project = response.scalar_one_or_none()
    return project.id if project else None


@router.get('', response_model=list[BankTransactionResponse])
async def list_bank_transactions(
    status: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    query = select(BankTransaction)
    if status:
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
    return [BankTransactionResponse.model_validate(item) for item in result.scalars().all()]


@router.post('', response_model=BankTransactionResponse)
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


@router.get('/{tx_id}', response_model=BankTransactionResponse)
async def get_bank_transaction(
    tx_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    result = await db.execute(select(BankTransaction).where(BankTransaction.id == tx_id))
    transaction = result.scalar_one_or_none()
    if not transaction:
        raise HTTPException(404, 'Транзакция не найдена')
    return BankTransactionResponse.model_validate(transaction)


@router.patch('/{tx_id}', response_model=BankTransactionResponse)
async def update_bank_transaction(
    tx_id: int,
    data: BankTransactionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    result = await db.execute(select(BankTransaction).where(BankTransaction.id == tx_id))
    transaction = result.scalar_one_or_none()
    if not transaction:
        raise HTTPException(404, 'Транзакция не найдена')

    payload = data.model_dump(exclude_unset=True)
    for key, value in payload.items():
        setattr(transaction, key, value)

    if 'project_id' in payload and transaction.matched_type == 'expense' and transaction.matched_id:
        expense_result = await db.execute(select(Expense).where(Expense.id == transaction.matched_id))
        expense = expense_result.scalar_one_or_none()
        if expense:
            expense.project_id = payload['project_id']

    await db.commit()
    await db.refresh(transaction)
    return BankTransactionResponse.model_validate(transaction)


@router.get('/{tx_id}/suggest', response_model=list[MatchCandidate])
async def get_suggested_matches(
    tx_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    result = await db.execute(select(BankTransaction).where(BankTransaction.id == tx_id))
    transaction = result.scalar_one_or_none()
    if not transaction:
        raise HTTPException(404, 'Транзакция не найдена')
    return await suggest_matches(db, transaction)


@router.post('/{tx_id}/match', response_model=BankTransactionResponse)
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
        return BankTransactionResponse.model_validate(transaction)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post('/{tx_id}/create-expense')
async def create_expense_from_transaction(
    tx_id: int,
    data: BankTransactionCreateExpenseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    result = await db.execute(select(BankTransaction).where(BankTransaction.id == tx_id))
    transaction = result.scalar_one_or_none()
    if not transaction:
        raise HTTPException(404, 'Транзакция не найдена')
    if transaction.direction != 'out':
        raise HTTPException(400, 'Расход можно создать только из исходящей транзакции')
    if transaction.status != 'unmatched':
        raise HTTPException(400, 'Транзакция уже сопоставлена или проигнорирована')

    project_id = data.project_id or transaction.project_id or await _get_unassigned_project_id(db)
    if project_id is not None:
        project_result = await db.execute(select(Project).where(Project.id == project_id))
        project = project_result.scalar_one_or_none()
        if not project:
            raise HTTPException(404, 'Проект не найден')
        if project.status == 'archived':
            raise HTTPException(400, 'Нельзя использовать архивный проект')

    category_name = None
    if data.category_id is not None:
        category_result = await db.execute(select(TransactionCategory).where(TransactionCategory.id == data.category_id))
        category = category_result.scalar_one_or_none()
        if not category:
            raise HTTPException(404, 'Категория не найдена')
        category_name = category.name_ru

    description = (data.description or transaction.purpose or transaction.counterparty_name or transaction.bank_reference or f'Bank transaction #{transaction.id}').strip()
    if not description:
        description = f'Bank transaction #{transaction.id}'

    expense = Expense(
        date=data.date or transaction.date,
        description=description[:500],
        amount=float(transaction.amount or 0),
        currency=transaction.currency or 'RSD',
        category=category_name,
        category_id=data.category_id,
        bank_reference=transaction.bank_reference,
        paid_date=transaction.date,
        status='paid',
        source='bank_import',
        note=data.note,
        project_id=project_id,
        created_by=current_user.id,
    )
    db.add(expense)
    await db.flush()

    transaction.status = 'matched'
    transaction.matched_type = 'expense'
    transaction.matched_id = expense.id
    transaction.project_id = project_id

    await db.commit()
    await db.refresh(transaction)
    return {
        'expense_id': expense.id,
        'transaction': BankTransactionResponse.model_validate(transaction).model_dump(),
    }


@router.post('/{tx_id}/unmatch', response_model=BankTransactionResponse)
async def revert_match(
    tx_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    try:
        transaction = await unmatch_transaction(db, tx_id)
        await db.commit()
        await db.refresh(transaction)
        return BankTransactionResponse.model_validate(transaction)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post('/bulk-assign-project')
async def bulk_assign_project(
    data: BankTransactionBulkAssignProject,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    if data.project_id is not None:
        result = await db.execute(select(Project).where(Project.id == data.project_id))
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(404, 'Проект не найден')

    result = await db.execute(select(BankTransaction).where(BankTransaction.id.in_(data.ids)))
    items = result.scalars().all()

    for item in items:
        item.project_id = data.project_id
        if item.matched_type == 'expense' and item.matched_id:
            expense_result = await db.execute(select(Expense).where(Expense.id == item.matched_id))
            expense = expense_result.scalar_one_or_none()
            if expense:
                expense.project_id = data.project_id

    await db.commit()
    return {'message': f'Проект назначен {len(items)} транзакциям'}
