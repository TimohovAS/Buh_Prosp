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
from backend.models import Income, Client, User, Project
from backend.schemas import IncomeCreate, IncomeUpdate, IncomeResponse, IncomeMarkPaid, BulkAssignProject
from backend.auth import get_current_user_required, require_edit_access
from backend.services import get_income_total, get_next_invoice_number, allocate_next_invoice_number

router = APIRouter(prefix="/income", tags=["income"])


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
            if not await has_invoice_duplicate(db, candidate, year):
                invoice_number = candidate
                allocated = True
                break
        if not allocated:
            raise HTTPException(409, "Не удалось подобрать уникальный номер счёта за год")
    else:
        invoice_number = to_number_year_format(invoice_number, year)
        invoice_year_val = data.invoice_year or invoice_year_from_number(invoice_number) or (data.issued_date.year if data.issued_date else date.today().year)
        if await has_invoice_duplicate(db, invoice_number, invoice_year_val):
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
        pass # BankTransaction now handles cash flow
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
    normalized = to_number_year_format(invoice_number, y)
    return {"exists": await has_invoice_duplicate(db, normalized, y)}


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
    await db.commit()
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
        pib_key = normalize_pib(client.pib)
        if pib_key and pib_key not in clients_by_pib:
            clients_by_pib[pib_key] = client
        name_key = normalize_name(client.name)
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
        try:
            async with db.begin_nested():
                normalized_invoice_number = to_number_year_format(parsed["invoice_number"], invoice_year)
                if await has_invoice_duplicate(db, normalized_invoice_number, invoice_year):
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
                await db.flush() # Keep flush here to allow rollback on IntegrityError within the loop
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
    await db.commit() # Commit all changes after the loop

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
            income.invoice_number = to_number_year_format(income.invoice_number, year_val)
            if await has_invoice_duplicate(db, income.invoice_number, year_val, exclude_income_id=income_id):
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
    # Синхронизация завершена, BankTransaction сам управляется
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
    await db.delete(income)
    return {"ok": True}
