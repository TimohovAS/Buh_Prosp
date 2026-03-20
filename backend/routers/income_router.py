"""Р РѕСѓС‚РµСЂ РґРѕС…РѕРґРѕРІ (РљРџРћ)."""
from datetime import date
from typing import Optional
from decimal import Decimal, InvalidOperation
import re
from xml.etree import ElementTree as ET

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select, or_, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from backend.database import get_db
from backend.efaktura_service import import_efaktura_documents
from backend.models import Income, Client, User, Project, BankTransaction, Contract, Enterprise, Expense
from backend.schemas import IncomeCreate, IncomeUpdate, IncomeResponse, IncomeMarkPaid, BulkAssignProject, IncomePaymentDetailsResponse, IncomePaymentTransactionResponse
from backend.auth import get_current_user_required, require_edit_access
from backend.services import get_income_total, get_next_invoice_number, allocate_next_invoice_number
from backend.decimal_utils import ZERO_DECIMAL, decimal_sum, to_decimal
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

async def _get_unassigned_project_id(db: AsyncSession) -> int | None:
    """РџРѕР»СѓС‡РёС‚СЊ id РїСЂРѕРµРєС‚Р° INT-UNASSIGNED."""
    r = await db.execute(select(Project).where(Project.code == "INT-UNASSIGNED"))
    p = r.scalar_one_or_none()
    return p.id if p else None


async def _get_enterprise(db: AsyncSession) -> Enterprise | None:
    result = await db.execute(select(Enterprise).order_by(Enterprise.id.asc()).limit(1))
    return result.scalar_one_or_none()


def _enterprise_matches_party(enterprise: Enterprise | None, party_name: str | None, party_pib: str | None) -> bool:
    if enterprise is None:
        return False
    enterprise_pib = normalize_pib(enterprise.pib)
    enterprise_name = normalize_name(enterprise.name)
    party_pib_normalized = normalize_pib(party_pib)
    party_name_normalized = normalize_name(party_name)
    if enterprise_pib and party_pib_normalized and enterprise_pib == party_pib_normalized:
        return True
    if enterprise_name and party_name_normalized and enterprise_name == party_name_normalized:
        return True
    return False


def _build_efaktura_expense_identity(invoice_number: str, invoice_year: int, supplier_pib: str | None, supplier_name: str | None) -> str:
    supplier_key = normalize_pib(supplier_pib) or normalize_name(supplier_name) or "unknown"
    normalized_invoice_number = to_number_year_format(invoice_number, invoice_year)
    return f"eFaktura-in|{normalized_invoice_number}|{supplier_key}"


def _build_efaktura_expense_note(
    invoice_number: str,
    invoice_year: int,
    supplier_name: str | None,
    supplier_pib: str | None,
    file_name: str,
) -> str:
    identity = _build_efaktura_expense_identity(invoice_number, invoice_year, supplier_pib, supplier_name)
    display_supplier = supplier_name or "Unknown supplier"
    display_pib = normalize_pib(supplier_pib) or "n/a"
    return f"[{identity}] Import eFaktura: {display_supplier}; PIB {display_pib}; file {file_name}"


async def _has_efaktura_expense_duplicate(
    db: AsyncSession,
    invoice_number: str,
    invoice_year: int,
    supplier_pib: str | None,
    supplier_name: str | None,
    issued_date: date,
    amount: Decimal,
) -> bool:
    identity = _build_efaktura_expense_identity(invoice_number, invoice_year, supplier_pib, supplier_name)
    result = await db.execute(
        select(Expense.note).where(
            Expense.source == EFAKTURA_IMPORT_SOURCE,
            Expense.date == issued_date,
            Expense.amount == amount,
        )
    )
    for (note,) in result.fetchall():
        if isinstance(note, str) and note.startswith(f"[{identity}]"):
            return True
    return False


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


async def _resolve_income_links(
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


async def _clear_contract_if_project_mismatch(db: AsyncSession, income: Income, project_id: int | None) -> None:
    if not income.contract_id or project_id is None:
        return
    contract = await _get_contract_or_404(db, income.contract_id)
    if contract.project_id != project_id:
        income.contract_id = None
        income.contract_payment_type = None


async def _get_income_linked_transactions(db: AsyncSession, income_id: int) -> list[BankTransaction]:
    result = await db.execute(
        select(BankTransaction)
        .where(BankTransaction.matched_type == "income", BankTransaction.matched_id == income_id)
        .order_by(BankTransaction.date.desc(), BankTransaction.id.desc())
    )
    return list(result.scalars().all())


def _build_income_payment_details(income: Income, linked_transactions: list[BankTransaction]) -> IncomePaymentDetailsResponse:
    linked_total = decimal_sum([tx.amount or ZERO_DECIMAL for tx in linked_transactions])
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
    linked_transactions = await _get_income_linked_transactions(db, income.id)
    linked_total = decimal_sum([tx.amount or ZERO_DECIMAL for tx in linked_transactions])
    amount_total = to_decimal(income.amount_rsd or ZERO_DECIMAL)
    latest_linked_date = max((tx.date for tx in linked_transactions), default=None)

    reconcile_income_payment_state(
        income,
        total_amount=amount_total,
        paid_amount=linked_total,
        paid_date=latest_linked_date,
    )

    if linked_transactions:
        income.bank_reference = next((tx.bank_reference for tx in linked_transactions if tx.bank_reference), None)
    else:
        income.bank_reference = None

    await db.flush()
    return _build_income_payment_details(income, linked_transactions)


async def _detach_income_transactions(db: AsyncSession, income_id: int) -> None:
    linked_transactions = await _get_income_linked_transactions(db, income_id)
    for transaction in linked_transactions:
        transaction.status = "unmatched"
        transaction.matched_type = None
        transaction.matched_id = None

from backend.income_service import (
    to_number_year_format,
    has_invoice_duplicate,
    parse_efaktura_invoice,
    invoice_year_from_number,
    normalize_pib,
    normalize_name,
)

@router.get("", response_model=list[IncomeResponse])
async def list_income(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    client_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """РЎРїРёСЃРѕРє РґРѕС…РѕРґРѕРІ СЃ С„РёР»СЊС‚СЂР°С†РёРµР№."""
    q = select(Income).options(selectinload(Income.contract), selectinload(Income.client)).order_by(Income.issued_date.desc(), Income.id.desc())
    if year:
        q = q.where(Income.issued_date >= date(year, 1, 1), Income.issued_date <= date(year, 12, 31))
    if month and year:
        import calendar
        last = calendar.monthrange(year, month)[1]
        q = q.where(Income.issued_date >= date(year, month, 1), Income.issued_date <= date(year, month, last))
    if client_id:
        q = q.where(Income.client_id == client_id)
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    items = result.scalars().all()
    out = []
    for i in items:
        data = IncomeResponse.model_validate(i).model_dump()
        if i.client:
            data["client_name"] = i.client.name
        out.append(IncomeResponse(**data))
    return out


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
    try:
        initialize_income_status(
            income,
            status_val,
            paid_date=data.paid_date,
            paid_amount=to_decimal(data.amount_rsd or ZERO_DECIMAL) if status_val == "paid" else ZERO_DECIMAL,
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
    await db.refresh(income)
    return IncomeResponse.model_validate(income)


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
        pid = await _get_unassigned_project_id(db)
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


@router.post("/import-efaktura")
async def import_efaktura(
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """РРјРїРѕСЂС‚ С„Р°РєС‚СѓСЂ eFaktura XML РІ РґРѕС…РѕРґС‹."""
    if not files:
        raise HTTPException(400, "РќСѓР¶РЅРѕ РІС‹Р±СЂР°С‚СЊ С…РѕС‚СЏ Р±С‹ РѕРґРёРЅ XML-С„Р°Р№Р»")
    documents = []
    for upload in files:
        documents.append(
            {
                "file_name": upload.filename or "unknown.xml",
                "content": await upload.read(),
            }
        )
    return await import_efaktura_documents(
        db,
        user_id=current_user.id,
        documents=documents,
        source="xml",
    )

    clients_result = await db.execute(select(Client))
    clients = clients_result.scalars().all()
    clients_by_pib: dict[str, Client] = {}
    clients_by_name: dict[str, Client] = {}
    for client in clients:
        pib_key = normalize_pib(client.pib)
        if pib_key and pib_key not in clients_by_pib:
            clients_by_pib[pib_key] = client
        name_key = normalize_name(client.name)
        if name_key and name_key not in clients_by_name:
            clients_by_name[name_key] = client

    enterprise = await _get_enterprise(db)
    has_enterprise_identity = bool(
        enterprise and (normalize_pib(enterprise.pib) or normalize_name(enterprise.name))
    )
    unassigned_project_id = await _get_unassigned_project_id(db)
    created = []
    skipped = []
    errors = []
    created_income_count = 0
    created_expense_count = 0

    for upload in files:
        file_name = upload.filename or "unknown.xml"
        content = await upload.read()
        if not content:
            errors.append({"file_name": file_name, "error": "РџСѓСЃС‚РѕР№ С„Р°Р№Р»"})
            continue

        try:
            parsed = parse_efaktura_invoice(content, file_name)
        except ValueError as exc:
            errors.append({"file_name": file_name, "error": str(exc)})
            continue

        matched_client = None
        if parsed["customer_pib"]:
            matched_client = clients_by_pib.get(parsed["customer_pib"])
        if matched_client is None and parsed["client_name"]:
            matched_client = clients_by_name.get(normalize_name(parsed["client_name"]))

        invoice_year = parsed["issued_date"].year
        normalized_invoice_number = to_number_year_format(parsed["invoice_number"], invoice_year)
        supplier_is_enterprise = _enterprise_matches_party(enterprise, parsed.get("supplier_name"), parsed.get("supplier_pib"))
        customer_is_enterprise = _enterprise_matches_party(enterprise, parsed.get("customer_name"), parsed.get("customer_pib"))
        direction = "income"
        if customer_is_enterprise and not supplier_is_enterprise:
            direction = "expense"
        elif supplier_is_enterprise and not customer_is_enterprise:
            direction = "income"
        elif has_enterprise_identity:
            errors.append(
                {
                    "file_name": file_name,
                    "error": "Could not determine whether this eFaktura is incoming or outgoing for the configured enterprise",
                }
            )
            continue
        try:
            async with db.begin_nested():
                if direction == "expense":
                    if await _has_efaktura_expense_duplicate(
                        db,
                        normalized_invoice_number,
                        invoice_year,
                        parsed.get("supplier_pib"),
                        parsed.get("supplier_name"),
                        parsed["issued_date"],
                        parsed["amount_rsd"],
                    ):
                        skipped.append(
                            {
                                "file_name": file_name,
                                "invoice_number": normalized_invoice_number,
                                "reason": "Incoming eFaktura already exists in expenses",
                            }
                        )
                        continue

                    expense = Expense(
                        date=parsed["issued_date"],
                        description=parsed["description"],
                        amount=parsed["amount_rsd"],
                        currency=parsed["currency"],
                        category=None,
                        category_id=None,
                        paid_date=None,
                        status="planned",
                        is_tax_related=False,
                        source=EFAKTURA_IMPORT_SOURCE,
                        project_id=unassigned_project_id,
                        note=_build_efaktura_expense_note(
                            normalized_invoice_number,
                            invoice_year,
                            parsed.get("supplier_name"),
                            parsed.get("supplier_pib"),
                            file_name,
                        ),
                        created_by=current_user.id,
                    )
                    db.add(expense)
                    await db.flush()
                    created.append(
                        {
                            "file_name": file_name,
                            "document_type": "expense",
                            "expense_id": expense.id,
                            "invoice_number": normalized_invoice_number,
                            "counterparty_name": parsed.get("supplier_name"),
                        }
                    )
                    created_expense_count += 1
                    continue

                if await has_invoice_duplicate(db, normalized_invoice_number, invoice_year):
                    skipped.append(
                        {
                            "file_name": file_name,
                            "invoice_number": normalized_invoice_number,
                            "reason": "Р¤Р°РєС‚СѓСЂР° СѓР¶Рµ СЃСѓС‰РµСЃС‚РІСѓРµС‚ РІ РґРѕС…РѕРґР°С… Р·Р° СЌС‚РѕС‚ РіРѕРґ",
                        }
                    )
                    continue

                income = Income(
                    issued_date=parsed["issued_date"],
                    invoice_number=normalized_invoice_number,
                    invoice_year=invoice_year,
                    client_id=matched_client.id if matched_client else None,
                    client_name=matched_client.name if matched_client else parsed["client_name"],
                    description=parsed["description"],
                    amount_rsd=parsed["amount_rsd"],
                    currency=parsed["currency"],
                    exchange_rate=1.0,
                    due_date=parsed["due_date"],
                    project_id=unassigned_project_id,
                    note=f"РРјРїРѕСЂС‚ eFaktura: {file_name}",
                    created_by=current_user.id,
                )
                initialize_income_status(income, "issued", paid_amount=ZERO_DECIMAL)
                db.add(income)
                await db.flush() # Keep flush here to allow rollback on IntegrityError within the loop
                created.append(
                    {
                        "file_name": file_name,
                        "document_type": "income",
                        "income_id": income.id,
                        "invoice_number": income.invoice_number,
                        "counterparty_name": income.client_name,
                    }
                )
                created_income_count += 1
        except IntegrityError:
            skipped.append(
                {
                    "file_name": file_name,
                    "invoice_number": parsed["invoice_number"],
                    "reason": "Р”СѓР±Р»РёРєР°С‚ С„Р°РєС‚СѓСЂС‹",
                }
            )
    await db.commit() # Commit all changes after the loop

    return {
        "created_count": len(created),
        "created_income_count": created_income_count,
        "created_expense_count": created_expense_count,
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "created": created,
        "skipped": skipped,
        "errors": errors,
    }


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
    linked_transactions = await _get_income_linked_transactions(db, income_id)
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
    r = await db.execute(select(Income).options(selectinload(Income.contract), selectinload(Income.client)).where(Income.id == income_id))
    income = r.scalar_one_or_none()
    if not income:
        raise HTTPException(404, "Р—Р°РїРёСЃСЊ РЅРµ РЅР°Р№РґРµРЅР°")
    data = IncomeResponse.model_validate(income).model_dump()
    if income.client:
        data["client_name"] = income.client.name
    return IncomeResponse(**data)


@router.patch("/{income_id}", response_model=IncomeResponse)
async def update_income(
    income_id: int,
    data: IncomeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """РћР±РЅРѕРІРёС‚СЊ Р·Р°РїРёСЃСЊ РґРѕС…РѕРґР°."""
    r = await db.execute(select(Income).where(Income.id == income_id))
    income = r.scalar_one_or_none()
    if not income:
        raise HTTPException(404, "Р—Р°РїРёСЃСЊ РЅРµ РЅР°Р№РґРµРЅР°")
    if income.status == "cancelled":
        raise HTTPException(400, "Cancelled income cannot be updated")
    dump = data.model_dump(exclude_unset=True)
    payment_fields_requested = "paid_date" in dump or "is_paid" in dump
    requested_paid_date = dump.pop("paid_date", income.paid_date) if "paid_date" in dump else income.paid_date
    requested_is_paid = dump.pop("is_paid", None) if "is_paid" in dump else None
    desired_project_id = dump.get("project_id", income.project_id)
    desired_contract_id = dump.get("contract_id", income.contract_id)

    if not desired_project_id:
        desired_project_id = await _get_unassigned_project_id(db)

    if desired_contract_id is None and income.contract_id and "project_id" in dump:
        contract = await _get_contract_or_404(db, income.contract_id)
        if contract.project_id != desired_project_id:
            desired_contract_id = None

    desired_project_id, desired_contract_id = await _resolve_income_links(db, desired_project_id, desired_contract_id)
    dump["project_id"] = desired_project_id
    dump["contract_id"] = desired_contract_id
    if desired_contract_id is None:
        dump["contract_payment_type"] = None
    for k, v in dump.items():
        setattr(income, k, v)
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
    r = await db.execute(select(Income).options(selectinload(Income.contract), selectinload(Income.client)).where(Income.id == income_id))
    income = r.scalar_one()
    data = IncomeResponse.model_validate(income).model_dump()
    if income.client:
        data["client_name"] = income.client.name
    return IncomeResponse(**data)


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


