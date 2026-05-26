from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.decimal_utils import ZERO_DECIMAL, money_abs, to_decimal
from backend.models import BankTransaction, Client, CounterpartyLoan, CounterpartyLoanMovement

LOAN_TYPE_BORROWED = "borrowed"
LOAN_TYPE_ISSUED = "issued"
LOAN_TYPES = {LOAN_TYPE_BORROWED, LOAN_TYPE_ISSUED}
LOAN_MOVEMENT_DISBURSEMENT = "disbursement"
LOAN_MOVEMENT_REPAYMENT = "repayment"
LOAN_MOVEMENT_TYPES = {LOAN_MOVEMENT_DISBURSEMENT, LOAN_MOVEMENT_REPAYMENT}
MATCH_TYPE_LOAN_MOVEMENT = "loan_movement"


def loan_totals(loan: CounterpartyLoan, *, exclude_movement_id: int | None = None) -> tuple[Decimal, Decimal, Decimal]:
    disbursed = ZERO_DECIMAL
    repaid = ZERO_DECIMAL
    for movement in loan.movements or []:
        if exclude_movement_id is not None and int(movement.id) == int(exclude_movement_id):
            continue
        amount = to_decimal(movement.amount or ZERO_DECIMAL)
        if movement.movement_type == LOAN_MOVEMENT_DISBURSEMENT:
            disbursed += amount
        elif movement.movement_type == LOAN_MOVEMENT_REPAYMENT:
            repaid += amount
    return disbursed, repaid, disbursed - repaid


def _expected_direction(loan_type: str, movement_type: str) -> str:
    if loan_type not in LOAN_TYPES:
        raise ValueError("Unsupported loan type")
    if movement_type not in LOAN_MOVEMENT_TYPES:
        raise ValueError("Unsupported loan movement type")
    if loan_type == LOAN_TYPE_BORROWED:
        return "in" if movement_type == LOAN_MOVEMENT_DISBURSEMENT else "out"
    return "out" if movement_type == LOAN_MOVEMENT_DISBURSEMENT else "in"


async def get_loan(db: AsyncSession, loan_id: int) -> CounterpartyLoan:
    result = await db.execute(
        select(CounterpartyLoan)
        .options(
            selectinload(CounterpartyLoan.client),
            selectinload(CounterpartyLoan.movements).selectinload(CounterpartyLoanMovement.bank_transaction),
        )
        .where(CounterpartyLoan.id == loan_id)
        .execution_options(populate_existing=True)
    )
    loan = result.scalar_one_or_none()
    if not loan:
        raise ValueError("Loan not found")
    return loan


async def _get_bank_transaction(db: AsyncSession, tx_id: int) -> BankTransaction:
    result = await db.execute(select(BankTransaction).where(BankTransaction.id == tx_id))
    transaction = result.scalar_one_or_none()
    if not transaction:
        raise ValueError("Bank transaction not found")
    if transaction.status not in {"unmatched", "ignored"}:
        raise ValueError("Bank transaction is already matched")
    if money_abs(transaction.amount or ZERO_DECIMAL) <= ZERO_DECIMAL:
        raise ValueError("Loan movement amount must be greater than zero")
    return transaction


async def _resolve_counterparty_name(
    db: AsyncSession,
    client_id: int | None,
    requested_name: str | None,
    transaction_name: str | None,
) -> str:
    if client_id is not None:
        client_result = await db.execute(select(Client).where(Client.id == client_id))
        client = client_result.scalar_one_or_none()
        if not client:
            raise ValueError("Counterparty not found")
        return (requested_name or client.name).strip()
    name = (requested_name or transaction_name or "").strip()
    if not name:
        raise ValueError("Counterparty name is required")
    return name


async def reconcile_loan_status(db: AsyncSession, loan: CounterpartyLoan, *, exclude_movement_id: int | None = None) -> None:
    _, _, outstanding = loan_totals(loan, exclude_movement_id=exclude_movement_id)
    # Final invariant: no mutation path may leave a loan over-repaid.
    if outstanding < ZERO_DECIMAL:
        raise ValueError("Repayment cannot exceed outstanding loan amount")
    if loan.status != "cancelled":
        remaining_movements = [
            movement for movement in (loan.movements or [])
            if exclude_movement_id is None or int(movement.id) != int(exclude_movement_id)
        ]
        loan.status = "repaid" if outstanding == ZERO_DECIMAL and remaining_movements else "open"
    await db.flush()


async def _add_movement(
    db: AsyncSession,
    loan: CounterpartyLoan,
    transaction: BankTransaction,
    movement_type: str,
    *,
    note: str | None,
    created_by: int | None,
) -> CounterpartyLoanMovement:
    if loan.status != "open":
        raise ValueError("Only open loans can receive movements")
    expected_direction = _expected_direction(loan.loan_type, movement_type)
    if transaction.direction != expected_direction:
        raise ValueError("Bank transaction direction does not match this loan movement")
    if (transaction.currency or "RSD") != (loan.currency or "RSD"):
        raise ValueError("Bank transaction currency does not match loan currency")

    amount = money_abs(transaction.amount or ZERO_DECIMAL)
    _, _, outstanding = loan_totals(loan)
    if movement_type == LOAN_MOVEMENT_REPAYMENT and amount > outstanding:
        raise ValueError("Repayment cannot exceed outstanding loan amount")

    movement = CounterpartyLoanMovement(
        loan_id=loan.id,
        movement_type=movement_type,
        date=transaction.date,
        amount=amount,
        currency=transaction.currency or "RSD",
        bank_transaction_id=transaction.id,
        note=note,
        created_by=created_by,
    )
    db.add(movement)
    await db.flush()

    transaction.status = "matched"
    transaction.matched_type = MATCH_TYPE_LOAN_MOVEMENT
    transaction.matched_id = movement.id
    transaction.project_id = None
    await db.flush()

    loan.movements.append(movement)
    await reconcile_loan_status(db, loan)
    return movement


async def create_loan_from_bank_transaction(
    db: AsyncSession,
    tx_id: int,
    *,
    loan_type: str,
    client_id: int | None,
    counterparty_name: str | None,
    agreement_number: str | None,
    agreement_date,
    due_date,
    note: str | None,
    created_by: int | None,
) -> CounterpartyLoan:
    if loan_type not in LOAN_TYPES:
        raise ValueError("Unsupported loan type")
    transaction = await _get_bank_transaction(db, tx_id)
    expected_direction = _expected_direction(loan_type, LOAN_MOVEMENT_DISBURSEMENT)
    if transaction.direction != expected_direction:
        raise ValueError("Bank transaction direction does not match loan type")
    name = await _resolve_counterparty_name(db, client_id, counterparty_name, transaction.counterparty_name)

    loan = CounterpartyLoan(
        loan_type=loan_type,
        client_id=client_id,
        counterparty_name=name,
        agreement_number=(agreement_number or "").strip() or None,
        agreement_date=agreement_date,
        start_date=transaction.date,
        due_date=due_date,
        currency=transaction.currency or "RSD",
        note=note,
        status="open",
        created_by=created_by,
        movements=[],
    )
    db.add(loan)
    await db.flush()
    await _add_movement(
        db,
        loan,
        transaction,
        LOAN_MOVEMENT_DISBURSEMENT,
        note=None,
        created_by=created_by,
    )
    return loan


async def add_movement_from_bank_transaction(
    db: AsyncSession,
    loan_id: int,
    tx_id: int,
    *,
    movement_type: str,
    note: str | None,
    created_by: int | None,
) -> CounterpartyLoan:
    loan = await get_loan(db, loan_id)
    transaction = await _get_bank_transaction(db, tx_id)
    await _add_movement(
        db,
        loan,
        transaction,
        movement_type,
        note=note,
        created_by=created_by,
    )
    return loan


async def unmatch_loan_movement(db: AsyncSession, transaction: BankTransaction) -> None:
    if not transaction.matched_id:
        raise ValueError("Loan movement link is missing")
    movement_result = await db.execute(
        select(CounterpartyLoanMovement)
        .options(selectinload(CounterpartyLoanMovement.loan).selectinload(CounterpartyLoan.movements))
        .where(CounterpartyLoanMovement.id == transaction.matched_id)
    )
    movement = movement_result.scalar_one_or_none()
    if not movement or movement.bank_transaction_id != transaction.id:
        raise ValueError("Linked loan movement not found")

    loan = movement.loan
    _, _, outstanding_after_unmatch = loan_totals(loan, exclude_movement_id=movement.id)
    if outstanding_after_unmatch < ZERO_DECIMAL:
        raise ValueError("Cannot unlink this transaction while later repayments depend on it")

    await db.delete(movement)
    await db.flush()
    await reconcile_loan_status(db, loan, exclude_movement_id=movement.id)
