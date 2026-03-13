"""Legacy-роутер платежей (изолирован, не подключён в active runtime)."""
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import Payment, ContributionRates, User
from backend.schemas import PaymentResponse, PaymentUpdate, ContributionRatesCreate, ContributionRatesResponse
from backend.auth import get_current_user_required, require_edit_access

router = APIRouter(prefix="/payments", tags=["payments"])


async def _legacy_get_or_create_payment(
    db: AsyncSession,
    year: int,
    month: int,
) -> Optional[Payment]:
    """Legacy helper для старого /payments API."""
    result = await db.execute(
        select(Payment).where(Payment.year == year, Payment.month == month)
    )
    payment = result.scalar_one_or_none()
    if payment:
        return payment

    rates_result = await db.execute(
        select(ContributionRates).where(
            ContributionRates.year == year,
            ContributionRates.is_active == True
        )
    )
    rates = rates_result.scalar_one_or_none()
    if not rates:
        return None

    payment = Payment(
        year=year,
        month=month,
        rates_id=rates.id,
        tax_amount=rates.tax_amount,
        pio_amount=rates.pio_amount,
        health_amount=rates.health_amount,
        unemployment_amount=rates.unemployment_amount,
        total_amount=rates.tax_amount + rates.pio_amount + rates.health_amount + rates.unemployment_amount,
    )
    db.add(payment)
    await db.flush()
    return payment


@router.get("", response_model=list[PaymentResponse])
async def list_payments(
    year: int = Query(..., description="Год"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Список платежей за год."""
    # Создаём записи для всех месяцев если их нет
    for m in range(1, 13):
        await _legacy_get_or_create_payment(db, year, m)
    await db.commit()
    r = await db.execute(
        select(Payment).where(Payment.year == year).order_by(Payment.month)
    )
    payments = r.scalars().all()
    return [PaymentResponse.model_validate(p) for p in payments]


@router.get("/rates", response_model=list[ContributionRatesResponse])
async def list_rates(
    year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Список ставок налогов и взносов."""
    q = select(ContributionRates).order_by(ContributionRates.year.desc())
    if year:
        q = q.where(ContributionRates.year == year)
    r = await db.execute(q)
    return [ContributionRatesResponse.model_validate(x) for x in r.scalars().all()]


@router.post("/rates", response_model=ContributionRatesResponse)
async def create_rates(
    data: ContributionRatesCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Добавить ставки (из налогового решения)."""
    r = await db.execute(select(ContributionRates).where(ContributionRates.year == data.year))
    if r.scalar_one_or_none():
        raise HTTPException(400, "Ставки за этот год уже существуют")
    rates = ContributionRates(**data.model_dump())
    db.add(rates)
    await db.commit()
    await db.refresh(rates)
    return ContributionRatesResponse.model_validate(rates)


@router.patch("/{payment_id}", response_model=PaymentResponse)
async def update_payment(
    payment_id: int,
    data: PaymentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Обновить платёж (отметить как оплаченный)."""
    r = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = r.scalar_one_or_none()
    if not payment:
        raise HTTPException(404, "Платёж не найден")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(payment, k, v)
    await db.commit()
    await db.refresh(payment)
    return PaymentResponse.model_validate(payment)
