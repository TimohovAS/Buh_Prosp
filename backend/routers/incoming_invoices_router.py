"""CRUD и settlement-операции для входящих фактур."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.auth import get_current_user_required, require_edit_access
from backend.database import get_db
from backend.date_utils import days_between
from backend.decimal_utils import to_decimal
from backend.incoming_invoice_service import (
    INCOMING_INVOICE_SOURCE,
    attach_existing_expense,
    create_incoming_invoice,
    get_counterparty_balances,
    link_advance_invoice,
    list_advance_invoice_candidates,
    list_closing_invoice_candidates,
    reverse_settlement,
    restore_incoming_invoice,
    settle_via_bank,
    settle_via_cash,
    settle_via_offset,
    unlink_advance_invoice,
    update_incoming_invoice,
)
from backend.models import (
    BankTransaction,
    Client,
    Expense,
    Income,
    IncomingInvoice,
    IncomingInvoiceSettlement,
    User,
)
from backend.schemas import (
    BankSettlementCreate,
    CounterpartyBalanceItem,
    CounterpartyBalanceResponse,
    IncomingInvoiceAttachExpenseRequest,
    IncomingInvoiceAdvanceLinkRequest,
    IncomingInvoiceClosingLinkRequest,
    IncomingInvoiceCreate,
    IncomingInvoiceExpenseCandidateResponse,
    IncomingInvoiceDetailResponse,
    IncomingInvoiceLinkSummary,
    IncomingInvoiceResponse,
    IncomingInvoiceSettlementCreate,
    IncomingInvoiceSettlementResponse,
    IncomingInvoiceUpdate,
    OffsetSettlementCreate,
)
from backend.state_machine import InvalidStatusTransition, cancel_incoming_invoice

router = APIRouter(prefix="/incoming-invoices", tags=["incoming-invoices"])


def _serialize(invoice: IncomingInvoice) -> dict:
    d = IncomingInvoiceResponse.model_validate(invoice).model_dump()
    d["remaining_amount"] = float(invoice.remaining_amount)
    if invoice.client:
        d["client_name"] = invoice.client.name
    elif not d.get("client_name"):
        d["client_name"] = invoice.counterparty_name
    if invoice.project:
        d["project_name"] = invoice.project.name
        d["project_code"] = invoice.project.code
    return d


def _serialize_detail(invoice: IncomingInvoice) -> dict:
    d = _serialize(invoice)
    d["settlements"] = [
        IncomingInvoiceSettlementResponse.model_validate(s).model_dump()
        for s in (invoice.settlements or [])
    ]
    return d


def _serialize_link_summary(invoice: IncomingInvoice | None) -> dict | None:
    if not invoice:
        return None
    return IncomingInvoiceLinkSummary(
        id=invoice.id,
        invoice_number=invoice.invoice_number,
        date=invoice.date,
        amount=to_decimal(invoice.amount or 0),
        currency=invoice.currency or "RSD",
        status=invoice.status,
        counterparty_name=invoice.counterparty_name,
        client_name=invoice.client.name if invoice.client else None,
        project_id=invoice.project_id,
        project_name=invoice.project.name if invoice.project else None,
        project_code=invoice.project.code if invoice.project else None,
        description=invoice.description,
    ).model_dump()


async def _serialize_detail_with_links(db: AsyncSession, invoice: IncomingInvoice) -> dict:
    d = _serialize_detail(invoice)
    advance_invoice = None
    if invoice.advance_invoice_id:
        advance_result = await db.execute(
            select(IncomingInvoice)
            .options(selectinload(IncomingInvoice.client), selectinload(IncomingInvoice.project))
            .where(IncomingInvoice.id == invoice.advance_invoice_id)
        )
        advance_invoice = advance_result.scalar_one_or_none()
    closing_result = await db.execute(
        select(IncomingInvoice)
        .options(selectinload(IncomingInvoice.client), selectinload(IncomingInvoice.project))
        .where(IncomingInvoice.advance_invoice_id == invoice.id)
        .limit(1)
    )
    closing_invoice = closing_result.scalar_one_or_none()
    d["advance_invoice"] = _serialize_link_summary(advance_invoice)
    d["closing_invoice"] = _serialize_link_summary(closing_invoice)
    return d


def _serialize_expense_candidate(expense: Expense, bank_transaction: BankTransaction | None) -> dict:
    return IncomingInvoiceExpenseCandidateResponse(
        id=expense.id,
        date=expense.date,
        paid_date=expense.paid_date,
        description=expense.description,
        amount=abs(to_decimal(expense.amount or 0)),
        currency=expense.currency or "RSD",
        category=expense.category,
        category_id=expense.category_id,
        status=expense.status,
        source=expense.source,
        project_id=expense.project_id,
        project_name=expense.project.name if expense.project else None,
        project_code=expense.project.code if expense.project else None,
        contract_id=expense.contract_id,
        contract_number=expense.contract.number if expense.contract else None,
        bank_reference=expense.bank_reference,
        note=expense.note,
        bank_transaction_id=bank_transaction.id if bank_transaction else None,
        bank_counterparty_name=bank_transaction.counterparty_name if bank_transaction else None,
        bank_purpose=bank_transaction.purpose if bank_transaction else None,
    ).model_dump()


@router.get("")
async def list_incoming_invoices(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    client_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    q = (
        select(IncomingInvoice)
        .options(selectinload(IncomingInvoice.client), selectinload(IncomingInvoice.project))
        .order_by(IncomingInvoice.date.desc(), IncomingInvoice.id.desc())
    )
    if year:
        from datetime import date as dt_date
        q = q.where(IncomingInvoice.date >= dt_date(year, 1, 1), IncomingInvoice.date <= dt_date(year, 12, 31))
    if month and year:
        import calendar
        from datetime import date as dt_date
        last_day = calendar.monthrange(year, month)[1]
        q = q.where(IncomingInvoice.date >= dt_date(year, month, 1), IncomingInvoice.date <= dt_date(year, month, last_day))
    if client_id:
        q = q.where(IncomingInvoice.client_id == client_id)
    if status:
        q = q.where(IncomingInvoice.status == status)
    if search:
        term = f"%{search.strip().lower()}%"
        q = q.where(
            IncomingInvoice.invoice_number.ilike(term)
            | IncomingInvoice.counterparty_name.ilike(term)
            | IncomingInvoice.description.ilike(term)
        )
    result = await db.execute(q)
    items = result.scalars().all()
    return [_serialize(inv) for inv in items]


@router.get("/years", response_model=list[int])
async def list_incoming_invoice_years(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(func.distinct(func.strftime("%Y", IncomingInvoice.date)).label("year"))
        .where(IncomingInvoice.date.isnot(None))
        .order_by(func.strftime("%Y", IncomingInvoice.date).desc())
    )
    return [int(row.year) for row in result.fetchall() if row.year]


@router.post("", response_model=IncomingInvoiceResponse)
async def create_invoice(
    data: IncomingInvoiceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    invoice = await create_incoming_invoice(
        db,
        invoice_number=data.invoice_number,
        invoice_date=data.date,
        client_id=data.client_id,
        counterparty_name=data.counterparty_name,
        project_id=data.project_id,
        amount=data.amount,
        currency=data.currency,
        description=data.description,
        note=data.note,
        source=data.source,
        created_by=current_user.id,
    )
    await db.commit()
    await db.refresh(invoice, ["client", "project"])
    return _serialize(invoice)


@router.get("/counterparty-balance", response_model=CounterpartyBalanceResponse)
async def counterparty_balance(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    items = await get_counterparty_balances(db)
    total_r = sum((i["receivables"] for i in items), to_decimal(0))
    total_p = sum((i["payables"] for i in items), to_decimal(0))
    return CounterpartyBalanceResponse(
        items=[CounterpartyBalanceItem(**i) for i in items],
        total_receivables=total_r,
        total_payables=total_p,
        total_net_balance=total_r - total_p,
    )


@router.get("/open-incomes/{client_id}")
async def open_incomes_for_offset(
    client_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Открытые исходящие фактуры клиента для взаимозачёта."""
    result = await db.execute(
        select(Income)
        .options(selectinload(Income.client), selectinload(Income.project))
        .where(Income.client_id == client_id, Income.status.in_(["issued", "partial"]))
        .order_by(Income.issued_date.desc())
    )
    incomes = result.scalars().all()
    return [
        {
            "id": i.id,
            "invoice_number": i.invoice_number,
            "date": i.issued_date.isoformat() if i.issued_date else None,
            "amount": float(i.amount_rsd or 0),
            "paid_amount": float(i.paid_amount or 0),
            "remaining": float(to_decimal(i.amount_rsd or 0) - to_decimal(i.paid_amount or 0)),
            "status": i.status,
            "client_name": i.client.name if i.client else i.client_name,
            "project_name": i.project.name if i.project else None,
            "project_code": i.project.code if i.project else None,
            "description": i.description,
        }
        for i in incomes
    ]


@router.get("/{invoice_id}/expense-candidates", response_model=list[IncomingInvoiceExpenseCandidateResponse])
async def expense_candidates(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    invoice = await db.get(IncomingInvoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "IncomingInvoice not found.")

    linked_expenses_subquery = (
        select(IncomingInvoice.expense_id)
        .where(IncomingInvoice.id != invoice.id, IncomingInvoice.expense_id.is_not(None))
    )
    result = await db.execute(
        select(Expense)
        .options(selectinload(Expense.project), selectinload(Expense.contract))
        .where(
            Expense.status == "paid",
            Expense.reversal_of_id.is_(None),
            func.abs(Expense.amount) == abs(to_decimal(invoice.amount or 0)),
            Expense.id.not_in(linked_expenses_subquery),
        )
        .order_by(Expense.paid_date.desc(), Expense.date.desc(), Expense.id.desc())
    )
    expenses = [
        expense
        for expense in result.scalars().all()
        if expense.id != invoice.expense_id and getattr(expense, "reversed_expense_id", None) is None
    ]
    if not expenses:
        return []

    expense_ids = [expense.id for expense in expenses]
    tx_result = await db.execute(
        select(BankTransaction)
        .where(
            BankTransaction.matched_type == "expense",
            BankTransaction.matched_id.in_(expense_ids),
        )
        .order_by(BankTransaction.date.desc(), BankTransaction.id.desc())
    )
    transactions_by_expense: dict[int, BankTransaction] = {}
    for transaction in tx_result.scalars().all():
        if transaction.matched_id is None:
            continue
        transactions_by_expense.setdefault(int(transaction.matched_id), transaction)

    expenses.sort(
        key=lambda expense: (
            0 if expense.source == "bank_import" else 1,
            days_between(expense.paid_date or expense.date, invoice.date, absolute=True),
            days_between(expense.date, invoice.date, absolute=True),
            -int(expense.id),
        )
    )
    return [
        _serialize_expense_candidate(expense, transactions_by_expense.get(int(expense.id)))
        for expense in expenses
    ]


@router.get("/{invoice_id}/advance-candidates", response_model=list[IncomingInvoiceLinkSummary])
async def advance_candidates(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    invoice = await db.get(IncomingInvoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "IncomingInvoice not found.")
    try:
        items = await list_advance_invoice_candidates(db, invoice)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return [_serialize_link_summary(item) for item in items]


@router.get("/{invoice_id}/closing-candidates", response_model=list[IncomingInvoiceLinkSummary])
async def closing_candidates(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    invoice = await db.get(IncomingInvoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "IncomingInvoice not found.")
    try:
        items = await list_closing_invoice_candidates(db, invoice)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return [_serialize_link_summary(item) for item in items]


@router.get("/{invoice_id}")
async def get_invoice(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(IncomingInvoice)
        .options(
            selectinload(IncomingInvoice.client),
            selectinload(IncomingInvoice.project),
            selectinload(IncomingInvoice.advance_invoice),
            selectinload(IncomingInvoice.settlements),
        )
        .where(IncomingInvoice.id == invoice_id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(404, "IncomingInvoice not found.")
    return await _serialize_detail_with_links(db, invoice)


@router.post("/{invoice_id}/attach-expense", response_model=IncomingInvoiceResponse)
async def attach_expense(
    invoice_id: int,
    data: IncomingInvoiceAttachExpenseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    result = await db.execute(
        select(IncomingInvoice)
        .options(selectinload(IncomingInvoice.client), selectinload(IncomingInvoice.project))
        .where(IncomingInvoice.id == invoice_id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(404, "IncomingInvoice not found.")
    try:
        invoice = await attach_existing_expense(db, invoice, data.expense_id)
    except (InvalidStatusTransition, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    await db.refresh(invoice, ["client", "project"])
    return _serialize(invoice)


@router.patch("/{invoice_id}", response_model=IncomingInvoiceResponse)
async def update_invoice(
    invoice_id: int,
    data: IncomingInvoiceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    invoice = await db.get(IncomingInvoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "IncomingInvoice not found.")
    try:
        fields = data.model_dump(exclude_unset=True)
        await update_incoming_invoice(db, invoice, **fields)
    except InvalidStatusTransition as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    await db.refresh(invoice, ["client", "project"])
    return _serialize(invoice)


@router.post("/{invoice_id}/restore", response_model=IncomingInvoiceResponse)
async def restore_invoice(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    invoice = await db.get(IncomingInvoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "IncomingInvoice not found.")
    try:
        invoice = await restore_incoming_invoice(db, invoice)
    except (InvalidStatusTransition, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    await db.refresh(invoice, ["client", "project"])
    return _serialize(invoice)


@router.post("/{invoice_id}/link-advance", response_model=IncomingInvoiceResponse)
async def link_invoice_advance(
    invoice_id: int,
    data: IncomingInvoiceAdvanceLinkRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    invoice = await db.get(IncomingInvoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "IncomingInvoice not found.")
    try:
        invoice = await link_advance_invoice(db, closing_invoice=invoice, advance_invoice_id=data.advance_invoice_id)
    except (InvalidStatusTransition, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    await db.refresh(invoice, ["client", "project", "advance_invoice"])
    return _serialize(invoice)


@router.post("/{invoice_id}/link-closing", response_model=IncomingInvoiceResponse)
async def link_invoice_closing(
    invoice_id: int,
    data: IncomingInvoiceClosingLinkRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    invoice = await db.get(IncomingInvoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "IncomingInvoice not found.")
    closing_invoice = await db.get(IncomingInvoice, data.closing_invoice_id)
    if not closing_invoice:
        raise HTTPException(404, "Closing invoice not found.")
    try:
        await link_advance_invoice(db, closing_invoice=closing_invoice, advance_invoice_id=invoice.id)
    except (InvalidStatusTransition, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    await db.refresh(invoice, ["client", "project"])
    return _serialize(invoice)


@router.post("/{invoice_id}/unlink-advance", response_model=IncomingInvoiceResponse)
async def unlink_invoice_advance(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    invoice = await db.get(IncomingInvoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "IncomingInvoice not found.")
    try:
        closing_invoice = await unlink_advance_invoice(db, invoice)
    except (InvalidStatusTransition, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    await db.refresh(closing_invoice, ["client", "project", "advance_invoice"])
    return _serialize(closing_invoice)


@router.post("/{invoice_id}/cancel")
async def cancel_invoice(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Отмена входящей фактуры (статус cancelled), без физического удаления."""
    invoice = await db.get(IncomingInvoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "IncomingInvoice not found.")
    try:
        cancel_incoming_invoice(invoice)
    except InvalidStatusTransition as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return {"ok": True, "status": invoice.status}


@router.delete("/{invoice_id}", deprecated=True)
async def cancel_invoice_deprecated_delete(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Deprecated: используйте POST /incoming-invoices/{id}/cancel. Будет удалён."""
    invoice = await db.get(IncomingInvoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "IncomingInvoice not found.")
    try:
        cancel_incoming_invoice(invoice)
    except InvalidStatusTransition as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return {"ok": True, "status": invoice.status}


@router.post("/{invoice_id}/settle/bank", response_model=IncomingInvoiceSettlementResponse)
async def settle_bank(
    invoice_id: int,
    data: BankSettlementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    invoice = await db.get(IncomingInvoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "IncomingInvoice not found.")
    try:
        settlement = await settle_via_bank(
            db, invoice,
            bank_transaction_id=data.bank_transaction_id,
            amount=data.amount,
            settlement_date=data.date,
            note=data.note,
            created_by=current_user.id,
        )
    except (InvalidStatusTransition, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return IncomingInvoiceSettlementResponse.model_validate(settlement)


@router.post("/{invoice_id}/settle/cash", response_model=IncomingInvoiceSettlementResponse)
async def settle_cash(
    invoice_id: int,
    data: IncomingInvoiceSettlementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    invoice = await db.get(IncomingInvoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "IncomingInvoice not found.")
    try:
        settlement = await settle_via_cash(
            db, invoice,
            amount=data.amount,
            settlement_date=data.date,
            note=data.note,
            created_by=current_user.id,
        )
    except (InvalidStatusTransition, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return IncomingInvoiceSettlementResponse.model_validate(settlement)


@router.post("/{invoice_id}/settle/offset", response_model=IncomingInvoiceSettlementResponse)
async def settle_offset(
    invoice_id: int,
    data: OffsetSettlementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    invoice = await db.get(IncomingInvoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "IncomingInvoice not found.")
    try:
        settlement = await settle_via_offset(
            db, invoice,
            income_id=data.income_id,
            amount=data.amount,
            settlement_date=data.date,
            note=data.note,
            created_by=current_user.id,
        )
    except (InvalidStatusTransition, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return IncomingInvoiceSettlementResponse.model_validate(settlement)


@router.delete("/settlements/{settlement_id}")
async def delete_settlement(
    settlement_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    try:
        invoice = await reverse_settlement(db, settlement_id)
    except (InvalidStatusTransition, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return {"ok": True, "invoice_id": invoice.id, "status": invoice.status}
