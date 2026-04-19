"""Р¤РёРЅР°РЅСЃРѕРІС‹Р№ СЃРµСЂРІРёСЃ: РјРµС‚СЂРёРєРё accrual vs cash."""
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Literal, Optional
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.cash_service import CASH_TRANSFER_SOURCE
from backend.decimal_utils import MONEY_PLACES, ZERO_DECIMAL, to_decimal
from backend.models import Income, Expense, Enterprise, Project, BankTransaction, BankTransactionIncomeAllocation

EFAKTURA_IMPORT_SOURCE = "efaktura_import"


def _visible_expense_condition():
    return or_(Expense.status != "planned", Expense.source == EFAKTURA_IMPORT_SOURCE)


def _append_period_amount(periods_data: dict[str, dict[str, Decimal]], period: str, key: str, amount) -> None:
    if period in periods_data:
        periods_data[period][key] += to_decimal(amount or ZERO_DECIMAL)


def _period_key(d: date, group_by: Literal["day", "month", "year"]) -> str:
    """РљР»СЋС‡ РїРµСЂРёРѕРґР°: YYYY-MM-DD | YYYY-MM | YYYY."""
    if group_by == "day":
        return d.strftime("%Y-%m-%d")
    if group_by == "month":
        return d.strftime("%Y-%m")
    return str(d.year)


def _iter_periods(
    date_from: date,
    date_to: date,
    group_by: Literal["day", "month", "year"],
):
    """РС‚РµСЂР°С‚РѕСЂ РїРѕ РїРµСЂРёРѕРґР°Рј РІ РґРёР°РїР°Р·РѕРЅРµ."""
    if group_by == "day":
        current = date_from
        while current <= date_to:
            yield _period_key(current, group_by)
            current += timedelta(days=1)
    elif group_by == "month":
        y, m = date_from.year, date_from.month
        while date(y, m, 1) <= date_to:
            yield _period_key(date(y, m, 1), group_by)
            m += 1
            if m > 12:
                m, y = 1, y + 1
    else:
        y = date_from.year
        while date(y, 1, 1) <= date_to:
            yield _period_key(date(y, 1, 1), group_by)
            y += 1


async def get_finance_summary(
    db: AsyncSession,
    date_from: date,
    date_to: date,
    group_by: Literal["day", "month", "year"],
    mode: Literal["accrual", "cash", "both"],
    filters: Optional[dict[str, Any]] = None,
) -> dict:
    """
    РђРіСЂРµРіР°С‚РѕСЂ РјРµС‚СЂРёРє РґР»СЏ accrual/cash.
    filters: client_id, contract_id, project_id (income), category, is_tax_related (expenses)
    """
    filters = filters or {}
    client_id = filters.get("client_id")
    contract_id = filters.get("contract_id")
    project_id = filters.get("project_id")
    category = filters.get("category")
    is_tax_related = filters.get("is_tax_related")

    # SQLite: date column РІ income РЅР°Р·С‹РІР°РµС‚СЃСЏ "date" (issued_date РІ РјРѕРґРµР»Рё)
    income_date_col = Income.issued_date
    income_paid_col = Income.paid_date
    income_amount = Income.amount_rsd
    income_status = Income.status

    expense_date_col = Expense.date
    expense_paid_col = Expense.paid_date
    expense_amount = Expense.amount
    expense_status = Expense.status
    expense_is_tax = Expense.is_tax_related

    # Р‘Р°Р·РѕРІС‹Рµ СѓСЃР»РѕРІРёСЏ РґР»СЏ income
    income_base = and_(
        income_status != "cancelled",
        income_date_col >= date_from,
        income_date_col <= date_to,
    )
    if client_id is not None:
        income_base = and_(income_base, Income.client_id == client_id)
    if contract_id is not None:
        income_base = and_(income_base, Income.contract_id == contract_id)
    if project_id is not None:
        income_base = and_(income_base, Income.project_id == project_id)

    # Р‘Р°Р·РѕРІС‹Рµ СѓСЃР»РѕРІРёСЏ РґР»СЏ expenses:
    # accrual: СѓС‡РёС‚С‹РІР°РµРј С„Р°РєС‚РёС‡РµСЃРєРёРµ РїСЂРѕРІРѕРґРєРё, РІРєР»СЋС‡Р°СЏ СЃС‚РѕСЂРЅРѕ (status=reversed, amount<0),
    # РЅРѕ РёСЃРєР»СЋС‡Р°РµРј planned.
    expense_accrual_base = and_(
        _visible_expense_condition(),
        Expense.source != CASH_TRANSFER_SOURCE,
        expense_date_col >= date_from,
        expense_date_col <= date_to,
    )
    if category is not None:
        expense_accrual_base = and_(expense_accrual_base, Expense.category == category)
    if is_tax_related is not None:
        expense_accrual_base = and_(
            expense_accrual_base,
            expense_is_tax == (1 if is_tax_related else 0),
        )

    # Cash: paid_date in period, СѓС‡РёС‚С‹РІР°РµРј paid Рё reversed (СЃС‚РѕСЂРЅРѕ РІР»РёСЏРµС‚ РЅР° cash-flow).
    income_cash_base = and_(
        income_status == "paid",
        income_paid_col.isnot(None),
        income_paid_col >= date_from,
        income_paid_col <= date_to,
    )
    if client_id is not None:
        income_cash_base = and_(income_cash_base, Income.client_id == client_id)
    if contract_id is not None:
        income_cash_base = and_(income_cash_base, Income.contract_id == contract_id)
    if project_id is not None:
        income_cash_base = and_(income_cash_base, Income.project_id == project_id)

    expense_cash_base = and_(
        expense_status.in_(["paid", "reversed"]),
        Expense.source != CASH_TRANSFER_SOURCE,
        expense_paid_col.isnot(None),
        expense_paid_col >= date_from,
        expense_paid_col <= date_to,
    )
    if category is not None:
        expense_cash_base = and_(expense_cash_base, Expense.category == category)
    if is_tax_related is not None:
        expense_cash_base = and_(
            expense_cash_base,
            expense_is_tax == (1 if is_tax_related else 0),
        )

    expense_tax_base = and_(
        expense_status.in_(["paid", "reversed"]),
        Expense.source != CASH_TRANSFER_SOURCE,
        expense_is_tax == True,
        expense_paid_col.isnot(None),
        expense_paid_col >= date_from,
        expense_paid_col <= date_to,
    )
    if category is not None:
        expense_tax_base = and_(expense_tax_base, Expense.category == category)

    # Р¤РѕСЂРјР°С‚ РґР»СЏ GROUP BY РІ SQLite
    if group_by == "day":
        fmt = "%Y-%m-%d"
    elif group_by == "month":
        fmt = "%Y-%m"
    else:
        fmt = "%Y"

    periods_data: dict[str, dict[str, float]] = {}
    for pk in _iter_periods(date_from, date_to, group_by):
        periods_data[pk] = {
            "revenue_accrual": ZERO_DECIMAL,
            "revenue_cash": ZERO_DECIMAL,
            "expense_accrual": ZERO_DECIMAL,
            "expense_cash": ZERO_DECIMAL,
            "taxes_cash": ZERO_DECIMAL,
            "net_profit_accrual": ZERO_DECIMAL,
            "net_profit_cash": ZERO_DECIMAL,
        }

    # Р”Р»СЏ РіСЂСѓРїРїРёСЂРѕРІРєРё РЅСѓР¶РЅС‹ РїРѕРґР·Р°РїСЂРѕСЃС‹ РїРѕ РєР°Р¶РґРѕРјСѓ РїРµСЂРёРѕРґСѓ РёР»Рё РёСЃРїРѕР»СЊР·РѕРІР°РЅРёРµ strftime
    # SQLite: strftime('%Y-%m', date) РґР»СЏ РіСЂСѓРїРїРёСЂРѕРІРєРё РїРѕ РјРµСЃСЏС†Сѓ
    if group_by == "day":
        grp = func.strftime("%Y-%m-%d", income_date_col)
        grp_paid_i = func.strftime("%Y-%m-%d", income_paid_col)
        grp_exp = func.strftime("%Y-%m-%d", expense_date_col)
        grp_paid_e = func.strftime("%Y-%m-%d", expense_paid_col)
    elif group_by == "month":
        grp = func.strftime("%Y-%m", income_date_col)
        grp_paid_i = func.strftime("%Y-%m", income_paid_col)
        grp_exp = func.strftime("%Y-%m", expense_date_col)
        grp_paid_e = func.strftime("%Y-%m", expense_paid_col)
    else:
        grp = func.strftime("%Y", income_date_col)
        grp_paid_i = func.strftime("%Y", income_paid_col)
        grp_exp = func.strftime("%Y", expense_date_col)
        grp_paid_e = func.strftime("%Y", expense_paid_col)

    need_accrual = mode in ("accrual", "both")
    need_cash = mode in ("cash", "both")

    if need_accrual:
        # revenue_accrual РїРѕ issued_date
        q_ra = (
            select(grp.label("period"), func.coalesce(func.sum(income_amount), 0).label("s"))
            .where(income_base)
            .group_by(grp)
        )
        r = await db.execute(q_ra)
        for row in r.fetchall():
            p = str(row.period)
            if p in periods_data:
                periods_data[p]["revenue_accrual"] = to_decimal(row.s)

        # expense_accrual РїРѕ date
        q_ea = (
            select(grp_exp.label("period"), func.coalesce(func.sum(expense_amount), 0).label("s"))
            .where(expense_accrual_base)
            .group_by(grp_exp)
        )
        r = await db.execute(q_ea)
        for row in r.fetchall():
            p = str(row.period)
            if p in periods_data:
                periods_data[p]["expense_accrual"] = to_decimal(row.s)

    if need_cash:
        bt_date = BankTransaction.date
        bt_amount = BankTransaction.amount
        bt_direction = BankTransaction.direction
        bt_status = BankTransaction.status
        bt_type = BankTransaction.matched_type

        # Р“СЂСѓРїРїРёСЂРѕРІРєР°
        if group_by == "day":
            grp_bt = func.strftime("%Y-%m-%d", bt_date)
        elif group_by == "month":
            grp_bt = func.strftime("%Y-%m", bt_date)
        else:
            grp_bt = func.strftime("%Y", bt_date)

        # Inflow - РІСЃРµ РїРѕСЃС‚СѓРїР»РµРЅРёСЏ (direction="in", status != "ignored")
        if client_id is not None or contract_id is not None or project_id is not None:
            q_rc_direct = (
                select(grp_bt.label("period"), func.coalesce(func.sum(bt_amount), 0).label("s"))
                .join(Income, BankTransaction.matched_id == Income.id)
                .where(
                    bt_direction == "in",
                    bt_status != "ignored",
                    bt_date >= date_from,
                    bt_date <= date_to,
                    BankTransaction.matched_type == "income",
                )
            )
            if client_id is not None:
                q_rc_direct = q_rc_direct.where(Income.client_id == client_id)
            if contract_id is not None:
                q_rc_direct = q_rc_direct.where(Income.contract_id == contract_id)
            if project_id is not None:
                q_rc_direct = q_rc_direct.where(Income.project_id == project_id)
            q_rc_direct = q_rc_direct.group_by(grp_bt)
            r = await db.execute(q_rc_direct)
            for row in r.fetchall():
                _append_period_amount(periods_data, str(row.period), "revenue_cash", row.s)

            q_rc_alloc = (
                select(grp_bt.label("period"), func.coalesce(func.sum(BankTransactionIncomeAllocation.amount), 0).label("s"))
                .join(BankTransactionIncomeAllocation, BankTransactionIncomeAllocation.bank_transaction_id == BankTransaction.id)
                .join(Income, BankTransactionIncomeAllocation.income_id == Income.id)
                .where(
                    bt_direction == "in",
                    bt_status != "ignored",
                    bt_date >= date_from,
                    bt_date <= date_to,
                    BankTransaction.matched_type == "income_allocation",
                )
            )
            if client_id is not None:
                q_rc_alloc = q_rc_alloc.where(Income.client_id == client_id)
            if contract_id is not None:
                q_rc_alloc = q_rc_alloc.where(Income.contract_id == contract_id)
            if project_id is not None:
                q_rc_alloc = q_rc_alloc.where(Income.project_id == project_id)
            q_rc_alloc = q_rc_alloc.group_by(grp_bt)
            r = await db.execute(q_rc_alloc)
            for row in r.fetchall():
                _append_period_amount(periods_data, str(row.period), "revenue_cash", row.s)
        else:
            q_rc = (
                select(grp_bt.label("period"), func.coalesce(func.sum(bt_amount), 0).label("s"))
                .where(
                    bt_direction == "in",
                    bt_status != "ignored",
                    bt_date >= date_from,
                    bt_date <= date_to,
                )
                .group_by(grp_bt)
            )
            r = await db.execute(q_rc)
            for row in r.fetchall():
                periods_data[str(row.period)]["revenue_cash"] = to_decimal(row.s)

        # Outflow (expenses + obligations)
        # Р•СЃР»Рё РЅРµС‚ С„РёР»СЊС‚СЂРѕРІ tax / category, РїСЂРѕСЃС‚Рѕ Р±РµСЂРµРј РІСЃРµ out != ignored
        q_ec = (
            select(grp_bt.label("period"), func.coalesce(func.sum(bt_amount), 0).label("s"))
            .where(
                bt_direction == "out",
                bt_status != "ignored",
                bt_date >= date_from,
                bt_date <= date_to,
            )
        )

        if category is not None or is_tax_related is not None:
            # Р”Р»СЏ С„РёР»СЊС‚СЂРѕРІ РЅСѓР¶РЅРѕ РїРѕРґС‚СЏРЅСѓС‚СЊ Expense
            q_ec = q_ec.join(Expense, BankTransaction.matched_id == Expense.id).where(
                BankTransaction.matched_type == "expense",
                Expense.source != CASH_TRANSFER_SOURCE,
            )
            if category is not None:
                q_ec = q_ec.where(Expense.category == category)
            if is_tax_related is not None:
                q_ec = q_ec.where(Expense.is_tax_related == (1 if is_tax_related else 0))

        q_ec = q_ec.group_by(grp_bt)
        r = await db.execute(q_ec)
        for row in r.fetchall():
            p = str(row.period)
            if p in periods_data:
                periods_data[p]["expense_cash"] += to_decimal(row.s)
                
        # Р•СЃР»Рё РЅРµ Р±С‹Р»Рѕ С„РёР»СЊС‚СЂРѕРІ, РґРѕР±Р°РІРёРј Рё obligation outflow
        if category is None and is_tax_related is None:
            pass # obligations СѓР¶Рµ РїРѕСЃС‡РёС‚Р°РЅС‹ РІ РѕР±С‰РµРј bt_direction=="out"
        elif is_tax_related:
             # Р•СЃР»Рё РёСЃРєР°Р»Рё РЅР°Р»РѕРіРё, obligation (Р·Р°СЂРїР»Р°С‚РЅС‹Рµ РЅР°Р»РѕРіРё) С‚СѓРґР° С‚РѕР¶Рµ РїР»СЋСЃСѓРµРј
             q_ob = (
                select(grp_bt.label("period"), func.coalesce(func.sum(bt_amount), 0).label("s"))
                .where(
                    bt_direction == "out",
                    bt_status != "ignored",
                    bt_date >= date_from,
                    bt_date <= date_to,
                    bt_type == "obligation"
                )
             )
             q_ob = q_ob.group_by(grp_bt)
             r = await db.execute(q_ob)
             for row in r.fetchall():
                p = str(row.period)
                if p in periods_data:
                    periods_data[p]["expense_cash"] += to_decimal(row.s)

        # taxes_cash (is_tax_related == True РёР»Рё obligations)
        # РЎСѓРјРјРёСЂСѓРµРј Expense is_tax=True Рё РІСЃРµ MonthlyObligation
        q_tc1 = (
            select(grp_bt.label("period"), func.coalesce(func.sum(bt_amount), 0).label("s"))
            .join(Expense, BankTransaction.matched_id == Expense.id)
            .where(
                bt_direction == "out",
                bt_status != "ignored",
                BankTransaction.matched_type == "expense",
                Expense.source != CASH_TRANSFER_SOURCE,
                Expense.is_tax_related == True,
                bt_date >= date_from,
                bt_date <= date_to,
            )
            .group_by(grp_bt)
        )
        r = await db.execute(q_tc1)
        for row in r.fetchall():
            p = str(row.period)
            if p in periods_data:
                periods_data[p]["taxes_cash"] += to_decimal(row.s)

        q_tc2 = (
            select(grp_bt.label("period"), func.coalesce(func.sum(bt_amount), 0).label("s"))
            .where(
                bt_direction == "out",
                bt_status != "ignored",
                bt_type == "obligation",
                bt_date >= date_from,
                bt_date <= date_to,
            )
            .group_by(grp_bt)
        )
        r = await db.execute(q_tc2)
        for row in r.fetchall():
            p = str(row.period)
            if p in periods_data:
                periods_data[p]["taxes_cash"] += to_decimal(row.s)

    # net profit
    for p, data in periods_data.items():
        data["net_profit_accrual"] = data["revenue_accrual"] - data["expense_accrual"]
        data["net_profit_cash"] = data["revenue_cash"] - data["expense_cash"]

    # РС‚РѕРіРё Р·Р° РІРµСЃСЊ РїРµСЂРёРѕРґ
    totals = {
        "revenue_accrual": sum(d["revenue_accrual"] for d in periods_data.values()),
        "revenue_cash": sum(d["revenue_cash"] for d in periods_data.values()),
        "expense_accrual": sum(d["expense_accrual"] for d in periods_data.values()),
        "expense_cash": sum(d["expense_cash"] for d in periods_data.values()),
        "taxes_cash": sum(d["taxes_cash"] for d in periods_data.values()),
    }
    totals["net_profit_accrual"] = totals["revenue_accrual"] - totals["expense_accrual"]
    totals["net_profit_cash"] = totals["revenue_cash"] - totals["expense_cash"]

    return {
        "range": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "group_by": group_by,
        "mode": mode,
        "series": [{"period": k, **v} for k, v in sorted(periods_data.items())],
        "totals": totals,
    }


async def get_accounts_receivable(db: AsyncSession, as_of: Optional[date] = None) -> dict:
    """
    Р”РµР±РёС‚РѕСЂСЃРєР°СЏ Р·Р°РґРѕР»Р¶РµРЅРЅРѕСЃС‚СЊ: unpaid Рё partial incomes.
    Р”Р»СЏ partial РїРѕРєР°Р·С‹РІР°РµС‚ РѕСЃС‚Р°С‚РѕРє (amount_rsd - paid_amount).
    """
    today = as_of or date.today()
    q = select(Income).options(selectinload(Income.client)).where(
        Income.status.in_(["issued", "partial"]),
        Income.issued_date <= today,
    ).order_by(Income.issued_date.asc())
    r = await db.execute(q)
    incomes = r.scalars().all()
    items = []
    ar_total = ZERO_DECIMAL
    ar_overdue = ZERO_DECIMAL
    for i in incomes:
        # Р”Р»СЏ С‡Р°СЃС‚РёС‡РЅРѕР№ РѕРїР»Р°С‚С‹ РїРѕРєР°Р·С‹РІР°РµРј РѕСЃС‚Р°С‚РѕРє
        remaining = to_decimal(i.amount_rsd) - to_decimal(i.paid_amount or ZERO_DECIMAL)
        if remaining <= 0:
            continue
        days_out = (today - i.issued_date).days
        due_dt = i.due_date or (i.issued_date + timedelta(days=30))
        days_overdue = (today - due_dt).days
        items.append({
            "income_id": i.id,
            "invoice_number": i.invoice_number,
            "client_name": i.client_name or (i.client.name if i.client else None),
            "issued_date": i.issued_date.isoformat(),
            "due_date": due_dt.isoformat(),
            "amount": float(remaining),          # РѕСЃС‚Р°С‚РѕРє Рє РѕРїР»Р°С‚Рµ
            "amount_full": float(to_decimal(i.amount_rsd)),
            "amount_paid": float(to_decimal(i.paid_amount or ZERO_DECIMAL)),
            "status": i.status,
            "days_outstanding": days_out,
            "days_overdue": days_overdue,
        })
        ar_total += remaining
        if days_overdue > 0:
            ar_overdue += remaining
    return {
        "items": items,
        "totals": {"ar_total": float(ar_total), "ar_overdue": float(ar_overdue)},
    }


async def get_cashflow(
    db: AsyncSession,
    date_from: date,
    date_to: date,
    group_by: Literal["day", "month", "year"],
) -> dict:
    """
    Cash flow: opening + inflow - outflow = closing (cumulative).
    inflow = revenue_cash, outflow = expense_cash.
    opening for the first point is the balance at the selected range start.
    """
    r = await db.execute(select(Enterprise).limit(1))
    ent = r.scalar_one_or_none()
    opening_cash_balance = to_decimal(ent.opening_cash_balance) if ent and ent.opening_cash_balance is not None else ZERO_DECIMAL
    opening_cash_date = ent.opening_cash_date if ent and ent.opening_cash_date is not None else None

    bt_date = BankTransaction.date
    bt_amount = BankTransaction.amount
    bt_direction = BankTransaction.direction
    bt_status = BankTransaction.status

    async def _sum_bank(direction: str, start: Optional[date] = None, end: Optional[date] = None) -> float:
        conditions = [bt_direction == direction, bt_status != "ignored"]
        if start is not None:
            conditions.append(bt_date >= start)
        if end is not None:
            conditions.append(bt_date < end)
        q = select(func.coalesce(func.sum(bt_amount), 0)).where(*conditions)
        value = await db.scalar(q)
        return to_decimal(value or ZERO_DECIMAL)

    opening_balance_at_range_start = opening_cash_balance
    if opening_cash_date is None or opening_cash_date < date_from:
        inflow_before = await _sum_bank("in", opening_cash_date, date_from)
        outflow_before = await _sum_bank("out", opening_cash_date, date_from)
        opening_balance_at_range_start += inflow_before - outflow_before
    elif opening_cash_date > date_from:
        inflow_after = await _sum_bank("in", date_from, opening_cash_date)
        outflow_after = await _sum_bank("out", date_from, opening_cash_date)
        opening_balance_at_range_start -= inflow_after - outflow_after

    summary = await get_finance_summary(db, date_from, date_to, group_by, "cash", None)
    series = summary.get("series", [])

    result_series = []
    prev_closing = opening_balance_at_range_start
    for s in series:
        inflow = to_decimal(s.get("revenue_cash", ZERO_DECIMAL) or ZERO_DECIMAL)
        outflow = to_decimal(s.get("expense_cash", ZERO_DECIMAL) or ZERO_DECIMAL)
        opening = prev_closing
        closing = opening + inflow - outflow
        prev_closing = closing
        result_series.append({
            "period": s["period"],
            "opening": opening,
            "inflow": inflow,
            "outflow": outflow,
            "closing": closing,
        })

    return {
        "range": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "group_by": group_by,
        "opening_cash_balance": opening_balance_at_range_start,
        "series": result_series,
    }


async def get_finance_by_project(
    db: AsyncSession,
    date_from: date,
    date_to: date,
    mode: Literal["accrual", "cash"] = "accrual",
) -> dict:
    """
    РђРЅР°Р»РёС‚РёРєР° РїРѕ РїСЂРѕРµРєС‚Р°Рј: revenue, expenses, profit, margin_percent.
    Р¤РѕСЂРјР°С‚: by_project[], unassigned.

    mode=accrual: РґРѕС…РѕРґС‹ РїРѕ Income.issued_date, СЂР°СЃС…РѕРґС‹ РїРѕ Expense.date.
    mode=cash: РґРѕС…РѕРґС‹ РїРѕ Income.paid_date (С‚РѕР»СЊРєРѕ paid), СЂР°СЃС…РѕРґС‹ РїРѕ Expense.paid_date (С‚РѕР»СЊРєРѕ paid).
    """
    income_date_col = Income.issued_date
    income_paid_col = Income.paid_date
    income_amount = Income.amount_rsd
    income_status = Income.status

    expense_date_col = Expense.date
    expense_paid_col = Expense.paid_date
    expense_amount = Expense.amount
    expense_status = Expense.status

    if mode == "accrual":
        # Р”РѕС…РѕРґС‹: issued_date РІ РїРµСЂРёРѕРґРµ, status != cancelled
        income_base = and_(
            income_status != "cancelled",
            income_date_col >= date_from,
            income_date_col <= date_to,
        )
        # Р Р°СЃС…РѕРґС‹: date РІ РїРµСЂРёРѕРґРµ, РІРєР»СЋС‡Р°СЏ СЃС‚РѕСЂРЅРѕ (reversed), РЅРѕ Р±РµР· planned
        expense_base = and_(
            _visible_expense_condition(),
            Expense.source != CASH_TRANSFER_SOURCE,
            expense_date_col >= date_from,
            expense_date_col <= date_to,
        )
    else:
        # cash: РґРѕС…РѕРґС‹ вЂ” С‚РѕР»СЊРєРѕ paid, РїРѕ paid_date
        income_base = and_(
            income_status == "paid",
            income_paid_col.isnot(None),
            income_paid_col >= date_from,
            income_paid_col <= date_to,
        )
        # cash: СЂР°СЃС…РѕРґС‹ вЂ” paid Рё reversed, РїРѕ paid_date (РµСЃР»Рё РЅРµС‚ paid_date вЂ” РЅРµ СЃС‡РёС‚Р°РµРј)
        expense_base = and_(
            expense_status.in_(["paid", "reversed"]),
            Expense.source != CASH_TRANSFER_SOURCE,
            expense_paid_col.isnot(None),
            expense_paid_col >= date_from,
            expense_paid_col <= date_to,
        )

    # Р’СЃРµ РїСЂРѕРµРєС‚С‹ (РґР»СЏ СЃРѕРѕС‚РІРµС‚СЃС‚РІРёСЏ СЃРїРёСЃРєСѓ РЅР° С„СЂРѕРЅС‚Рµ РїСЂРё show_archived)
    r = await db.execute(select(Project).order_by(Project.name))
    projects = list(r.scalars().all())
    project_ids = [p.id for p in projects]
    all_ids = project_ids + [None]  # None = Р±РµР· РїСЂРѕРµРєС‚Р°

    by_project = []
    unassigned = {"revenue": 0.0, "expenses": 0.0, "profit": 0.0}

    for pid in all_ids:
        name = "вЂ” Р‘РµР· РїСЂРѕРµРєС‚Р° вЂ”" if pid is None else next((p.name for p in projects if p.id == pid), f"Project {pid}")

        # Revenue РїРѕ РїСЂРѕРµРєС‚Сѓ
        if mode == "accrual":
            inc_cond = and_(income_base, Income.project_id == pid)
            q_rev = select(func.coalesce(func.sum(income_amount), 0)).where(inc_cond)
            r = await db.execute(q_rev)
            revenue = to_decimal(r.scalar() or ZERO_DECIMAL)
            
            exp_cond = and_(expense_base, Expense.project_id == pid)
            q_exp = select(func.coalesce(func.sum(expense_amount), 0)).where(exp_cond)
            r = await db.execute(q_exp)
            expenses = to_decimal(r.scalar() or ZERO_DECIMAL)
        else:
            # cash: Revenue - direct matches + allocated incoming payments
            q_rev_direct = (
                select(func.coalesce(func.sum(BankTransaction.amount), 0))
                .select_from(BankTransaction)
                .join(Income, BankTransaction.matched_id == Income.id)
                .where(
                    and_(
                        BankTransaction.direction == "in",
                        BankTransaction.status != "ignored",
                        BankTransaction.matched_type == "income",
                        BankTransaction.date >= date_from,
                        BankTransaction.date <= date_to,
                        Income.project_id == pid,
                    )
                )
            )
            r = await db.execute(q_rev_direct)
            revenue = to_decimal(r.scalar() or ZERO_DECIMAL)

            q_rev_alloc = (
                select(func.coalesce(func.sum(BankTransactionIncomeAllocation.amount), 0))
                .select_from(BankTransaction)
                .join(BankTransactionIncomeAllocation, BankTransactionIncomeAllocation.bank_transaction_id == BankTransaction.id)
                .join(Income, BankTransactionIncomeAllocation.income_id == Income.id)
                .where(
                    and_(
                        BankTransaction.direction == "in",
                        BankTransaction.status != "ignored",
                        BankTransaction.matched_type == "income_allocation",
                        BankTransaction.date >= date_from,
                        BankTransaction.date <= date_to,
                        Income.project_id == pid,
                    )
                )
            )
            r = await db.execute(q_rev_alloc)
            revenue += to_decimal(r.scalar() or ZERO_DECIMAL)

            # cash: Expenses - sum of BankTransaction out, matched to expense with this project_id
            q_exp = (
                select(func.coalesce(func.sum(BankTransaction.amount), 0))
                .select_from(BankTransaction)
                .join(Expense, BankTransaction.matched_id == Expense.id)
                .where(
                    and_(
                        BankTransaction.direction == "out",
                        BankTransaction.status != "ignored",
                        BankTransaction.matched_type == "expense",
                        Expense.source != CASH_TRANSFER_SOURCE,
                        BankTransaction.date >= date_from,
                        BankTransaction.date <= date_to,
                        Expense.project_id == pid,
                    )
                )
            )
            r = await db.execute(q_exp)
            expenses = to_decimal(r.scalar() or ZERO_DECIMAL)

        profit = revenue - expenses
        margin_percent = float(((profit / revenue) * Decimal("100")).quantize(Decimal("0.1"))) if revenue and revenue > ZERO_DECIMAL else 0.0

        row = {
            "project_id": pid,
            "project_name": name,
            "revenue": revenue,
            "expenses": expenses,
            "profit": profit,
            "margin_percent": margin_percent,
        }
        by_project.append(row)

        if pid is None:
            unassigned = {"revenue": revenue, "expenses": expenses, "profit": profit}

    return {
        "range": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "mode": mode,
        "by_project": by_project,
        "unassigned": unassigned,
    }


async def get_project_movement_bounds(
    db: AsyncSession,
    project_ids: Optional[list[int]] = None,
) -> dict[int, dict[str, Optional[date]]]:
    if project_ids is not None and not project_ids:
        return {}

    bounds: dict[int, dict[str, Optional[date]]] = {}

    income_conditions = [
        Income.project_id.isnot(None),
        Income.status != "cancelled",
    ]
    if project_ids is not None:
        income_conditions.append(Income.project_id.in_(project_ids))

    income_rows = await db.execute(
        select(
            Income.project_id,
            func.min(Income.issued_date),
            func.max(Income.issued_date),
        ).where(
            and_(*income_conditions)
        ).group_by(Income.project_id)
    )

    for project_id, min_date, max_date in income_rows.fetchall():
        if project_id is None:
            continue
        entry = bounds.setdefault(project_id, {"first_movement_date": None, "last_movement_date": None})
        if min_date is not None and (entry["first_movement_date"] is None or min_date < entry["first_movement_date"]):
            entry["first_movement_date"] = min_date
        if max_date is not None and (entry["last_movement_date"] is None or max_date > entry["last_movement_date"]):
            entry["last_movement_date"] = max_date

    expense_conditions = [
        _visible_expense_condition(),
        Expense.source != CASH_TRANSFER_SOURCE,
        Expense.project_id.isnot(None),
    ]
    if project_ids is not None:
        expense_conditions.append(Expense.project_id.in_(project_ids))

    expense_rows = await db.execute(
        select(
            Expense.project_id,
            func.min(Expense.date),
            func.max(Expense.date),
        ).where(
            and_(*expense_conditions)
        ).group_by(Expense.project_id)
    )

    for project_id, min_date, max_date in expense_rows.fetchall():
        if project_id is None:
            continue
        entry = bounds.setdefault(project_id, {"first_movement_date": None, "last_movement_date": None})
        if min_date is not None and (entry["first_movement_date"] is None or min_date < entry["first_movement_date"]):
            entry["first_movement_date"] = min_date
        if max_date is not None and (entry["last_movement_date"] is None or max_date > entry["last_movement_date"]):
            entry["last_movement_date"] = max_date

    return bounds


async def get_project_movements(
    db: AsyncSession,
    project_id: int,
    date_from: date,
    date_to: date,
    mode: Literal["accrual", "cash"] = "accrual",
) -> dict:
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not project:
        raise ValueError("Project not found")

    items: list[dict[str, Any]] = []

    if mode == "accrual":
        income_rows = await db.execute(
            select(
                Income.id,
                Income.issued_date,
                Income.invoice_number,
                Income.client_name,
                Income.description,
                Income.amount_rsd,
                Income.status,
            ).where(
                and_(
                    Income.project_id == project_id,
                    Income.status != "cancelled",
                    Income.issued_date >= date_from,
                    Income.issued_date <= date_to,
                )
            )
        )
        for income_id, issued_date, invoice_number, client_name, description, amount_rsd, status in income_rows.fetchall():
            items.append({
                "row_key": f"income-{income_id}",
                "date": issued_date,
                "direction": "in",
                "movement_type": "income",
                "source_kind": "income",
                "document_number": invoice_number,
                "counterparty_name": client_name,
                "description": description,
                "amount": to_decimal(amount_rsd or ZERO_DECIMAL),
                "status": status,
            })

        expense_rows = await db.execute(
            select(
                Expense.id,
                Expense.date,
                Expense.bank_reference,
                Expense.description,
                Expense.amount,
                Expense.status,
            ).where(
                and_(
                    _visible_expense_condition(),
                    Expense.project_id == project_id,
                    Expense.source != CASH_TRANSFER_SOURCE,
                    Expense.date >= date_from,
                    Expense.date <= date_to,
                )
            )
        )
        for expense_id, expense_date, bank_reference, description, amount, status in expense_rows.fetchall():
            items.append({
                "row_key": f"expense-{expense_id}",
                "date": expense_date,
                "direction": "out",
                "movement_type": "expense",
                "source_kind": "expense",
                "document_number": bank_reference,
                "counterparty_name": None,
                "description": description,
                "amount": abs(to_decimal(amount or ZERO_DECIMAL)),
                "status": status,
            })
    else:
        direct_income_rows = await db.execute(
            select(
                BankTransaction.id,
                BankTransaction.date,
                Income.invoice_number,
                BankTransaction.counterparty_name,
                BankTransaction.purpose,
                Income.description,
                BankTransaction.amount,
                BankTransaction.status,
            )
            .select_from(BankTransaction)
            .join(Income, BankTransaction.matched_id == Income.id)
            .where(
                and_(
                    BankTransaction.direction == "in",
                    BankTransaction.status != "ignored",
                    BankTransaction.matched_type == "income",
                    BankTransaction.date >= date_from,
                    BankTransaction.date <= date_to,
                    Income.project_id == project_id,
                )
            )
        )
        for tx_id, tx_date, invoice_number, counterparty_name, purpose, description, amount, status in direct_income_rows.fetchall():
            items.append({
                "row_key": f"bank-income-{tx_id}",
                "date": tx_date,
                "direction": "in",
                "movement_type": "income",
                "source_kind": "bank",
                "document_number": invoice_number,
                "counterparty_name": counterparty_name,
                "description": purpose or description,
                "amount": abs(to_decimal(amount or ZERO_DECIMAL)),
                "status": status,
            })

        allocated_income_rows = await db.execute(
            select(
                BankTransaction.id,
                BankTransactionIncomeAllocation.id,
                BankTransaction.date,
                Income.invoice_number,
                BankTransaction.counterparty_name,
                BankTransaction.purpose,
                Income.description,
                BankTransactionIncomeAllocation.amount,
                BankTransaction.status,
            )
            .select_from(BankTransaction)
            .join(BankTransactionIncomeAllocation, BankTransactionIncomeAllocation.bank_transaction_id == BankTransaction.id)
            .join(Income, BankTransactionIncomeAllocation.income_id == Income.id)
            .where(
                and_(
                    BankTransaction.direction == "in",
                    BankTransaction.status != "ignored",
                    BankTransaction.matched_type == "income_allocation",
                    BankTransaction.date >= date_from,
                    BankTransaction.date <= date_to,
                    Income.project_id == project_id,
                )
            )
        )
        for tx_id, allocation_id, tx_date, invoice_number, counterparty_name, purpose, description, amount, status in allocated_income_rows.fetchall():
            items.append({
                "row_key": f"bank-income-allocation-{allocation_id}",
                "date": tx_date,
                "direction": "in",
                "movement_type": "income",
                "source_kind": "allocation",
                "document_number": invoice_number,
                "counterparty_name": counterparty_name,
                "description": purpose or description,
                "amount": abs(to_decimal(amount or ZERO_DECIMAL)),
                "status": status,
            })

        expense_cash_rows = await db.execute(
            select(
                BankTransaction.id,
                BankTransaction.date,
                Expense.bank_reference,
                BankTransaction.counterparty_name,
                BankTransaction.purpose,
                Expense.description,
                BankTransaction.amount,
                BankTransaction.status,
            )
            .select_from(BankTransaction)
            .join(Expense, BankTransaction.matched_id == Expense.id)
            .where(
                and_(
                    BankTransaction.direction == "out",
                    BankTransaction.status != "ignored",
                    BankTransaction.matched_type == "expense",
                    Expense.source != CASH_TRANSFER_SOURCE,
                    BankTransaction.date >= date_from,
                    BankTransaction.date <= date_to,
                    Expense.project_id == project_id,
                )
            )
        )
        for tx_id, tx_date, bank_reference, counterparty_name, purpose, description, amount, status in expense_cash_rows.fetchall():
            items.append({
                "row_key": f"bank-expense-{tx_id}",
                "date": tx_date,
                "direction": "out",
                "movement_type": "expense",
                "source_kind": "bank",
                "document_number": bank_reference,
                "counterparty_name": counterparty_name,
                "description": purpose or description,
                "amount": abs(to_decimal(amount or ZERO_DECIMAL)),
                "status": status,
            })

    items.sort(key=lambda item: (item["date"], item["direction"] == "out", item["row_key"]), reverse=True)

    return {
        "project_id": project.id,
        "project_name": project.name,
        "mode": mode,
        "from_date": date_from,
        "to_date": date_to,
        "items": items,
    }




async def get_finance_pnl(db: AsyncSession, year: int) -> dict:
    """Monthly accrual-based P&L by Income.issued_date and Expense.date."""
    date_from = date(year, 1, 1)
    date_to = date(year, 12, 31)

    months: dict[int, dict[str, Decimal]] = {
        month: {
            "revenue": ZERO_DECIMAL,
            "expenses": ZERO_DECIMAL,
            "taxes": ZERO_DECIMAL,
            "profit": ZERO_DECIMAL,
        }
        for month in range(1, 13)
    }

    revenue_rows = await db.execute(
        select(
            func.strftime("%m", Income.issued_date).label("month"),
            func.coalesce(func.sum(Income.amount_rsd), 0).label("amount"),
        ).where(
            Income.status != "cancelled",
            Income.issued_date >= date_from,
            Income.issued_date <= date_to,
        ).group_by(func.strftime("%m", Income.issued_date))
    )
    for row in revenue_rows.fetchall():
        months[int(row.month)]["revenue"] = to_decimal(row.amount)

    operating_rows = await db.execute(
        select(
            func.strftime("%m", Expense.date).label("month"),
            func.coalesce(func.sum(Expense.amount), 0).label("amount"),
        ).where(
            _visible_expense_condition(),
            Expense.status != "reversed",
            Expense.source != CASH_TRANSFER_SOURCE,
            Expense.date >= date_from,
            Expense.date <= date_to,
            func.coalesce(Expense.is_tax_related, False) == False,
        ).group_by(func.strftime("%m", Expense.date))
    )
    for row in operating_rows.fetchall():
        months[int(row.month)]["expenses"] = to_decimal(row.amount)

    tax_rows = await db.execute(
        select(
            func.strftime("%m", Expense.date).label("month"),
            func.coalesce(func.sum(Expense.amount), 0).label("amount"),
        ).where(
            _visible_expense_condition(),
            Expense.status != "reversed",
            Expense.source != CASH_TRANSFER_SOURCE,
            Expense.date >= date_from,
            Expense.date <= date_to,
            Expense.is_tax_related == True,
        ).group_by(func.strftime("%m", Expense.date))
    )
    for row in tax_rows.fetchall():
        months[int(row.month)]["taxes"] = to_decimal(row.amount)

    items = []
    totals = {
        "revenue": ZERO_DECIMAL,
        "expenses": ZERO_DECIMAL,
        "taxes": ZERO_DECIMAL,
        "profit": ZERO_DECIMAL,
    }
    for month in range(1, 13):
        revenue = months[month]["revenue"]
        expenses = months[month]["expenses"]
        taxes = months[month]["taxes"]
        profit = revenue - expenses - taxes
        items.append({
            "month": month,
            "revenue": revenue,
            "expenses": expenses,
            "taxes": taxes,
            "profit": profit,
        })
        totals["revenue"] += revenue
        totals["expenses"] += expenses
        totals["taxes"] += taxes
        totals["profit"] += profit

    return {
        "year": year,
        "items": items,
        "totals": totals,
    }


async def get_finance_pnl_years(db: AsyncSession) -> list[int]:
    income_rows = await db.execute(
        select(func.distinct(func.strftime("%Y", Income.issued_date)).label("year"))
        .where(
            Income.status != "cancelled",
            Income.issued_date.isnot(None),
        )
    )
    expense_rows = await db.execute(
        select(func.distinct(func.strftime("%Y", Expense.date)).label("year"))
        .where(
            _visible_expense_condition(),
            Expense.status != "reversed",
            Expense.source != CASH_TRANSFER_SOURCE,
            Expense.date.isnot(None),
        )
    )

    years = {
        int(row.year)
        for row in income_rows.fetchall() + expense_rows.fetchall()
        if row.year
    }
    return sorted(years, reverse=True)
