from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.auth import get_current_user_required, require_edit_access
from backend.counterparty_loan_service import (
    add_movement_from_bank_transaction,
    create_loan_from_bank_transaction,
    get_loan,
    loan_totals,
)
from backend.database import get_db
from backend.decimal_utils import money_abs
from backend.models import BankTransaction, Client, CounterpartyLoan, CounterpartyLoanMovement, User
from backend.schemas import (
    CounterpartyLoanCreateFromBank,
    CounterpartyLoanMovementFromBank,
    CounterpartyLoanResponse,
    CounterpartyLoanUpdate,
    OwnerFundsMovementResponse,
)

router = APIRouter(prefix="/counterparty-loans", tags=["counterparty-loans"])

MATCH_TYPE_OWNER_FUNDS = "owner_funds"


def _serialize(loan: CounterpartyLoan) -> CounterpartyLoanResponse:
    disbursed, repaid, outstanding = loan_totals(loan)
    movements = []
    for movement in loan.movements or []:
        bank_transaction = movement.bank_transaction
        movements.append(
            {
                "id": movement.id,
                "loan_id": movement.loan_id,
                "movement_type": movement.movement_type,
                "date": movement.date,
                "amount": movement.amount,
                "currency": movement.currency or "RSD",
                "bank_transaction_id": movement.bank_transaction_id,
                "note": movement.note,
                "created_at": movement.created_at,
                "bank_reference": bank_transaction.bank_reference if bank_transaction else None,
                "bank_purpose": bank_transaction.purpose if bank_transaction else None,
            }
        )
    return CounterpartyLoanResponse(
        id=loan.id,
        loan_type=loan.loan_type,
        client_id=loan.client_id,
        client_name=loan.client.name if loan.client else None,
        counterparty_name=loan.counterparty_name,
        agreement_number=loan.agreement_number,
        agreement_date=loan.agreement_date,
        start_date=loan.start_date,
        due_date=loan.due_date,
        currency=loan.currency or "RSD",
        note=loan.note,
        status=loan.status,
        created_at=loan.created_at,
        disbursed_amount=disbursed,
        repaid_amount=repaid,
        outstanding_amount=outstanding,
        movements=movements,
    )


def _with_links():
    return (
        selectinload(CounterpartyLoan.client),
        selectinload(CounterpartyLoan.movements).selectinload(CounterpartyLoanMovement.bank_transaction),
    )


@router.get("", response_model=list[CounterpartyLoanResponse])
async def list_loans(
    loan_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    query = (
        select(CounterpartyLoan)
        .options(*_with_links())
        .order_by(CounterpartyLoan.start_date.desc(), CounterpartyLoan.id.desc())
    )
    if loan_type:
        query = query.where(CounterpartyLoan.loan_type == loan_type)
    if status:
        query = query.where(CounterpartyLoan.status == status)
    if search:
        term = f"%{search.strip()}%"
        query = query.outerjoin(Client).where(
            or_(
                CounterpartyLoan.counterparty_name.ilike(term),
                CounterpartyLoan.agreement_number.ilike(term),
                Client.name.ilike(term),
            )
        )
    result = await db.execute(query)
    return [_serialize(loan) for loan in result.scalars().all()]


@router.post("/from-bank/{tx_id}", response_model=CounterpartyLoanResponse)
async def create_from_bank(
    tx_id: int,
    data: CounterpartyLoanCreateFromBank,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    try:
        loan = await create_loan_from_bank_transaction(
            db,
            tx_id,
            loan_type=data.loan_type,
            client_id=data.client_id,
            counterparty_name=data.counterparty_name,
            agreement_number=data.agreement_number,
            agreement_date=data.agreement_date,
            due_date=data.due_date,
            note=data.note,
            created_by=current_user.id,
        )
        await db.commit()
        return _serialize(await get_loan(db, loan.id))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Bank transaction is already linked to a loan movement")


@router.get("/owner-funds", response_model=list[OwnerFundsMovementResponse])
async def list_owner_funds_movements(
    direction: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    query = (
        select(BankTransaction)
        .where(
            BankTransaction.status == "matched",
            BankTransaction.matched_type == MATCH_TYPE_OWNER_FUNDS,
        )
        .order_by(BankTransaction.date.desc(), BankTransaction.id.desc())
        .limit(limit)
    )
    if direction:
        query = query.where(BankTransaction.direction == direction)
    if search:
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                BankTransaction.counterparty_name.ilike(term),
                BankTransaction.purpose.ilike(term),
                BankTransaction.bank_reference.ilike(term),
            )
        )
    result = await db.execute(query)
    return [
        OwnerFundsMovementResponse(
            id=transaction.id,
            date=transaction.date,
            direction=transaction.direction,
            amount=money_abs(transaction.amount),
            currency=transaction.currency or "RSD",
            counterparty_name=transaction.counterparty_name,
            purpose=transaction.purpose,
            bank_reference=transaction.bank_reference,
            created_at=transaction.created_at,
        )
        for transaction in result.scalars().all()
    ]


@router.get("/{loan_id}", response_model=CounterpartyLoanResponse)
async def get_one_loan(
    loan_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    try:
        return _serialize(await get_loan(db, loan_id))
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.post("/{loan_id}/movements/from-bank/{tx_id}", response_model=CounterpartyLoanResponse)
async def add_movement_from_bank(
    loan_id: int,
    tx_id: int,
    data: CounterpartyLoanMovementFromBank,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    try:
        loan = await add_movement_from_bank_transaction(
            db,
            loan_id,
            tx_id,
            movement_type=data.movement_type,
            note=data.note,
            created_by=current_user.id,
        )
        await db.commit()
        return _serialize(await get_loan(db, loan.id))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Bank transaction is already linked to a loan movement")


@router.patch("/{loan_id}", response_model=CounterpartyLoanResponse)
async def update_loan(
    loan_id: int,
    data: CounterpartyLoanUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    try:
        loan = await get_loan(db, loan_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    payload = data.model_dump(exclude_unset=True)
    new_client_id = payload.get("client_id", loan.client_id)
    new_counterparty_name = payload.get("counterparty_name", loan.counterparty_name)
    if "client_id" in payload and payload["client_id"] is not None:
        client_result = await db.execute(select(Client).where(Client.id == payload["client_id"]))
        client = client_result.scalar_one_or_none()
        if not client:
            raise HTTPException(400, "Counterparty not found")
        if "counterparty_name" not in payload and payload["client_id"] != loan.client_id:
            new_counterparty_name = client.name
            payload["counterparty_name"] = new_counterparty_name
    if "counterparty_name" in payload and not (payload["counterparty_name"] or "").strip():
        raise HTTPException(400, "Counterparty name is required")
    if "counterparty_name" in payload:
        new_counterparty_name = payload["counterparty_name"].strip()
        payload["counterparty_name"] = new_counterparty_name
    if loan.movements and (new_client_id != loan.client_id or new_counterparty_name != loan.counterparty_name):
        raise HTTPException(400, "Counterparty cannot be changed after loan movements exist")
    for field, value in payload.items():
        setattr(loan, field, value)
    await db.commit()
    return _serialize(await get_loan(db, loan.id))


@router.post("/{loan_id}/cancel", response_model=CounterpartyLoanResponse)
async def cancel_loan(
    loan_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    try:
        loan = await get_loan(db, loan_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    if loan.status == "cancelled":
        raise HTTPException(400, "Loan is already cancelled")
    if loan.movements:
        raise HTTPException(400, "Loan with movements cannot be cancelled")
    loan.status = "cancelled"
    await db.commit()
    return _serialize(await get_loan(db, loan.id))
