"""Р РѕСѓС‚РµСЂ РґРѕС…РѕРґРѕРІ (РљРџРћ)."""
from datetime import date
from typing import Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from backend.database import get_db
from backend.db_utils import (
    get_contract_or_404,
    get_project_or_404,
    get_unassigned_project_id,
)
from backend.models import Income, IncomeItem, Client, User, Project, BankTransaction, BankTransactionIncomeAllocation, Contract, ContractItem, Enterprise
from backend.schemas import (
    IncomeCreate,
    IncomeUpdate,
    IncomeResponse,
    IncomeItemCreate,
    IncomeItemSuggestion,
    BulkAssignProject,
    IncomePaymentDetailsResponse,
    IncomePaymentTransactionResponse,
)
from backend.auth import get_current_user_required, require_edit_access
from backend.bank_matching_service import detach_income_transaction_link, get_income_linked_payment_entries
from backend.services import get_next_invoice_number, allocate_next_invoice_number
from backend.decimal_utils import ZERO_DECIMAL, decimal_sum, to_decimal
from backend.invoice_export_service import build_income_efaktura_xml
from backend.state_machine import (
    InvalidStatusTransition,
    cancel_income,
    initialize_income_status,
    reconcile_income_payment_state,
    transition_income_status,
)

router = APIRouter(prefix="/income", tags=["income"])

INVOICE_DUPLICATE_DETAIL = "Invoice number already exists for this year."
INVOICE_ALLOCATE_DETAIL = "Could not allocate a unique invoice number for this year."
EFAKTURA_IMPORT_SOURCE = "efaktura_import"

async def _resolve_income_links(
    db: AsyncSession,
    project_id: int | None,
    contract_id: int | None,
) -> tuple[int | None, int | None]:
    resolved_project_id = project_id or await get_unassigned_project_id(db)
    resolved_contract_id = contract_id

    if resolved_contract_id is not None:
        contract = await get_contract_or_404(db, resolved_contract_id)
        if contract.project_id is None:
            if resolved_project_id is None:
                raise HTTPException(400, "Select a project before linking this contract")
            await get_project_or_404(db, resolved_project_id)
            contract.project_id = resolved_project_id
            await db.flush()
        resolved_project_id = contract.project_id

    if resolved_project_id is not None:
        await get_project_or_404(db, resolved_project_id)

    return resolved_project_id, resolved_contract_id


async def _clear_contract_if_project_mismatch(db: AsyncSession, income: Income, project_id: int | None) -> None:
    if not income.contract_id or project_id is None:
        return
    contract = await get_contract_or_404(db, income.contract_id)
    if contract.project_id != project_id:
        income.contract_id = None
        income.contract_payment_type = None


def _build_income_payment_details(income: Income, linked_transactions: list[dict]) -> IncomePaymentDetailsResponse:
    linked_total = decimal_sum([tx.get("amount", ZERO_DECIMAL) for tx in linked_transactions])
    recorded_paid = to_decimal(income.paid_amount or ZERO_DECIMAL)
    manual_paid_amount = max(ZERO_DECIMAL, recorded_paid - linked_total)
    has_manual_payment = manual_paid_amount > ZERO_DECIMAL or (
        linked_total == 0 and (income.status in ("paid", "partial") or bool(income.is_paid) or income.paid_date is not None or recorded_paid > 0)
    )
    if has_manual_payment and manual_paid_amount <= 0:
        if recorded_paid > ZERO_DECIMAL:
            manual_paid_amount = recorded_paid
        elif income.status == "paid":
            manual_paid_amount = to_decimal(income.amount_rsd or ZERO_DECIMAL)
    manual_paid_date = income.paid_date if has_manual_payment else None
    return IncomePaymentDetailsResponse(
        income_id=income.id,
        status=income.status,
        amount_rsd=to_decimal(income.amount_rsd or ZERO_DECIMAL),
        paid_amount=to_decimal(recorded_paid),
        paid_date=income.paid_date,
        linked_total=to_decimal(linked_total),
        manual_paid_amount=to_decimal(manual_paid_amount),
        manual_paid_date=manual_paid_date,
        has_manual_payment=has_manual_payment,
        linked_transactions=[IncomePaymentTransactionResponse.model_validate(tx) for tx in linked_transactions],
    )


async def _clear_income_manual_payment(db: AsyncSession, income: Income) -> IncomePaymentDetailsResponse:
    linked_transactions = await get_income_linked_payment_entries(db, income.id)
    linked_total = decimal_sum([tx.get("amount", ZERO_DECIMAL) for tx in linked_transactions])
    amount_total = to_decimal(income.amount_rsd or ZERO_DECIMAL)
    latest_linked_date = max((tx.get("date") for tx in linked_transactions), default=None)

    reconcile_income_payment_state(
        income,
        total_amount=amount_total,
        paid_amount=linked_total,
        paid_date=latest_linked_date,
    )

    if linked_transactions:
        income.bank_reference = next((tx.get("bank_reference") for tx in linked_transactions if tx.get("bank_reference")), None)
    else:
        income.bank_reference = None

    await db.flush()
    return _build_income_payment_details(income, linked_transactions)


async def _detach_income_transactions(db: AsyncSession, income_id: int) -> None:
    direct_result = await db.execute(
        select(BankTransaction.id).where(
            BankTransaction.matched_type == "income",
            BankTransaction.matched_id == income_id,
        )
    )
    direct_tx_ids = [int(value) for value in direct_result.scalars().all()]

    allocation_result = await db.execute(
        select(BankTransactionIncomeAllocation.bank_transaction_id).where(
            BankTransactionIncomeAllocation.income_id == income_id
        )
    )
    allocation_tx_ids = [int(value) for value in allocation_result.scalars().all()]

    for tx_id in dict.fromkeys(direct_tx_ids + allocation_tx_ids):
        await detach_income_transaction_link(db, tx_id, income_id)


def _line_total(item: IncomeItemCreate) -> Decimal:
    explicit = item.total_amount
    if explicit is not None:
        return to_decimal(explicit)
    return to_decimal(item.quantity or ZERO_DECIMAL) * to_decimal(item.unit_price or ZERO_DECIMAL)


def _normalize_income_items(items: list[IncomeItemCreate] | None) -> tuple[list[dict], Decimal]:
    normalized: list[dict] = []
    for index, item in enumerate(items or [], start=1):
        name = (item.name or "").strip()
        if not name:
            continue
        quantity = to_decimal(item.quantity or ZERO_DECIMAL)
        unit_price = to_decimal(item.unit_price or ZERO_DECIMAL)
        total_amount = _line_total(item)
        normalized.append(
            {
                "line_no": len(normalized) + 1,
                "name": name,
                "quantity": quantity,
                "unit": (item.unit or "kom").strip() or "kom",
                "unit_price": unit_price,
                "total_amount": total_amount,
                "tax_category": "O",
                "tax_rate": ZERO_DECIMAL,
                "note": item.note,
            }
        )
    return normalized, decimal_sum([item["total_amount"] for item in normalized])


def _replace_income_items(income: Income, items: list[IncomeItemCreate] | None) -> Decimal | None:
    if items is None:
        return None
    normalized, total = _normalize_income_items(items)
    income.items = [IncomeItem(**item) for item in normalized]
    return total if normalized else None


def _income_response(income: Income) -> IncomeResponse:
    data = IncomeResponse.model_validate(income).model_dump()
    if income.client:
        data["client_name"] = income.client.name
    return IncomeResponse(**data)


def _is_legacy_full_invoice_item(item: IncomeItem, income: Income) -> bool:
    name = (item.name or "").strip()
    description = (income.description or "").strip()
    if not name or not description or name != description or ";" not in name:
        return False
    invoice_amount = to_decimal(income.amount_rsd or ZERO_DECIMAL)
    return (
        to_decimal(item.quantity or ZERO_DECIMAL) == Decimal("1")
        and to_decimal(item.unit_price or ZERO_DECIMAL) == invoice_amount
        and to_decimal(item.total_amount or ZERO_DECIMAL) == invoice_amount
    )

from backend.income_service import (
    to_number_year_format,
    has_invoice_duplicate,
    invoice_year_from_number,
)

@router.get("", response_model=list[IncomeResponse])
async def list_income(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    client_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: Optional[int] = Query(None, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """РЎРїРёСЃРѕРє РґРѕС…РѕРґРѕРІ СЃ С„РёР»СЊС‚СЂР°С†РёРµР№."""
    q = select(Income).options(selectinload(Income.contract), selectinload(Income.client), selectinload(Income.items)).order_by(Income.issued_date.desc(), Income.id.desc())
    if year:
        q = q.where(Income.issued_date >= date(year, 1, 1), Income.issued_date <= date(year, 12, 31))
    if month and year:
        import calendar
        last = calendar.monthrange(year, month)[1]
        q = q.where(Income.issued_date >= date(year, month, 1), Income.issued_date <= date(year, month, last))
    if client_id:
        q = q.where(Income.client_id == client_id)
    if skip:
        q = q.offset(skip)
    if limit is not None:
        q = q.limit(limit)
    result = await db.execute(q)
    items = result.scalars().all()
    return [_income_response(i) for i in items]


@router.get("/years", response_model=list[int])
async def list_income_years(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Список годов, в которых есть доходы."""
    result = await db.execute(select(Income.invoice_year, Income.issued_date))
    years: set[int] = set()
    for invoice_year, issued_date in result.fetchall():
        year_value = int(invoice_year) if invoice_year is not None else (issued_date.year if issued_date else None)
        if year_value is not None:
            years.add(year_value)
    if not years:
        years.add(date.today().year)
    return sorted(years, reverse=True)


@router.post("", response_model=IncomeResponse)
async def create_income(
    data: IncomeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Р”РѕР±Р°РІРёС‚СЊ Р·Р°РїРёСЃСЊ РґРѕС…РѕРґР° (РљРџРћ). РќРѕРјРµСЂ СЃС‡С‘С‚Р°: Р°РІС‚Рѕ (РїРѕ РіРѕРґСѓ) РёР»Рё РїРµСЂРµРґР°РЅ; СѓРЅРёРєР°Р»СЊРЅРѕСЃС‚СЊ per year."""
    client_name = data.client_name
    if data.client_id:
        r = await db.execute(select(Client).where(Client.id == data.client_id))
        client = r.scalar_one_or_none()
        if client:
            client_name = client_name or client.name

    year = data.invoice_year or (data.issued_date.year if data.issued_date else None) or date.today().year
    invoice_number = (data.invoice_number or "").strip() if data.invoice_number is not None else ""
    invoice_year_val = year

    if not invoice_number:
        # РњРѕР¶РµС‚ Р±С‹С‚СЊ СЃС‚Р°СЂС‹Р№ С„РѕСЂРјР°С‚ РІ Р‘Р” (YYYY-NNNN), РїРѕСЌС‚РѕРјСѓ РїСЂРё РєРѕР»Р»РёР·РёРё Р±РµСЂС‘Рј СЃР»РµРґСѓСЋС‰РёР№ РЅРѕРјРµСЂ.
        allocated = False
        for _ in range(50):
            next_n = await allocate_next_invoice_number(db, year)
            candidate = f"{next_n:04d}-{year}"
            if not await has_invoice_duplicate(db, candidate, year):
                invoice_number = candidate
                allocated = True
                break
        if not allocated:
            raise HTTPException(409, INVOICE_ALLOCATE_DETAIL)
    else:
        invoice_number = to_number_year_format(invoice_number, year)
        invoice_year_val = data.invoice_year or invoice_year_from_number(invoice_number) or (data.issued_date.year if data.issued_date else date.today().year)
        if await has_invoice_duplicate(db, invoice_number, invoice_year_val):
            raise HTTPException(409, INVOICE_DUPLICATE_DETAIL)

    status_val = data.status or ("paid" if data.paid_date else "issued")
    project_id, contract_id = await _resolve_income_links(db, data.project_id, data.contract_id)
    income = Income(
        issued_date=data.issued_date,
        invoice_number=invoice_number,
        invoice_year=invoice_year_val,
        client_id=data.client_id,
        client_name=client_name,
        contract_id=contract_id,
        contract_payment_type=(data.contract_payment_type or None) if contract_id is not None else None,
        description=data.description,
        amount_rsd=data.amount_rsd,
        currency=data.currency,
        exchange_rate=data.exchange_rate,
        due_date=data.due_date,
        project_id=project_id,
        income_type=data.income_type or {"advance":"advance","intermediate":"intermediate","closing":"final"}.get(data.contract_payment_type or "", None),
        note=data.note,
        created_by=current_user.id,
    )
    item_total = _replace_income_items(income, data.items)
    if item_total is not None:
        income.amount_rsd = item_total
    try:
        initialize_income_status(
            income,
            status_val,
            paid_date=data.paid_date,
            paid_amount=to_decimal(income.amount_rsd or ZERO_DECIMAL) if status_val == "paid" else ZERO_DECIMAL,
        )
    except InvalidStatusTransition as exc:
        raise HTTPException(400, str(exc)) from exc
    db.add(income)
    try:
        await db.flush()
    except IntegrityError as e:
        msg = str(e.orig) if getattr(e, "orig", None) else str(e)
        low = msg.lower()
        if "unique" in low and ("invoice" in low or "uq_income_invoice_per_year" in low):
            raise HTTPException(409, INVOICE_DUPLICATE_DETAIL) from e
        raise
    if status_val == "paid" and data.paid_date:
        pass # BankTransaction now handles cash flow
    await db.commit()
    await db.refresh(income, ["contract", "client", "items"])
    return _income_response(income)


@router.get("/check-invoice")
async def check_invoice_exists(
    invoice_number: str = Query(..., description="РќРѕРјРµСЂ СЃС‡С‘С‚Р°"),
    year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """РџСЂРѕРІРµСЂРёС‚СЊ, СЃСѓС‰РµСЃС‚РІСѓРµС‚ Р»Рё СЃС‡С‘С‚ СЃ С‚Р°РєРёРј РЅРѕРјРµСЂРѕРј РІ СѓРєР°Р·Р°РЅРЅРѕРј РіРѕРґСѓ (РїРµСЂРёРѕРґ СЃС‡С‘С‚Р°)."""
    y = year or date.today().year
    normalized = to_number_year_format(invoice_number, y)
    return {"exists": await has_invoice_duplicate(db, normalized, y)}


@router.get("/next-invoice-number")
async def next_invoice_number(
    year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """РЎР»РµРґСѓСЋС‰РёР№ РЅРѕРјРµСЂ СЃС‡С‘С‚Р° Р·Р° РіРѕРґ (NNNN СЃР±СЂР°СЃС‹РІР°РµС‚СЃСЏ РЅР° 0001 РІ РЅРѕРІРѕРј РіРѕРґСѓ)."""
    y = year or date.today().year
    r = await db.execute(
        select(Income).where(
            or_(
                Income.invoice_year == y,
                and_(Income.invoice_year.is_(None), Income.issued_date >= date(y, 1, 1), Income.issued_date <= date(y, 12, 31)),
            )
        )
    )
    incomes = r.scalars().all()
    return {"invoice_number": get_next_invoice_number(incomes, y)}


@router.post("/bulk-assign-project")
async def bulk_assign_project_income(
    data: BulkAssignProject,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """РњР°СЃСЃРѕРІРѕРµ РЅР°Р·РЅР°С‡РµРЅРёРµ РїСЂРѕРµРєС‚Р° РґРѕС…РѕРґР°Рј. project_id=null в†’ INT-UNASSIGNED."""
    if not data.ids:
        return {"updated": 0}
    pid = data.project_id
    if pid is None:
        pid = await get_unassigned_project_id(db)
    if pid is not None:
        r = await db.execute(select(Project).where(Project.id == pid))
        proj = r.scalar_one_or_none()
        if not proj:
            raise HTTPException(404, "РџСЂРѕРµРєС‚ РЅРµ РЅР°Р№РґРµРЅ")
        if proj.status == "archived":
            raise HTTPException(400, "РќРµР»СЊР·СЏ РЅР°Р·РЅР°С‡РёС‚СЊ Р°СЂС…РёРІРёСЂРѕРІР°РЅРЅС‹Р№ РїСЂРѕРµРєС‚")
    r = await db.execute(select(Income).where(Income.id.in_(data.ids)))
    items = r.scalars().all()
    for item in items:
        item.project_id = pid
        await _clear_contract_if_project_mismatch(db, item, pid)
    await db.commit()
    return {"updated": len(items)}


@router.get("/item-suggestions", response_model=list[IncomeItemSuggestion])
async def income_item_suggestions(
    client_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    pattern = f"%{search.strip()}%" if search and search.strip() else None
    suggestions: list[IncomeItemSuggestion] = []
    seen: set[tuple[str, str, str]] = set()

    item_query = (
        select(IncomeItem, Income)
        .join(Income, IncomeItem.income_id == Income.id)
        .options(selectinload(Income.client))
        .order_by(Income.issued_date.desc(), IncomeItem.line_no.asc())
        .limit(300)
    )
    if client_id:
        item_query = item_query.where(Income.client_id == client_id)
    if pattern:
        item_query = item_query.where(IncomeItem.name.ilike(pattern))
    item_rows = await db.execute(item_query)
    for item, income in item_rows.fetchall():
        if _is_legacy_full_invoice_item(item, income):
            continue
        key = (item.name.strip().lower(), (item.unit or "kom").lower(), str(to_decimal(item.unit_price or ZERO_DECIMAL)))
        if key in seen:
            continue
        seen.add(key)
        suggestions.append(
            IncomeItemSuggestion(
                source="invoice",
                name=item.name,
                unit=item.unit or "kom",
                quantity=item.quantity or Decimal("1"),
                unit_price=item.unit_price or ZERO_DECIMAL,
                total_amount=item.total_amount or ZERO_DECIMAL,
                tax_category="O",
                tax_rate=ZERO_DECIMAL,
                invoice_id=income.id,
                invoice_number=income.invoice_number,
                issued_date=income.issued_date,
                client_name=income.client.name if income.client else income.client_name,
            )
        )
        if len(suggestions) >= limit:
            return suggestions

    contract_query = select(ContractItem, Contract).join(Contract, ContractItem.contract_id == Contract.id).order_by(Contract.date.desc(), ContractItem.sort_order.asc()).limit(300)
    if client_id:
        contract_query = contract_query.where(Contract.client_id == client_id)
    if pattern:
        contract_query = contract_query.where(ContractItem.description.ilike(pattern))
    contract_rows = await db.execute(contract_query)
    for item, contract in contract_rows.fetchall():
        key = (item.description.strip().lower(), (item.unit or "kom").lower(), str(to_decimal(item.price or ZERO_DECIMAL)))
        if key in seen:
            continue
        seen.add(key)
        suggestions.append(
            IncomeItemSuggestion(
                source="contract",
                name=item.description,
                unit=item.unit or "kom",
                quantity=to_decimal(item.quantity or 1),
                unit_price=item.price or ZERO_DECIMAL,
                total_amount=item.amount or ZERO_DECIMAL,
                client_name=None,
            )
        )
        if len(suggestions) >= limit:
            break
    return suggestions


@router.get("/{income_id}/efaktura-xml")
async def export_income_efaktura_xml(
    income_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(Income)
        .options(selectinload(Income.client), selectinload(Income.items))
        .where(Income.id == income_id)
    )
    income = result.scalar_one_or_none()
    if not income:
        raise HTTPException(404, "Income not found")
    enterprise_result = await db.execute(select(Enterprise).limit(1))
    enterprise = enterprise_result.scalar_one_or_none()
    if not enterprise:
        raise HTTPException(400, "Enterprise settings are required for eFaktura export")
    xml_bytes = build_income_efaktura_xml(income, enterprise, income.client)
    safe_number = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in income.invoice_number)
    return Response(
        content=xml_bytes,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="efaktura_{safe_number}.xml"'},
    )


@router.get("/{income_id}/payments", response_model=IncomePaymentDetailsResponse)
async def get_income_payments(
    income_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    income_result = await db.execute(select(Income).where(Income.id == income_id))
    income = income_result.scalar_one_or_none()
    if not income:
        raise HTTPException(404, "Income not found")
    linked_transactions = await get_income_linked_payment_entries(db, income_id)
    return _build_income_payment_details(income, linked_transactions)


@router.post("/{income_id}/clear-manual-payment", response_model=IncomePaymentDetailsResponse)
async def clear_income_manual_payment(
    income_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    income_result = await db.execute(select(Income).where(Income.id == income_id))
    income = income_result.scalar_one_or_none()
    if not income:
        raise HTTPException(404, "Income not found")
    if income.status == "cancelled":
        raise HTTPException(400, "Cancelled income cannot be updated")
    details = await _clear_income_manual_payment(db, income)
    await db.commit()
    return details

@router.get("/{income_id}", response_model=IncomeResponse)
async def get_income(
    income_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """РџРѕР»СѓС‡РёС‚СЊ Р·Р°РїРёСЃСЊ РґРѕС…РѕРґР°."""
    r = await db.execute(select(Income).options(selectinload(Income.contract), selectinload(Income.client), selectinload(Income.items)).where(Income.id == income_id))
    income = r.scalar_one_or_none()
    if not income:
        raise HTTPException(404, "Р—Р°РїРёСЃСЊ РЅРµ РЅР°Р№РґРµРЅР°")
    return _income_response(income)


@router.patch("/{income_id}", response_model=IncomeResponse)
async def update_income(
    income_id: int,
    data: IncomeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """РћР±РЅРѕРІРёС‚СЊ Р·Р°РїРёСЃСЊ РґРѕС…РѕРґР°."""
    r = await db.execute(select(Income).options(selectinload(Income.items)).where(Income.id == income_id))
    income = r.scalar_one_or_none()
    if not income:
        raise HTTPException(404, "Р—Р°РїРёСЃСЊ РЅРµ РЅР°Р№РґРµРЅР°")
    if income.status == "cancelled":
        raise HTTPException(400, "Cancelled income cannot be updated")
    requested_items = data.items if "items" in data.model_fields_set else None
    dump = data.model_dump(exclude_unset=True, exclude={"items"})
    payment_fields_requested = "paid_date" in dump or "is_paid" in dump
    requested_paid_date = dump.pop("paid_date", income.paid_date) if "paid_date" in dump else income.paid_date
    requested_is_paid = dump.pop("is_paid", None) if "is_paid" in dump else None
    desired_project_id = dump.get("project_id", income.project_id)
    desired_contract_id = dump.get("contract_id", income.contract_id)

    if not desired_project_id:
        desired_project_id = await get_unassigned_project_id(db)

    if desired_contract_id is None and income.contract_id and "project_id" in dump:
        contract = await get_contract_or_404(db, income.contract_id)
        if contract.project_id != desired_project_id:
            desired_contract_id = None

    desired_project_id, desired_contract_id = await _resolve_income_links(db, desired_project_id, desired_contract_id)
    dump["project_id"] = desired_project_id
    dump["contract_id"] = desired_contract_id
    if desired_contract_id is None:
        dump["contract_payment_type"] = None
    for k, v in dump.items():
        setattr(income, k, v)
    item_total = _replace_income_items(income, requested_items)
    if item_total is not None:
        income.amount_rsd = item_total
    if payment_fields_requested:
        should_mark_paid = requested_paid_date is not None
        if requested_is_paid is not None:
            should_mark_paid = bool(requested_is_paid)
        try:
            if should_mark_paid:
                transition_income_status(
                    income,
                    "paid",
                    paid_date=requested_paid_date,
                    paid_amount=to_decimal(income.amount_rsd or ZERO_DECIMAL),
                )
            else:
                reconcile_income_payment_state(
                    income,
                    total_amount=to_decimal(income.amount_rsd or ZERO_DECIMAL),
                    paid_amount=to_decimal(income.paid_amount or ZERO_DECIMAL),
                    paid_date=None,
                )
        except InvalidStatusTransition as exc:
            raise HTTPException(400, str(exc)) from exc
    # РџСЂРѕРІРµСЂРєР° СѓРЅРёРєР°Р»СЊРЅРѕСЃС‚Рё (invoice_year, invoice_number) РґРѕ flush
    if "invoice_number" in dump:
        year_val = income.invoice_year
        if year_val is None and income.issued_date:
            year_val = income.issued_date.year
        if year_val is not None:
            income.invoice_number = to_number_year_format(income.invoice_number, year_val)
            if await has_invoice_duplicate(db, income.invoice_number, year_val, exclude_income_id=income_id):
                raise HTTPException(
                    409,
                    INVOICE_DUPLICATE_DETAIL,
                )
    try:
        await db.flush()
        await db.commit()
    except IntegrityError as e:
        msg = str(e.orig) if getattr(e, "orig", None) else str(e)
        if "UNIQUE" in msg and ("invoice" in msg or "income" in msg.lower()):
            raise HTTPException(409, INVOICE_DUPLICATE_DETAIL) from e
        raise
    # РЎРёРЅС…СЂРѕРЅРёР·Р°С†РёСЏ Р·Р°РІРµСЂС€РµРЅР°, BankTransaction СЃР°Рј СѓРїСЂР°РІР»СЏРµС‚СЃСЏ
    r = await db.execute(select(Income).options(selectinload(Income.contract), selectinload(Income.client), selectinload(Income.items)).where(Income.id == income_id))
    income = r.scalar_one()
    return _income_response(income)


@router.delete("/{income_id}")
async def delete_income(
    income_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Delete income using cancel-first semantics."""
    r = await db.execute(select(Income).where(Income.id == income_id))
    income = r.scalar_one_or_none()
    if not income:
        raise HTTPException(404, "Income record not found")

    if income.status == "cancelled":
        await _detach_income_transactions(db, income.id)
        await db.delete(income)
        await db.commit()
        return {"ok": True, "deleted": True}

    await _detach_income_transactions(db, income.id)
    try:
        cancel_income(income)
    except InvalidStatusTransition as exc:
        raise HTTPException(400, str(exc)) from exc
    income.paid_date = None
    income.bank_reference = None
    await db.commit()
    return {"ok": True, "cancelled": True}
