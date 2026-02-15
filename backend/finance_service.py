"""Финансовый сервис: метрики accrual vs cash."""
from datetime import date, timedelta
from typing import Literal, Optional, Any
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import Income, Expense, Enterprise, Project, CashTransaction


def _period_key(d: date, group_by: Literal["day", "month", "year"]) -> str:
    """Ключ периода: YYYY-MM-DD | YYYY-MM | YYYY."""
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
    """Итератор по периодам в диапазоне."""
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
    Агрегатор метрик для accrual/cash.
    filters: client_id, contract_id, project_id (income), category, is_tax_related (expenses)
    """
    filters = filters or {}
    client_id = filters.get("client_id")
    contract_id = filters.get("contract_id")
    project_id = filters.get("project_id")
    category = filters.get("category")
    is_tax_related = filters.get("is_tax_related")

    # SQLite: date column в income называется "date" (issued_date в модели)
    income_date_col = Income.issued_date
    income_paid_col = Income.paid_date
    income_amount = Income.amount_rsd
    income_status = Income.status

    expense_date_col = Expense.date
    expense_paid_col = Expense.paid_date
    expense_amount = Expense.amount
    expense_status = Expense.status
    expense_is_tax = Expense.is_tax_related

    # Базовые условия для income
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

    # Базовые условия для expenses (accrual: date in period, status != reversed)
    expense_accrual_base = and_(
        expense_status != "reversed",
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

    # Cash: paid_date in period, status == paid (и не reversed — paid уже подразумевает не reversed)
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
        expense_status == "paid",
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
        expense_status == "paid",
        expense_is_tax == True,
        expense_paid_col.isnot(None),
        expense_paid_col >= date_from,
        expense_paid_col <= date_to,
    )
    if category is not None:
        expense_tax_base = and_(expense_tax_base, Expense.category == category)

    # Формат для GROUP BY в SQLite
    if group_by == "day":
        fmt = "%Y-%m-%d"
    elif group_by == "month":
        fmt = "%Y-%m"
    else:
        fmt = "%Y"

    periods_data: dict[str, dict[str, float]] = {}
    for pk in _iter_periods(date_from, date_to, group_by):
        periods_data[pk] = {
            "revenue_accrual": 0.0,
            "revenue_cash": 0.0,
            "expense_accrual": 0.0,
            "expense_cash": 0.0,
            "taxes_cash": 0.0,
            "net_profit_accrual": 0.0,
            "net_profit_cash": 0.0,
        }

    # Для группировки нужны подзапросы по каждому периоду или использование strftime
    # SQLite: strftime('%Y-%m', date) для группировки по месяцу
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
        # revenue_accrual по issued_date
        q_ra = (
            select(grp.label("period"), func.coalesce(func.sum(income_amount), 0).label("s"))
            .where(income_base)
            .group_by(grp)
        )
        r = await db.execute(q_ra)
        for row in r.fetchall():
            p = str(row.period)
            if p in periods_data:
                periods_data[p]["revenue_accrual"] = float(row.s)

        # expense_accrual по date
        q_ea = (
            select(grp_exp.label("period"), func.coalesce(func.sum(expense_amount), 0).label("s"))
            .where(expense_accrual_base)
            .group_by(grp_exp)
        )
        r = await db.execute(q_ea)
        for row in r.fetchall():
            p = str(row.period)
            if p in periods_data:
                periods_data[p]["expense_accrual"] = float(row.s)

    if need_cash:
        # revenue_cash из cash_transactions (создаётся при mark-paid invoice)
        ct_date = CashTransaction.date
        ct_amount = CashTransaction.amount
        if group_by == "day":
            grp_ct = func.strftime("%Y-%m-%d", ct_date)
        elif group_by == "month":
            grp_ct = func.strftime("%Y-%m", ct_date)
        else:
            grp_ct = func.strftime("%Y", ct_date)
        q_rc = (
            select(grp_ct.label("period"), func.coalesce(func.sum(ct_amount), 0).label("s"))
            .where(
                and_(
                    CashTransaction.type == "income",
                    ct_date >= date_from,
                    ct_date <= date_to,
                )
            )
            .group_by(grp_ct)
        )
        r = await db.execute(q_rc)
        for row in r.fetchall():
            p = str(row.period)
            if p in periods_data:
                periods_data[p]["revenue_cash"] = float(row.s)

        # expense_cash по paid_date
        q_ec = (
            select(grp_paid_e.label("period"), func.coalesce(func.sum(expense_amount), 0).label("s"))
            .where(expense_cash_base)
            .group_by(grp_paid_e)
        )
        r = await db.execute(q_ec)
        for row in r.fetchall():
            p = str(row.period)
            if p in periods_data:
                periods_data[p]["expense_cash"] = float(row.s)

        # taxes_cash
        q_tc = (
            select(grp_paid_e.label("period"), func.coalesce(func.sum(expense_amount), 0).label("s"))
            .where(expense_tax_base)
            .group_by(grp_paid_e)
        )
        r = await db.execute(q_tc)
        for row in r.fetchall():
            p = str(row.period)
            if p in periods_data:
                periods_data[p]["taxes_cash"] = float(row.s)

    # net profit
    for p, data in periods_data.items():
        data["net_profit_accrual"] = data["revenue_accrual"] - data["expense_accrual"]
        data["net_profit_cash"] = data["revenue_cash"] - data["expense_cash"]

    # Итоги за весь период
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


async def get_accounts_receivable(db: AsyncSession) -> dict:
    """
    Дебиторская задолженность: unpaid incomes (status != 'cancelled' and paid_date is null).
    """
    today = date.today()
    q = select(Income).options(selectinload(Income.client)).where(
        Income.status != "cancelled",
        Income.paid_date.is_(None),
    ).order_by(Income.issued_date.asc())
    r = await db.execute(q)
    incomes = r.scalars().all()
    items = []
    ar_total = 0.0
    ar_overdue = 0.0
    for i in incomes:
        amt = float(i.amount_rsd)
        days_out = (today - i.issued_date).days
        items.append({
            "income_id": i.id,
            "invoice_number": i.invoice_number,
            "client_name": i.client_name or (i.client.name if i.client else None),
            "issued_date": i.issued_date.isoformat(),
            "amount": amt,
            "days_outstanding": days_out,
        })
        ar_total += amt
        if days_out > 30:
            ar_overdue += amt
    return {
        "items": items,
        "totals": {"ar_total": ar_total, "ar_overdue": ar_overdue},
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
    opening для первой точки = opening_cash_balance.
    """
    # Получаем opening_cash_balance из enterprise
    r = await db.execute(select(Enterprise).limit(1))
    ent = r.scalar_one_or_none()
    opening_cash_balance = float(ent.opening_cash_balance) if ent and ent.opening_cash_balance is not None else 0.0

    # Финансовый агрегат по cash
    summary = await get_finance_summary(db, date_from, date_to, group_by, "cash", None)
    series = summary.get("series", [])

    result_series = []
    prev_closing = opening_cash_balance
    for i, s in enumerate(series):
        inflow = float(s.get("revenue_cash", 0) or 0)
        outflow = float(s.get("expense_cash", 0) or 0)
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
        "opening_cash_balance": opening_cash_balance,
        "series": result_series,
    }


async def get_finance_by_project(
    db: AsyncSession,
    date_from: date,
    date_to: date,
    mode: Literal["accrual", "cash"] = "accrual",
) -> dict:
    """
    Аналитика по проектам: revenue, expenses, profit, margin_percent.
    Формат: by_project[], unassigned.

    mode=accrual: доходы по Income.issued_date, расходы по Expense.date.
    mode=cash: доходы по Income.paid_date (только paid), расходы по Expense.paid_date (только paid).
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
        # Доходы: issued_date в периоде, status != cancelled
        income_base = and_(
            income_status != "cancelled",
            income_date_col >= date_from,
            income_date_col <= date_to,
        )
        # Расходы: date в периоде, status != reversed
        expense_base = and_(
            expense_status != "reversed",
            expense_date_col >= date_from,
            expense_date_col <= date_to,
        )
    else:
        # cash: доходы — только paid, по paid_date
        income_base = and_(
            income_status == "paid",
            income_paid_col.isnot(None),
            income_paid_col >= date_from,
            income_paid_col <= date_to,
        )
        # cash: расходы — только paid, по paid_date (если нет paid_date — не считаем)
        expense_base = and_(
            expense_status == "paid",
            expense_paid_col.isnot(None),
            expense_paid_col >= date_from,
            expense_paid_col <= date_to,
        )

    # Все проекты (для соответствия списку на фронте при show_archived)
    r = await db.execute(select(Project).order_by(Project.name))
    projects = list(r.scalars().all())
    project_ids = [p.id for p in projects]
    all_ids = project_ids + [None]  # None = без проекта

    by_project = []
    unassigned = {"revenue": 0.0, "expenses": 0.0, "profit": 0.0}

    for pid in all_ids:
        name = "— Без проекта —" if pid is None else next((p.name for p in projects if p.id == pid), f"Project {pid}")

        # Revenue по проекту
        if mode == "accrual":
            inc_cond = and_(income_base, Income.project_id == pid)
            q_rev = select(func.coalesce(func.sum(income_amount), 0)).where(inc_cond)
        else:
            # cash: из cash_transactions (создаётся при mark-paid)
            q_rev = (
                select(func.coalesce(func.sum(CashTransaction.amount), 0))
                .select_from(CashTransaction)
                .join(Income, CashTransaction.reference_id == Income.id)
                .where(
                    and_(
                        CashTransaction.type == "income",
                        CashTransaction.source == "invoice",
                        CashTransaction.date >= date_from,
                        CashTransaction.date <= date_to,
                        Income.project_id == pid,
                    )
                )
            )
        r = await db.execute(q_rev)
        revenue = float(r.scalar() or 0)

        # Expenses по проекту (ключ expenses, не expense/cost)
        exp_cond = and_(expense_base, Expense.project_id == pid)
        q_exp = select(func.coalesce(func.sum(expense_amount), 0)).where(exp_cond)
        r = await db.execute(q_exp)
        expenses = float(r.scalar() or 0)

        profit = revenue - expenses
        margin_percent = round((profit / revenue * 100), 1) if revenue and revenue > 0 else 0.0

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
