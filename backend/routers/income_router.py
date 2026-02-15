"""Роутер доходов (КПО)."""
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
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
    """Год из номера YYYY-NNNN или None."""
    s = (invoice_number or "").strip()
    if len(s) >= 4 and s[:4].isdigit():
        return int(s[:4])
    return None


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
        next_n = await allocate_next_invoice_number(db, year)
        invoice_number = f"{year}-{next_n:04d}"
    else:
        invoice_year_val = data.invoice_year or _invoice_year_from_number(invoice_number) or (data.issued_date.year if data.issued_date else date.today().year)

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
    except IntegrityError:
        raise HTTPException(409, "Номер счёта уже существует в этом году (уникальность по году)")
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
    r = await db.execute(
        select(Income).where(
            Income.invoice_number == invoice_number.strip(),
            or_(
                Income.invoice_year == y,
                and_(Income.invoice_year.is_(None), Income.issued_date >= date(y, 1, 1), Income.issued_date <= date(y, 12, 31)),
            ),
        )
    )
    return {"exists": r.scalars().first() is not None}


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
    await db.flush()
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
