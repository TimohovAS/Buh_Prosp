"""CRUD и settlement-операции для входящих фактур."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.auth import get_current_user_required, require_edit_access
from backend.database import get_db
from backend.decimal_utils import to_decimal
from backend.incoming_invoice_service import (
    INCOMING_INVOICE_SOURCE,
    create_incoming_invoice,
    get_counterparty_balances,
    reverse_settlement,
    settle_via_bank,
    settle_via_cash,
    settle_via_offset,
    update_incoming_invoice,
)
from backend.models import (
    Client,
    Income,
    IncomingInvoice,
    IncomingInvoiceSettlement,
    User,
)
from backend.schemas import (
    BankSettlementCreate,
    CounterpartyBalanceItem,
    CounterpartyBalanceResponse,
    IncomingInvoiceCreate,
    IncomingInvoiceDetailResponse,
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
        }
        for i in incomes
    ]


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
            selectinload(IncomingInvoice.settlements),
        )
        .where(IncomingInvoice.id == invoice_id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(404, "IncomingInvoice not found.")
    return _serialize_detail(invoice)


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
