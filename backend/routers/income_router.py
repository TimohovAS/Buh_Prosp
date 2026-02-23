"""Роутер доходов (КПО)."""
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
from backend.models import Income, Client, User, CashTransaction, Project
from backend.schemas import IncomeCreate, IncomeUpdate, IncomeResponse, IncomeMarkPaid, BulkAssignProject
from backend.auth import get_current_user_required, require_edit_access
from backend.services import get_income_total, get_next_invoice_number, allocate_next_invoice_number

router = APIRouter(prefix="/income", tags=["income"])


EF_NS = {
    "env": "urn:eFaktura:MinFinrs:envelop:schema",
    "inv": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
}


def _normalize_whitespace(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    compact = " ".join(value.split()).strip()
    return compact or None


def _normalize_pib(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    if not digits:
        return None
    # В eFaktura может приходить CompanyID вида RS123456789.
    return digits[-9:] if len(digits) > 9 else digits


def _normalize_name(value: Optional[str]) -> Optional[str]:
    text = _normalize_whitespace(value)
    return text.lower() if text else None


def _parse_invoice_number_parts(value: Optional[str]) -> tuple[Optional[int], Optional[int]]:
    """
    Разобрать номер фактуры в форматах YYYY-NNNN и NNNN-YYYY.
    Возвращает (year, serial) или (None, None), если шаблон не распознан.
    """
    s = (_normalize_whitespace(value) or "").upper()
    if not s:
        return None, None
    m_year_first = re.fullmatch(r"(20\d{2})-(\d{1,10})", s)
    if m_year_first:
        return int(m_year_first.group(1)), int(m_year_first.group(2))
    m_num_first = re.fullmatch(r"(\d{1,10})-(20\d{2})", s)
    if m_num_first:
        return int(m_num_first.group(2)), int(m_num_first.group(1))
    return None, None


def _invoice_identity(invoice_number: Optional[str], invoice_year: Optional[int]) -> tuple[Optional[int], str]:
    """
    Нормализованный ключ фактуры для сравнения дублей.
    Для числовых форматов сравниваем по (year, serial без ведущих нулей).
    """
    raw = (_normalize_whitespace(invoice_number) or "").upper()
    parsed_year, serial = _parse_invoice_number_parts(raw)
    year_key = parsed_year if parsed_year is not None else invoice_year
    if serial is not None:
        return year_key, str(serial)
    return year_key, raw


def _to_number_year_format(invoice_number: Optional[str], fallback_year: Optional[int] = None) -> str:
    """Привести распознанный номер к формату NNNN-YYYY."""
    raw = (_normalize_whitespace(invoice_number) or "")
    parsed_year, serial = _parse_invoice_number_parts(raw)
    year_val = parsed_year if parsed_year is not None else fallback_year
    if serial is not None and year_val is not None:
        return f"{serial:04d}-{year_val}"
    return raw


async def _has_invoice_duplicate(
    db: AsyncSession,
    invoice_number: str,
    invoice_year: int,
    exclude_income_id: Optional[int] = None,
) -> bool:
    """
    Проверка дубля с учётом форматов YYYY-NNNN и NNNN-YYYY.
    Нужна для старых данных, где могут встречаться оба формата.
    """
    target_year, target_key = _invoice_identity(invoice_number, invoice_year)
    r = await db.execute(
        select(Income.id, Income.invoice_number, Income.invoice_year, Income.issued_date).where(
            or_(
                Income.invoice_year == invoice_year,
                and_(
                    Income.invoice_year.is_(None),
                    Income.issued_date >= date(invoice_year, 1, 1),
                    Income.issued_date <= date(invoice_year, 12, 31),
                ),
            )
        )
    )
    for income_id, existing_number, existing_year, issued_date in r.fetchall():
        if exclude_income_id is not None and int(income_id) == int(exclude_income_id):
            continue
        year_val = int(existing_year) if existing_year is not None else (issued_date.year if issued_date else None)
        ex_year, ex_key = _invoice_identity(existing_number, year_val)
        if ex_year == target_year and ex_key == target_key:
            return True
    return False


def _parse_efaktura_invoice(xml_bytes: bytes, file_name: str) -> dict:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError(f"{file_name}: не удалось прочитать XML ({exc})") from exc

    invoice = root.find("env:DocumentBody/inv:Invoice", EF_NS)
    if invoice is None and root.tag.endswith("Invoice"):
        invoice = root
    if invoice is None:
        raise ValueError(f"{file_name}: не найден блок Invoice")

    invoice_number = _normalize_whitespace(invoice.findtext("cbc:ID", default="", namespaces=EF_NS))
    if not invoice_number:
        raise ValueError(f"{file_name}: отсутствует номер фактуры (cbc:ID)")

    issue_raw = _normalize_whitespace(invoice.findtext("cbc:IssueDate", default="", namespaces=EF_NS))
    if not issue_raw:
        raise ValueError(f"{file_name}: отсутствует дата фактуры (cbc:IssueDate)")
    try:
        issue_date = date.fromisoformat(issue_raw)
    except ValueError as exc:
        raise ValueError(f"{file_name}: некорректная дата фактуры ({issue_raw})") from exc

    due_raw = _normalize_whitespace(invoice.findtext("cbc:DueDate", default="", namespaces=EF_NS))
    due_date = None
    if due_raw:
        try:
            due_date = date.fromisoformat(due_raw)
        except ValueError as exc:
            raise ValueError(f"{file_name}: некорректная дата оплаты (cbc:DueDate={due_raw})") from exc

    amount_raw = _normalize_whitespace(
        invoice.findtext("cac:LegalMonetaryTotal/cbc:PayableAmount", default="", namespaces=EF_NS)
    )
    if not amount_raw:
        raise ValueError(f"{file_name}: отсутствует сумма к оплате (cbc:PayableAmount)")
    normalized_amount = amount_raw.replace("\u00A0", "").replace(" ", "").replace(",", ".")
    try:
        amount_rsd = float(Decimal(normalized_amount))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{file_name}: некорректная сумма ({amount_raw})") from exc

    customer_name = _normalize_whitespace(
        invoice.findtext("cac:AccountingCustomerParty/cac:Party/cac:PartyName/cbc:Name", default="", namespaces=EF_NS)
    ) or _normalize_whitespace(
        invoice.findtext(
            "cac:AccountingCustomerParty/cac:Party/cac:PartyLegalEntity/cbc:RegistrationName",
            default="",
            namespaces=EF_NS,
        )
    )
    customer_tax_id = _normalize_whitespace(
        invoice.findtext(
            "cac:AccountingCustomerParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID",
            default="",
            namespaces=EF_NS,
        )
    ) or _normalize_whitespace(
        invoice.findtext("cac:AccountingCustomerParty/cac:Party/cbc:EndpointID", default="", namespaces=EF_NS)
    )

    line_titles: list[str] = []
    for node in invoice.findall("cac:InvoiceLine/cac:Item/cbc:Name", EF_NS):
        line_name = _normalize_whitespace(node.text)
        if line_name:
            line_titles.append(line_name)
    description = "; ".join(line_titles) if line_titles else f"eFaktura {invoice_number}"
    if len(description) > 500:
        description = f"{description[:497]}..."

    currency = _normalize_whitespace(invoice.findtext("cbc:DocumentCurrencyCode", default="RSD", namespaces=EF_NS)) or "RSD"

    return {
        "invoice_number": _to_number_year_format(invoice_number, issue_date.year),
        "issued_date": issue_date,
        "due_date": due_date,
        "amount_rsd": amount_rsd,
        "currency": currency,
        "client_name": customer_name,
        "customer_pib": _normalize_pib(customer_tax_id),
        "description": description,
    }


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
    """Список доходов с фильтрацией."""
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


def _invoice_year_from_number(invoice_number: str) -> Optional[int]:
    """Год из номера YYYY-NNNN или NNNN-YYYY."""
    y, _ = _parse_invoice_number_parts(invoice_number)
    return y


@router.post("", response_model=IncomeResponse)
async def create_income(
    data: IncomeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Добавить запись дохода (КПО). Номер счёта: авто (по году) или передан; уникальность per year."""
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
        # Может быть старый формат в БД (YYYY-NNNN), поэтому при коллизии берём следующий номер.
        allocated = False
        for _ in range(50):
            next_n = await allocate_next_invoice_number(db, year)
            candidate = f"{next_n:04d}-{year}"
            if not await _has_invoice_duplicate(db, candidate, year):
                invoice_number = candidate
                allocated = True
                break
        if not allocated:
            raise HTTPException(409, "Не удалось подобрать уникальный номер счёта за год")
    else:
        invoice_number = _to_number_year_format(invoice_number, year)
        invoice_year_val = data.invoice_year or _invoice_year_from_number(invoice_number) or (data.issued_date.year if data.issued_date else date.today().year)
        if await _has_invoice_duplicate(db, invoice_number, invoice_year_val):
            raise HTTPException(409, "Номер счёта уже существует в этом году (уникальность по году)")

    status_val = data.status or ("paid" if data.paid_date else "issued")
    income = Income(
        issued_date=data.issued_date,
        invoice_number=invoice_number,
        invoice_year=invoice_year_val,
        client_id=data.client_id,
        client_name=client_name,
        contract_id=data.contract_id,
        contract_payment_type=data.contract_payment_type or None,
        description=data.description,
        amount_rsd=data.amount_rsd,
        currency=data.currency,
        exchange_rate=data.exchange_rate,
        paid_date=data.paid_date,
        due_date=data.due_date,
        status=status_val,
        project_id=data.project_id,
        income_type=data.income_type or {"advance":"advance","intermediate":"intermediate","closing":"final"}.get(data.contract_payment_type or "", None),
        note=data.note,
        is_paid=(status_val == "paid"),
        created_by=current_user.id,
    )
    db.add(income)
    try:
        await db.flush()
    except IntegrityError as e:
        msg = str(e.orig) if getattr(e, "orig", None) else str(e)
        low = msg.lower()
        if "unique" in low and ("invoice" in low or "uq_income_invoice_per_year" in low):
            raise HTTPException(409, "Номер счёта уже существует в этом году (уникальность по году)") from e
        raise
    if status_val == "paid" and data.paid_date:
        ct = CashTransaction(
            type="income",
            source="invoice",
            reference_id=income.id,
            amount=float(income.amount_rsd),
            date=data.paid_date,
        )
        db.add(ct)
        await db.flush()
    await db.refresh(income)
    return IncomeResponse.model_validate(income)


@router.get("/check-invoice")
async def check_invoice_exists(
    invoice_number: str = Query(..., description="Номер счёта"),
    year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Проверить, существует ли счёт с таким номером в указанном году (период счёта)."""
    y = year or date.today().year
    normalized = _to_number_year_format(invoice_number, y)
    return {"exists": await _has_invoice_duplicate(db, normalized, y)}


@router.get("/next-invoice-number")
async def next_invoice_number(
    year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Следующий номер счёта за год (NNNN сбрасывается на 0001 в новом году)."""
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
    """Массовое назначение проекта доходам. project_id=null — снять проект."""
    if not data.ids:
        return {"updated": 0}
    if data.project_id is not None:
        r = await db.execute(select(Project).where(Project.id == data.project_id))
        proj = r.scalar_one_or_none()
        if not proj:
            raise HTTPException(404, "Проект не найден")
        if proj.status == "archived":
            raise HTTPException(400, "Нельзя назначить архивированный проект")
    r = await db.execute(select(Income).where(Income.id.in_(data.ids)))
    items = r.scalars().all()
    for item in items:
        item.project_id = data.project_id
    await db.flush()
    return {"updated": len(items)}


@router.post("/import-efaktura")
async def import_efaktura(
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Импорт фактур eFaktura XML в доходы."""
    if not files:
        raise HTTPException(400, "Нужно выбрать хотя бы один XML-файл")

    clients_result = await db.execute(select(Client))
    clients = clients_result.scalars().all()
    clients_by_pib: dict[str, Client] = {}
    clients_by_name: dict[str, Client] = {}
    for client in clients:
        pib_key = _normalize_pib(client.pib)
        if pib_key and pib_key not in clients_by_pib:
            clients_by_pib[pib_key] = client
        name_key = _normalize_name(client.name)
        if name_key and name_key not in clients_by_name:
            clients_by_name[name_key] = client

    created = []
    skipped = []
    errors = []

    for upload in files:
        file_name = upload.filename or "unknown.xml"
        content = await upload.read()
        if not content:
            errors.append({"file_name": file_name, "error": "Пустой файл"})
            continue

        try:
            parsed = _parse_efaktura_invoice(content, file_name)
        except ValueError as exc:
            errors.append({"file_name": file_name, "error": str(exc)})
            continue

        matched_client = None
        if parsed["customer_pib"]:
            matched_client = clients_by_pib.get(parsed["customer_pib"])
        if matched_client is None and parsed["client_name"]:
            matched_client = clients_by_name.get(_normalize_name(parsed["client_name"]))

        invoice_year = parsed["issued_date"].year
        try:
            async with db.begin_nested():
                normalized_invoice_number = _to_number_year_format(parsed["invoice_number"], invoice_year)
                if await _has_invoice_duplicate(db, normalized_invoice_number, invoice_year):
                    skipped.append(
                        {
                            "file_name": file_name,
                            "invoice_number": normalized_invoice_number,
                            "reason": "Фактура уже существует в доходах за этот год",
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
                    status="issued",
                    is_paid=False,
                    note=f"Импорт eFaktura: {file_name}",
                    created_by=current_user.id,
                )
                db.add(income)
                await db.flush()
                created.append(
                    {
                        "file_name": file_name,
                        "income_id": income.id,
                        "invoice_number": income.invoice_number,
                        "client_name": income.client_name,
                    }
                )
        except IntegrityError:
            skipped.append(
                {
                    "file_name": file_name,
                    "invoice_number": parsed["invoice_number"],
                    "reason": "Дубликат фактуры",
                }
            )

    return {
        "created_count": len(created),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "created": created,
        "skipped": skipped,
        "errors": errors,
    }


@router.get("/{income_id}", response_model=IncomeResponse)
async def get_income(
    income_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Получить запись дохода."""
    r = await db.execute(select(Income).options(selectinload(Income.contract), selectinload(Income.client)).where(Income.id == income_id))
    income = r.scalar_one_or_none()
    if not income:
        raise HTTPException(404, "Запись не найдена")
    data = IncomeResponse.model_validate(income).model_dump()
    if income.client:
        data["client_name"] = income.client.name
    return IncomeResponse(**data)


@router.patch("/{income_id}/mark-paid", response_model=IncomeResponse)
async def mark_income_paid(
    income_id: int,
    data: IncomeMarkPaid,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Отметить доход как оплаченный: paid_date, status='paid', создать cash_transaction."""
    r = await db.execute(select(Income).options(selectinload(Income.contract), selectinload(Income.client)).where(Income.id == income_id))
    income = r.scalar_one_or_none()
    if not income:
        raise HTTPException(404, "Запись не найдена")
    income.paid_date = data.paid_date
    income.status = "paid"
    income.is_paid = True
    await db.flush()
    # Создать cash_transaction для cash-flow
    existing = await db.execute(
        select(CashTransaction).where(
            CashTransaction.source == "invoice",
            CashTransaction.reference_id == income_id,
        )
    )
    if existing.scalar_one_or_none() is None:
        ct = CashTransaction(
            type="income",
            source="invoice",
            reference_id=income_id,
            amount=float(income.amount_rsd),
            date=data.paid_date,
        )
        db.add(ct)
        await db.flush()
    await db.refresh(income)
    data_out = IncomeResponse.model_validate(income).model_dump()
    if income.client:
        data_out["client_name"] = income.client.name
    return IncomeResponse(**data_out)


@router.patch("/{income_id}/mark-unpaid")
async def mark_income_unpaid(
    income_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Отменить отметку оплаты: paid_date=null, status=issued, удалить cash_transaction."""
    r = await db.execute(select(Income).where(Income.id == income_id))
    income = r.scalar_one_or_none()
    if not income:
        raise HTTPException(404, "Запись не найдена")
    income.paid_date = None
    income.status = "issued"
    income.is_paid = False
    await db.flush()
    # Удалить cash_transaction
    r2 = await db.execute(
        select(CashTransaction).where(
            CashTransaction.source == "invoice",
            CashTransaction.reference_id == income_id,
        )
    )
    ct = r2.scalar_one_or_none()
    if ct:
        await db.delete(ct)
        await db.flush()
    return {"ok": True}


@router.patch("/{income_id}", response_model=IncomeResponse)
async def update_income(
    income_id: int,
    data: IncomeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Обновить запись дохода."""
    r = await db.execute(select(Income).where(Income.id == income_id))
    income = r.scalar_one_or_none()
    if not income:
        raise HTTPException(404, "Запись не найдена")
    dump = data.model_dump(exclude_unset=True)
    paid_date_new = dump.get("paid_date")
    for k, v in dump.items():
        setattr(income, k, v)
    if "paid_date" in dump or "status" in dump:
        income.is_paid = income.status == "paid"
    # Проверка уникальности (invoice_year, invoice_number) до flush
    if "invoice_number" in dump:
        year_val = income.invoice_year
        if year_val is None and income.issued_date:
            year_val = income.issued_date.year
        if year_val is not None:
            income.invoice_number = _to_number_year_format(income.invoice_number, year_val)
            if await _has_invoice_duplicate(db, income.invoice_number, year_val, exclude_income_id=income_id):
                raise HTTPException(
                    409,
                    "Запись с таким номером счёта за этот год уже существует (invoice_year, invoice_number).",
                )
    try:
        await db.flush()
    except IntegrityError as e:
        msg = str(e.orig) if getattr(e, "orig", None) else str(e)
        if "UNIQUE" in msg and ("invoice" in msg or "income" in msg.lower()):
            raise HTTPException(409, "Запись с таким номером счёта за этот год уже существует.") from e
        raise
    # Синхронизация cash_transaction
    r2 = await db.execute(
        select(CashTransaction).where(
            CashTransaction.source == "invoice",
            CashTransaction.reference_id == income_id,
        )
    )
    ct = r2.scalar_one_or_none()
    if income.status == "paid" and income.paid_date:
        if ct:
            ct.amount = float(income.amount_rsd)
            ct.date = income.paid_date
            await db.flush()
        else:
            db.add(CashTransaction(
                type="income", source="invoice", reference_id=income_id,
                amount=float(income.amount_rsd), date=income.paid_date,
            ))
            await db.flush()
    elif ct:
        await db.delete(ct)
        await db.flush()
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
    """Удалить запись дохода."""
    r = await db.execute(select(Income).where(Income.id == income_id))
    income = r.scalar_one_or_none()
    if not income:
        raise HTTPException(404, "Запись не найдена")
    r2 = await db.execute(
        select(CashTransaction).where(
            CashTransaction.source == "invoice",
            CashTransaction.reference_id == income_id,
        )
    )
    ct = r2.scalar_one_or_none()
    if ct:
        await db.delete(ct)
        await db.flush()
    await db.delete(income)
    return {"ok": True}
