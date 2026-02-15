"""Бизнес-логика ProspEl."""
from datetime import date, datetime
from typing import Optional
from sqlalchemy import select, func, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Income, Client, Payment, ContributionRates, Enterprise
from backend.config import get_settings

settings = get_settings()


async def get_income_total(
    db: AsyncSession,
    year: Optional[int] = None,
    month: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
) -> float:
    """Сумма доходов за период."""
    from datetime import date as date_type
    import calendar

    q = select(func.coalesce(func.sum(Income.amount_rsd), 0)).select_from(Income)
    if year and month:
        last_day = calendar.monthrange(year, month)[1]
        q = q.where(
            Income.issued_date >= date_type(year, month, 1),
            Income.issued_date <= date_type(year, month, last_day)
        )
    elif year:
        q = q.where(
            Income.issued_date >= date_type(year, 1, 1),
            Income.issued_date <= date_type(year, 12, 31)
        )
    if start_date:
        q = q.where(Income.issued_date >= start_date)
    if end_date:
        q = q.where(Income.issued_date <= end_date)
    result = await db.execute(q)
    return float(result.scalar() or 0)


async def get_income_total_12_months(db: AsyncSession, as_of: date) -> float:
    """Доход за последние 12 месяцев (для лимита 8 млн)."""
    from dateutil.relativedelta import relativedelta
    start = as_of - relativedelta(months=12)
    return await get_income_total(db, start_date=start, end_date=as_of)


def _invoice_year_from_record(i: Income) -> Optional[int]:
    """Год периода счёта: из поля invoice_year или из префикса YYYY в invoice_number."""
    if getattr(i, "invoice_year", None) is not None:
        return int(i.invoice_year)
    s = (i.invoice_number or "").strip()
    if len(s) >= 4 and s[:4].isdigit() and (len(s) == 4 or s[4:5] in ("-", "")):
        return int(s[:4])
    return None


def get_next_invoice_number(db_incomes: list[Income], year: int) -> str:
    """Следующий номер счёта за год (формат YYYY-NNNN). NNNN сбрасывается на 0001 в новом году."""
    nums = []
    for i in db_incomes:
        if not i.invoice_number:
            continue
        if _invoice_year_from_record(i) != year:
            continue
        s = str(i.invoice_number).strip()
        if "-" in s:
            parts = s.split("-", 1)
            if len(parts) == 2 and parts[1].isdigit():
                nums.append(int(parts[1]))
        elif s.isdigit():
            nums.append(int(s))
    next_num = max(nums, default=0) + 1
    return f"{year}-{next_num:04d}"


async def allocate_next_invoice_number(db: AsyncSession, year: int) -> int:
    """Атомарно выделить следующий порядковый номер счёта за год (блокировка конкуренции)."""
    r = await db.execute(
        text("""
            INSERT INTO invoice_sequence (year, last_number) VALUES (:y, 1)
            ON CONFLICT(year) DO UPDATE SET last_number = last_number + 1
            RETURNING last_number
        """),
        {"y": year},
    )
    row = r.fetchone()
    if row is not None:
        return int(row[0])
    r2 = await db.execute(text("SELECT last_number FROM invoice_sequence WHERE year = :y"), {"y": year})
    row2 = r2.fetchone()
    return int(row2[0]) if row2 else 1


async def allocate_next_project_code(db: AsyncSession) -> str:
    """Атомарно выделить следующий код проекта (PR-YYYY-NNNN). Без дублей при параллельных запросах."""
    from datetime import date
    year = date.today().year
    # Атомарный increment (INSERT or UPDATE) + RETURNING
    r = await db.execute(
        text("""
            INSERT INTO project_sequence (year, last_number) VALUES (:y, 1)
            ON CONFLICT(year) DO UPDATE SET last_number = last_number + 1
            RETURNING last_number
        """),
        {"y": year},
    )
    row = r.fetchone()
    if row is not None:
        return f"PR-{year}-{int(row[0]):04d}"
    # Fallback для SQLite без RETURNING: атомарный UPDATE
    await db.execute(
        text("""
            INSERT INTO project_sequence (year, last_number) VALUES (:y, 1)
            ON CONFLICT(year) DO UPDATE SET last_number = last_number + 1
        """),
        {"y": year},
    )
    r2 = await db.execute(text("SELECT last_number FROM project_sequence WHERE year = :y"), {"y": year})
    row2 = r2.fetchone()
    return f"PR-{year}-{int(row2[0] or 1):04d}"


async def create_expense_reversal(
    db: AsyncSession,
    expense: "Expense",
    reverse_date: Optional[date] = None,
    comment: Optional[str] = None,
    source: str = "manual",
    created_by: Optional[int] = None,
) -> "Expense":
    """
    Создать сторно расхода. Оригинал остаётся status=paid, получает reversed_expense_id.
    Сторно: amount=-original.amount, status=reversed, reversal_of_id=original.id.
    """
    from backend.models import Expense
    rev_date = reverse_date or getattr(expense, "paid_date", None) or date.today()
    desc = f"Сторно: {(expense.description or '')[:450]}"
    if comment:
        desc += f" ({comment})"
    if len(desc) > 500:
        desc = desc[:497] + "..."
    reversal = Expense(
        date=rev_date,
        description=desc,
        amount=-expense.amount,
        currency=expense.currency or "RSD",
        category=expense.category,
        paid_date=rev_date,
        status="reversed",
        source=source,
        is_tax_related=getattr(expense, "is_tax_related", False) or False,
        reversal_of_id=expense.id,
        note=comment,
        created_by=created_by,
    )
    db.add(reversal)
    await db.flush()
    expense.reversed_expense_id = reversal.id
    await db.flush()
    await db.refresh(reversal)
    return reversal


async def get_income_limit_status(db: AsyncSession, year: int) -> dict:
    """Статус лимитов дохода."""
    year_income = await get_income_total(db, year=year)
    today = date.today()
    income_12m = await get_income_total_12_months(db, today)

    limit_6m = settings.income_limit_pausal
    limit_8m = settings.income_limit_vat
    warn = settings.limit_warning_percent

    return {
        "year_income": year_income,
        "income_12m": income_12m,
        "limit_6m": limit_6m,
        "limit_8m": limit_8m,
        "percent_6m": round(year_income / limit_6m * 100, 2) if limit_6m else 0,
        "percent_8m": round(income_12m / limit_8m * 100, 2) if limit_8m else 0,
        "warning_6m": year_income >= limit_6m * warn,
        "warning_8m": income_12m >= limit_8m * warn,
        "exceeded_6m": year_income > limit_6m,
        "exceeded_8m": income_12m > limit_8m,
    }


async def get_or_create_payment(
    db: AsyncSession,
    year: int,
    month: int
) -> Optional[Payment]:
    """Получить или создать платёж за месяц."""
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
