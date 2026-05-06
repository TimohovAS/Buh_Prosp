"""Р‘РёР·РЅРµСЃ-Р»РѕРіРёРєР° ProspEl."""
import calendar
from datetime import date, datetime, timedelta
from decimal import Decimal
import re
from typing import Optional
from sqlalchemy import select, func, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Income, Client, Enterprise
from backend.config import get_settings
from backend.decimal_utils import MONEY_PLACES, ZERO_DECIMAL, to_decimal
from backend.state_machine import ensure_expense_can_reverse, initialize_expense_status

settings = get_settings()


async def get_income_total(
    db: AsyncSession,
    year: Optional[int] = None,
    month: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
) -> Decimal:
    """РЎСѓРјРјР° РґРѕС…РѕРґРѕРІ Р·Р° РїРµСЂРёРѕРґ."""
    from datetime import date as date_type
    import calendar

    q = (
        select(func.coalesce(func.sum(Income.amount_rsd), 0))
        .select_from(Income)
        .where(Income.status != "cancelled")
    )
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
    return to_decimal(result.scalar() or ZERO_DECIMAL)


async def get_income_total_12_months(db: AsyncSession, as_of: date) -> Decimal:
    """Р”РѕС…РѕРґ Р·Р° РїРѕСЃР»РµРґРЅРёРµ 12 РјРµСЃСЏС†РµРІ (РґР»СЏ Р»РёРјРёС‚Р° 8 РјР»РЅ)."""
    from dateutil.relativedelta import relativedelta
    start = as_of - relativedelta(months=12)
    return await get_income_total(db, start_date=start, end_date=as_of)


def _parse_invoice_number_parts(value: Optional[str]) -> tuple[Optional[int], Optional[int]]:
    """
    Р’РµСЂРЅСѓС‚СЊ (year, serial) РґР»СЏ С„РѕСЂРјР°С‚РѕРІ:
    - YYYY-NNNN
    - NNNN-YYYY
    """
    s = (value or "").strip()
    if not s:
        return None, None
    m_year_first = re.fullmatch(r"(20\d{2})-(\d{1,10})", s)
    if m_year_first:
        return int(m_year_first.group(1)), int(m_year_first.group(2))
    m_num_first = re.fullmatch(r"(\d{1,10})-(20\d{2})", s)
    if m_num_first:
        return int(m_num_first.group(2)), int(m_num_first.group(1))
    return None, None


def _normalize_invoice_number(value: Optional[str]) -> str:
    if not value:
        return ""
    s = re.sub(r"\s+", "", str(value).strip().upper())
    m_year_first = re.fullmatch(r"(20\d{2})-(\d{1,10})", s)
    if m_year_first:
        return f"{m_year_first.group(1)}:{int(m_year_first.group(2))}"
    m_num_first = re.fullmatch(r"(\d{1,10})-(20\d{2})", s)
    if m_num_first:
        return f"{m_num_first.group(2)}:{int(m_num_first.group(1))}"
    return s


def _extract_invoice_candidates(*parts: Optional[str]) -> list[str]:
    """
    Р”РѕСЃС‚Р°С‘Рј РІРѕР·РјРѕР¶РЅС‹Рµ РЅРѕРјРµСЂР° С„Р°РєС‚СѓСЂ РёР· С‚РµРєСЃС‚Р° РЅР°Р·РЅР°С‡РµРЅРёСЏ/СЂРµС„РµСЂРµРЅС†РёРё.
    РџРѕРґРґРµСЂР¶РёРІР°РµРј РѕР±Р° С‡Р°СЃС‚С‹С… С„РѕСЂРјР°С‚Р°: YYYY-NNNN Рё NNN-YYYY.
    """
    text = " ".join([str(p or "") for p in parts]).upper()
    patterns = [
        r"\b20\d{2}-\d{1,6}\b",   # 2026-0008
        r"\b\d{1,6}-20\d{2}\b",   # 008-2026
    ]
    out: list[str] = []
    seen: set[str] = set()
    for pat in patterns:
        for m in re.findall(pat, text):
            v = m.strip()
            if v and v not in seen:
                seen.add(v)
                out.append(v)
    return out


def _invoice_year_from_record(i: Income) -> Optional[int]:
    """Р“РѕРґ РїРµСЂРёРѕРґР° СЃС‡С‘С‚Р°: РёР· РїРѕР»СЏ invoice_year РёР»Рё РёР· РЅРѕРјРµСЂР° СЃС‡С‘С‚Р°."""
    if getattr(i, "invoice_year", None) is not None:
        return int(i.invoice_year)
    y, _ = _parse_invoice_number_parts(getattr(i, "invoice_number", None))
    if y is not None:
        return y
    return None


def get_next_invoice_number(db_incomes: list[Income], year: int) -> str:
    """РЎР»РµРґСѓСЋС‰РёР№ РЅРѕРјРµСЂ СЃС‡С‘С‚Р° Р·Р° РіРѕРґ (С„РѕСЂРјР°С‚ NNNN-YYYY)."""
    nums = []
    for i in db_incomes:
        if not i.invoice_number:
            continue
        if _invoice_year_from_record(i) != year:
            continue
        _, serial = _parse_invoice_number_parts(str(i.invoice_number).strip())
        if serial is not None:
            nums.append(serial)
        elif str(i.invoice_number).strip().isdigit():
            nums.append(int(str(i.invoice_number).strip()))
    next_num = max(nums, default=0) + 1
    return f"{next_num:04d}-{year}"


async def allocate_next_invoice_number(db: AsyncSession, year: int) -> int:
    """РђС‚РѕРјР°СЂРЅРѕ РІС‹РґРµР»РёС‚СЊ СЃР»РµРґСѓСЋС‰РёР№ РїРѕСЂСЏРґРєРѕРІС‹Р№ РЅРѕРјРµСЂ СЃС‡С‘С‚Р° Р·Р° РіРѕРґ (Р±Р»РѕРєРёСЂРѕРІРєР° РєРѕРЅРєСѓСЂРµРЅС†РёРё)."""
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
    """РђС‚РѕРјР°СЂРЅРѕ РІС‹РґРµР»РёС‚СЊ СЃР»РµРґСѓСЋС‰РёР№ РєРѕРґ РїСЂРѕРµРєС‚Р° (PR-YYYY-NNNN). Р‘РµР· РґСѓР±Р»РµР№ РїСЂРё РїР°СЂР°Р»Р»РµР»СЊРЅС‹С… Р·Р°РїСЂРѕСЃР°С…."""
    from datetime import date
    year = date.today().year
    # РђС‚РѕРјР°СЂРЅС‹Р№ increment (INSERT or UPDATE) + RETURNING
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
    # Fallback РґР»СЏ SQLite Р±РµР· RETURNING: Р°С‚РѕРјР°СЂРЅС‹Р№ UPDATE
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
    ensure_expense_can_reverse(expense)
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
        category_id=getattr(expense, "category_id", None),
        paid_date=rev_date,
        source=source,
        is_tax_related=getattr(expense, "is_tax_related", False) or False,
        reversal_of_id=expense.id,
        bank_reference=getattr(expense, "bank_reference", None),
        project_id=getattr(expense, "project_id", None),
        contract_id=getattr(expense, "contract_id", None),
        note=comment,
        created_by=created_by,
    )
    initialize_expense_status(reversal, "reversed", paid_date=rev_date)
    db.add(reversal)
    await db.flush()
    expense.reversed_expense_id = reversal.id
    await db.flush()
    await db.refresh(reversal)
    return reversal


async def get_income_limit_status(db: AsyncSession, year: int) -> dict:
    """РЎС‚Р°С‚СѓСЃ Р»РёРјРёС‚РѕРІ РґРѕС…РѕРґР°."""
    year_income = await get_income_total(db, year=year)
    today = date.today()
    income_12m = await get_income_total_12_months(db, today)

    limit_6m = settings.income_limit_pausal
    limit_8m = settings.income_limit_vat
    warn = settings.limit_warning_percent

    year_income_decimal = to_decimal(year_income)
    income_12m_decimal = to_decimal(income_12m)
    limit_6m_decimal = Decimal(str(limit_6m))
    limit_8m_decimal = Decimal(str(limit_8m))
    warning_ratio = Decimal(str(warn))

    return {
        "year_income": year_income_decimal,
        "income_12m": income_12m_decimal,
        "limit_6m": limit_6m,
        "limit_8m": limit_8m,
        "percent_6m": float(((year_income_decimal / limit_6m_decimal) * Decimal("100")).quantize(MONEY_PLACES)) if limit_6m else 0,
        "percent_8m": float(((income_12m_decimal / limit_8m_decimal) * Decimal("100")).quantize(MONEY_PLACES)) if limit_8m else 0,
        "warning_6m": year_income_decimal >= (limit_6m_decimal * warning_ratio),
        "warning_8m": income_12m_decimal >= (limit_8m_decimal * warning_ratio),
        "exceeded_6m": year_income_decimal > limit_6m_decimal,
        "exceeded_8m": income_12m_decimal > limit_8m_decimal,
    }




async def get_finance_limits_overview(db: AsyncSession, as_of: Optional[date] = None) -> dict:
    """Accrual-based paucal income limits using Income.issued_date."""
    current_date = as_of or date.today()
    annual_total = await get_income_total(db, year=current_date.year)
    rolling_12_total = await get_income_total_12_months(db, current_date)

    annual_limit = settings.income_limit_pausal
    vat_limit = settings.income_limit_vat
    annual_limit_decimal = Decimal(str(annual_limit))
    vat_limit_decimal = Decimal(str(vat_limit))

    annual_percent = (
        float(((annual_total / annual_limit_decimal) * Decimal("100")).quantize(MONEY_PLACES))
        if annual_limit else 0.0
    )
    vat_percent = (
        float(((rolling_12_total / vat_limit_decimal) * Decimal("100")).quantize(MONEY_PLACES))
        if vat_limit else 0.0
    )

    days_in_month = calendar.monthrange(current_date.year, current_date.month)[1]
    elapsed_months = Decimal(str((current_date.month - 1) + (current_date.day / days_in_month)))
    if elapsed_months <= ZERO_DECIMAL:
        elapsed_months = Decimal("1")
    average_monthly_income = (annual_total / elapsed_months).quantize(MONEY_PLACES)
    forecast_year_end = (average_monthly_income * Decimal("12")).quantize(MONEY_PLACES)

    start_of_year = date(current_date.year, 1, 1)
    elapsed_days = max(1, (current_date - start_of_year).days + 1)
    daily_rate = (annual_total / Decimal(str(elapsed_days))).quantize(MONEY_PLACES) if annual_total > ZERO_DECIMAL else ZERO_DECIMAL

    estimated_limit_date: Optional[str] = None
    if annual_total >= annual_limit_decimal:
        estimated_limit_date = current_date.isoformat()
    elif daily_rate > ZERO_DECIMAL:
        remaining = annual_limit_decimal - annual_total
        days_to_limit = int((remaining / daily_rate).to_integral_value())
        estimated_date = current_date + timedelta(days=max(0, days_to_limit))
        if estimated_date.year == current_date.year:
            estimated_limit_date = estimated_date.isoformat()

    annual_warning_percent = max(annual_percent, 0.0)
    vat_warning_percent = max(vat_percent, 0.0)
    if (
        annual_total >= annual_limit_decimal
        or rolling_12_total >= vat_limit_decimal
        or forecast_year_end >= annual_limit_decimal
        or annual_warning_percent >= 90
        or vat_warning_percent >= 90
    ):
        risk = "high"
    elif (
        annual_warning_percent >= 70
        or vat_warning_percent >= 75
        or forecast_year_end >= (annual_limit_decimal * Decimal("0.90"))
    ):
        risk = "medium"
    else:
        risk = "low"

    return {
        "annual_total": annual_total,
        "annual_limit": annual_limit,
        "annual_percent": annual_percent,
        "rolling_12_total": rolling_12_total,
        "vat_limit": vat_limit,
        "vat_percent": vat_percent,
        "average_monthly_income": average_monthly_income,
        "forecast_year_end": forecast_year_end,
        "estimated_limit_date": estimated_limit_date,
        "risk": risk,
    }


