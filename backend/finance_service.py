"""Финансовый сервис: метрики accrual vs cash."""
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Literal, Optional
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.cash_service import CASH_TRANSFER_SOURCE
from backend.decimal_utils import MONEY_PLACES, ZERO_DECIMAL, to_decimal
from backend.models import Income, Expense, Enterprise, Project, BankTransaction


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

    # Базовые условия для expenses:
    # accrual: учитываем фактические проводки, включая сторно (status=reversed, amount<0),
    # но исключаем planned.
    expense_accrual_base = and_(
        expense_status != "planned",
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

    # Cash: paid_date in period, учитываем paid и reversed (сторно влияет на cash-flow).
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
            "revenue_accrual": ZERO_DECIMAL,
            "revenue_cash": ZERO_DECIMAL,
            "expense_accrual": ZERO_DECIMAL,
            "expense_cash": ZERO_DECIMAL,
            "taxes_cash": ZERO_DECIMAL,
            "net_profit_accrual": ZERO_DECIMAL,
            "net_profit_cash": ZERO_DECIMAL,
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
                periods_data[p]["revenue_accrual"] = to_decimal(row.s)

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
                periods_data[p]["expense_accrual"] = to_decimal(row.s)

    if need_cash:
        bt_date = BankTransaction.date
        bt_amount = BankTransaction.amount
        bt_direction = BankTransaction.direction
        bt_status = BankTransaction.status
        bt_type = BankTransaction.matched_type

        # Группировка
        if group_by == "day":
            grp_bt = func.strftime("%Y-%m-%d", bt_date)
        elif group_by == "month":
            grp_bt = func.strftime("%Y-%m", bt_date)
        else:
            grp_bt = func.strftime("%Y", bt_date)

        # Inflow - все поступления (direction="in", status != "ignored")
        q_rc = (
            select(grp_bt.label("period"), func.coalesce(func.sum(bt_amount), 0).label("s"))
            .where(
                bt_direction == "in",
                bt_status != "ignored",
                bt_date >= date_from,
                bt_date <= date_to,
            )
        )
        # Если есть фильтры по клиенту, контракту, проекту, нужно заджоинить Income
        # Так как BankTransaction должен матчиться с Income для этих данных
        if client_id is not None or contract_id is not None or project_id is not None:
            q_rc = q_rc.join(Income, BankTransaction.matched_id == Income.id).where(
                BankTransaction.matched_type == "income"
            )
            if client_id is not None:
                q_rc = q_rc.where(Income.client_id == client_id)
            if contract_id is not None:
                q_rc = q_rc.where(Income.contract_id == contract_id)
            if project_id is not None:
                q_rc = q_rc.where(Income.project_id == project_id)

        q_rc = q_rc.group_by(grp_bt)
        r = await db.execute(q_rc)
        for row in r.fetchall():
            p = str(row.period)
            if p in periods_data:
                periods_data[p]["revenue_cash"] = to_decimal(row.s)

        # Outflow (expenses + obligations)
        # Если нет фильтров tax / category, просто берем все out != ignored
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
            # Для фильтров нужно подтянуть Expense
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
                
        # Если не было фильтров, добавим и obligation outflow
        if category is None and is_tax_related is None:
            pass # obligations уже посчитаны в общем bt_direction=="out"
        elif is_tax_related:
             # Если искали налоги, obligation (зарплатные налоги) туда тоже плюсуем
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

        # taxes_cash (is_tax_related == True или obligations)
        # Суммируем Expense is_tax=True и все MonthlyObligation
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


async def get_accounts_receivable(db: AsyncSession, as_of: Optional[date] = None) -> dict:
    """
    Дебиторская задолженность: unpaid и partial incomes.
    Для partial показывает остаток (amount_rsd - paid_amount).
    """
    today = as_of or date.today()
    q = select(Income).options(selectinload(Income.client)).where(
        Income.status.in_(["issued", "partial"]),
        Income.issued_date <= today,
    ).order_by(Income.issued_date.asc())
    r = await db.execute(q)
    incomes = r.scalars().all()
    items = []
    ar_total = 0.0
    ar_overdue = 0.0
    for i in incomes:
        # Для частичной оплаты показываем остаток
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
            "amount": remaining,          # остаток к оплате
            "amount_full": to_decimal(i.amount_rsd),
            "amount_paid": to_decimal(i.paid_amount or ZERO_DECIMAL),
            "status": i.status,
            "days_outstanding": days_out,
            "days_overdue": days_overdue,
        })
        ar_total += remaining
        if days_overdue > 0:
            ar_overdue += remaining
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
        # Расходы: date в периоде, включая сторно (reversed), но без planned
        expense_base = and_(
            expense_status != "planned",
            Expense.source != CASH_TRANSFER_SOURCE,
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
        # cash: расходы — paid и reversed, по paid_date (если нет paid_date — не считаем)
        expense_base = and_(
            expense_status.in_(["paid", "reversed"]),
            Expense.source != CASH_TRANSFER_SOURCE,
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
            r = await db.execute(q_rev)
            revenue = to_decimal(r.scalar() or ZERO_DECIMAL)
            
            exp_cond = and_(expense_base, Expense.project_id == pid)
            q_exp = select(func.coalesce(func.sum(expense_amount), 0)).where(exp_cond)
            r = await db.execute(q_exp)
            expenses = to_decimal(r.scalar() or ZERO_DECIMAL)
        else:
            # cash: Revenue - sum of BankTransaction in, matched to income with this project_id 
            q_rev = (
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
            r = await db.execute(q_rev)
            revenue = to_decimal(r.scalar() or ZERO_DECIMAL)

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



