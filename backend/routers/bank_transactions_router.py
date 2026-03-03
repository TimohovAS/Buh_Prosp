"""Роутер банковских транзакций (BankTransaction)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from backend.database import get_db
from backend.models import BankTransaction, User
from backend.schemas import (
    BankTransactionCreate, 
    BankTransactionUpdate, 
    BankTransactionResponse,
    MatchCandidate,
    MatchRequest
)
from backend.auth import get_current_user_required, require_edit_access
from backend.bank_matching_service import suggest_matches, match_transaction, unmatch_transaction

router = APIRouter(prefix="/bank-transactions", tags=["bank-transactions"])


@router.get("", response_model=list[BankTransactionResponse])
async def list_bank_transactions(
    status: Optional[str] = Query(None, description="Фильтр по статусу (unmatched, matched, ignored)"),
    direction: Optional[str] = Query(None, description="Фильтр по направлению (in, out)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Список банковских транзакций."""
    q = select(BankTransaction)
    if status:
        q = q.where(BankTransaction.status == status)
    if direction:
        q = q.where(BankTransaction.direction == direction)
    q = q.order_by(desc(BankTransaction.date), desc(BankTransaction.id))
    result = await db.execute(q)
    return [BankTransactionResponse.model_validate(t) for t in result.scalars().all()]


@router.post("", response_model=BankTransactionResponse)
async def create_bank_transaction(
    data: BankTransactionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Добавить банковскую транзакцию вручную."""
    transaction = BankTransaction(**data.model_dump())
    db.add(transaction)
    await db.flush()
    await db.refresh(transaction)
    return BankTransactionResponse.model_validate(transaction)


@router.get("/{tx_id}", response_model=BankTransactionResponse)
async def get_bank_transaction(
    tx_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Получить транзакцию."""
    r = await db.execute(select(BankTransaction).where(BankTransaction.id == tx_id))
    tx = r.scalar_one_or_none()
    if not tx:
        raise HTTPException(404, "Транзакция не найдена")
    return BankTransactionResponse.model_validate(tx)


@router.patch("/{tx_id}", response_model=BankTransactionResponse)
async def update_bank_transaction(
    tx_id: int,
    data: BankTransactionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Обновить транзакцию (например, изменить статус матчинга)."""
    r = await db.execute(select(BankTransaction).where(BankTransaction.id == tx_id))
    tx = r.scalar_one_or_none()
    if not tx:
        raise HTTPException(404, "Транзакция не найдена")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(tx, k, v)
    await db.flush()
    await db.refresh(tx)
    return BankTransactionResponse.model_validate(tx)


@router.get("/{tx_id}/suggest", response_model=list[MatchCandidate])
async def get_suggested_matches(
    tx_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Предложить подходящие счета/документы для транзакции."""
    r = await db.execute(select(BankTransaction).where(BankTransaction.id == tx_id))
    tx = r.scalar_one_or_none()
    if not tx:
        raise HTTPException(404, "Транзакция не найдена")
    
    candidates = await suggest_matches(db, tx)
    return candidates


@router.post("/{tx_id}/match", response_model=BankTransactionResponse)
async def apply_match(
    tx_id: int,
    body: MatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Сопоставить банковскую транзакцию с документом."""
    try:
        tx = await match_transaction(db, tx_id, body.type, body.id)
        # SQLAlchemy may not return a fresh model immediately after status updates, 
        # so we refresh it before responding.
        await db.refresh(tx)
        return BankTransactionResponse.model_validate(tx)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{tx_id}/unmatch", response_model=BankTransactionResponse)
async def revert_match(
    tx_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Отменить сопоставление банковской транзакции."""
    try:
        tx = await unmatch_transaction(db, tx_id)
        await db.refresh(tx)
        return BankTransactionResponse.model_validate(tx)
    except ValueError as e:
        raise HTTPException(400, str(e))
