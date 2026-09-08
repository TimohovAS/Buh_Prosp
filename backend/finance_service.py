"""Финансовый сервис: метрики accrual vs cash."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Literal, Optional
from sqlalchemy import select, func, and_, or_, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.cash_service import CASH_TRANSFER_SOURCE
from backend.date_utils import coerce_date
from backend.decimal_utils import ZERO_DECIMAL, to_decimal
from backend.models import (
    Income,
    Expense,
    Enterprise,
    Project,
    BankTransaction,
    BankTransactionIncomeAllocation,
    PurchaseReceipt,
)

EFAKTURA_IMPORT_SOURCE = "efaktura_import"
RECEIPT_SOURCE = "receipt"
MATCH_TYPE_LOAN_MOVEMENT = "loan_movement"


def _visible_expense_condition():
    return or_(
        Expense.status != "planned",
        Expense.source.in_([EFAKTURA_IMPORT_SOURCE, RECEIPT_SOURCE]),
    )


def _append_period_amount(periods_data: dict[str, dict[str, Decimal]], period: str, key: str, amount) -> None:
    if period in periods_data:
        periods_data[period][key] += to_decimal(amount or ZERO_DECIMAL)


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
    if date_from > date_to:
        raise ValueError("Start date must not be after end date")
    if group_by == "day" and (date_to - date_from).days >= 366:
        raise ValueError("Daily detail is limited to 366 days")
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
    # accrual: учитываем фактические проводки, включая сторно (status=reversed, amount<0).
    # Обычные planned исключаем, но документы из eFaktura и кассовых чеков учитываем сразу.
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

    periods_data: dict[str, dict[str, Decimal]] = {}
    for pk in _iter_periods(date_from, date_to, group_by):
        periods_data[pk] = {
            "revenue_accrual": ZERO_DECIMAL,
            "revenue_cash": ZERO_DECIMAL,
            "expense_accrual": ZERO_DECIMAL,
            "taxes_accrual": ZERO_DECIMAL,
            "expense_cash": ZERO_DECIMAL,
            "taxes_cash": ZERO_DECIMAL,
            "net_profit_accrual": ZERO_DECIMAL,
            "net_profit_cash": ZERO_DECIMAL,
        }

    # Для группировки нужны подзапросы по каждому периоду или использование strftime
    # SQLite: strftime('%Y-%m', date) для группировки по месяцу
    if group_by == "day":
        grp = func.strftime("%Y-%m-%d", income_date_col)
        grp_exp = func.strftime("%Y-%m-%d", expense_date_col)
        grp_paid_e = func.strftime("%Y-%m-%d", expense_paid_col)
    elif group_by == "month":
        grp = func.strftime("%Y-%m", income_date_col)
        grp_exp = func.strftime("%Y-%m", expense_date_col)
        grp_paid_e = func.strftime("%Y-%m", expense_paid_col)
    else:
        grp = func.strftime("%Y", income_date_col)
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

        tax_rows = await db.execute(
            select(grp_exp.label("period"), func.coalesce(func.sum(expense_amount), 0).label("s"))
            .where(expense_accrual_base, expense_is_tax == True)
            .group_by(grp_exp)
        )
        for row in tax_rows.fetchall():
            _append_period_amount(periods_data, str(row.period), "taxes_accrual", row.s)

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

        q_rc_direct = (
            select(grp_bt.label("period"), func.coalesce(func.sum(bt_amount), 0).label("s"))
            .select_from(BankTransaction)
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
            select(
                grp_bt.label("period"), func.coalesce(func.sum(BankTransactionIncomeAllocation.amount), 0).label("s")
            )
            .select_from(BankTransaction)
            .join(
                BankTransactionIncomeAllocation,
                BankTransactionIncomeAllocation.bank_transaction_id == BankTransaction.id,
            )
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

        q_ec = (
            select(grp_bt.label("period"), func.coalesce(func.sum(func.abs(bt_amount)), 0).label("s"))
            .select_from(BankTransaction)
            .join(Expense, BankTransaction.matched_id == Expense.id)
            .where(
                bt_direction == "out",
                bt_status != "ignored",
                bt_date >= date_from,
                bt_date <= date_to,
                BankTransaction.matched_type == "expense",
                Expense.source != CASH_TRANSFER_SOURCE,
            )
        )
        if category is not None:
            q_ec = q_ec.where(Expense.category == category)
        if is_tax_related is not None:
            q_ec = q_ec.where(Expense.is_tax_related == (1 if is_tax_related else 0))
        q_ec = q_ec.group_by(grp_bt)
        r = await db.execute(q_ec)
        for row in r.fetchall():
            _append_period_amount(periods_data, str(row.period), "expense_cash", row.s)

        q_cash_expense = (
            select(grp_paid_e.label("period"), func.coalesce(func.sum(expense_amount), 0).label("s"))
            .where(expense_cash_base, Expense.source == "cash")
            .group_by(grp_paid_e)
        )
        r = await db.execute(q_cash_expense)
        for row in r.fetchall():
            _append_period_amount(periods_data, str(row.period), "expense_cash", row.s)

        if category is None and (is_tax_related is None or is_tax_related):
            q_ob = (
                select(grp_bt.label("period"), func.coalesce(func.sum(func.abs(bt_amount)), 0).label("s"))
                .where(
                    bt_direction == "out",
                    bt_status != "ignored",
                    bt_date >= date_from,
                    bt_date <= date_to,
                    bt_type == "obligation",
                )
                .group_by(grp_bt)
            )
            r = await db.execute(q_ob)
            for row in r.fetchall():
                _append_period_amount(periods_data, str(row.period), "expense_cash", row.s)

        q_tc1 = (
            select(grp_bt.label("period"), func.coalesce(func.sum(func.abs(bt_amount)), 0).label("s"))
            .select_from(BankTransaction)
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
            _append_period_amount(periods_data, str(row.period), "taxes_cash", row.s)

        q_cash_tax = (
            select(grp_paid_e.label("period"), func.coalesce(func.sum(expense_amount), 0).label("s"))
            .where(expense_tax_base, Expense.source == "cash")
            .group_by(grp_paid_e)
        )
        r = await db.execute(q_cash_tax)
        for row in r.fetchall():
            _append_period_amount(periods_data, str(row.period), "taxes_cash", row.s)

        q_tc2 = (
            select(grp_bt.label("period"), func.coalesce(func.sum(func.abs(bt_amount)), 0).label("s"))
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
            _append_period_amount(periods_data, str(row.period), "taxes_cash", row.s)

    # net profit
    for _period, data in periods_data.items():
        data["net_profit_accrual"] = data["revenue_accrual"] - data["expense_accrual"]
        data["net_profit_cash"] = data["revenue_cash"] - data["expense_cash"]

    # Итоги за весь период
    totals = {
        "revenue_accrual": sum(d["revenue_accrual"] for d in periods_data.values()),
        "revenue_cash": sum(d["revenue_cash"] for d in periods_data.values()),
        "expense_accrual": sum(d["expense_accrual"] for d in periods_data.values()),
        "taxes_accrual": sum(d["taxes_accrual"] for d in periods_data.values()),
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
    """Reconstruct balances using current invoice links and dated payments.

    An undated manual payment is usable for today's snapshot only. A missing
    contractual due date is not replaced with an invented payment deadline.
    """
    cutoff = as_of or date.today()
    if cutoff > date.today():
        raise ValueError("Receivables are available only up to today")
    incomes = list(
        (
            await db.scalars(
                select(Income)
                .options(selectinload(Income.client))
                .where(Income.status != "cancelled", Income.issued_date <= cutoff)
                .order_by(Income.issued_date, Income.id)
            )
        ).all()
    )

    payments: dict[int, dict[str, Decimal]] = {}
    # Keep all-time linked totals to separate manual amounts from bank amounts;
    # use only payments up to the cutoff in the historical balance.
    for income_col, amount_col, is_allocation in (
        (BankTransaction.matched_id, BankTransaction.amount, False),
        (BankTransactionIncomeAllocation.income_id, BankTransactionIncomeAllocation.amount, True),
    ):
        query = select(
            income_col.label("income_id"),
            func.sum(amount_col).label("all_paid"),
            func.sum(case((BankTransaction.date <= cutoff, amount_col), else_=0)).label("paid_to_date"),
        ).select_from(BankTransaction)
        if is_allocation:
            query = query.join(
                BankTransactionIncomeAllocation,
                BankTransactionIncomeAllocation.bank_transaction_id == BankTransaction.id,
            )
        query = (
            query.join(Income, Income.id == income_col)
            .where(
                Income.status != "cancelled",
                Income.issued_date <= cutoff,
                BankTransaction.status == "matched",
                BankTransaction.direction == "in",
                BankTransaction.matched_type == ("income_allocation" if is_allocation else "income"),
            )
            .group_by(income_col)
        )
        for row in (await db.execute(query)).all():
            entry = payments.setdefault(row.income_id, {"all": ZERO_DECIMAL, "dated": ZERO_DECIMAL})
            entry["all"] += to_decimal(row.all_paid)
            entry["dated"] += to_decimal(row.paid_to_date)

    buckets = {
        key: {"key": key, "amount": ZERO_DECIMAL, "count": 0}
        for key in ("not_due", "1_30", "31_60", "61_90", "over_90", "no_due")
    }
    items = []
    missing_payment_dates = 0
    for income in incomes:
        full = to_decimal(income.amount_rsd)
        linked = payments.get(income.id, {"all": ZERO_DECIMAL, "dated": ZERO_DECIMAL})
        recorded = to_decimal(income.paid_amount)
        if income.status == "paid" and recorded <= 0:
            recorded = full
        manual = max(ZERO_DECIMAL, recorded - linked["all"])
        paid_date = coerce_date(income.paid_date)
        missing_date = manual > 0 and paid_date is None
        if missing_date:
            missing_payment_dates += 1
        paid = linked["dated"]
        if manual > 0 and ((paid_date and paid_date <= cutoff) or (missing_date and cutoff == date.today())):
            paid += manual
        paid = min(full, max(ZERO_DECIMAL, paid))
        remaining = full - paid
        if remaining <= 0:
            continue
        due_date = coerce_date(income.due_date)
        overdue_days = max(0, (cutoff - due_date).days) if due_date else None
        bucket = (
            "no_due"
            if due_date is None
            else "not_due"
            if overdue_days == 0
            else (
                "1_30"
                if overdue_days <= 30
                else "31_60"
                if overdue_days <= 60
                else "61_90"
                if overdue_days <= 90
                else "over_90"
            )
        )
        buckets[bucket]["amount"] += remaining
        buckets[bucket]["count"] += 1
        items.append(
            {
                "income_id": income.id,
                "client_id": income.client_id,
                "invoice_number": income.invoice_number,
                "client_name": income.client_name or (income.client.name if income.client else None),
                "issued_date": income.issued_date.isoformat(),
                "due_date": due_date.isoformat() if due_date else None,
                "amount": remaining,
                "amount_full": full,
                "amount_paid": paid,
                "status": "partial" if paid > 0 else "issued",
                "days_outstanding": (cutoff - income.issued_date).days,
                "days_overdue": overdue_days,
                "aging_bucket": bucket,
                "payment_date_missing": missing_date,
            }
        )
    overdue = [item for item in items if (item["days_overdue"] or 0) > 0]
    return {
        "as_of": cutoff.isoformat(),
        "items": items,
        "aging": list(buckets.values()),
        "missing_payment_dates": missing_payment_dates,
        "totals": {
            "ar_total": sum((item["amount"] for item in items), ZERO_DECIMAL),
            "ar_overdue": sum((item["amount"] for item in overdue), ZERO_DECIMAL),
            "ar_not_due": buckets["not_due"]["amount"],
            "ar_without_due_date": buckets["no_due"]["amount"],
            "invoice_count": len(items),
            "overdue_count": len(overdue),
            "client_count": len({item["client_id"] or (item["client_name"] or "").casefold() for item in items}),
            "oldest_overdue_days": max((item["days_overdue"] for item in overdue), default=0),
        },
    }


async def _cashflow_movements(
    db: AsyncSession,
    date_from: date,
    date_to: date,
    group_by: Literal["day", "month", "year"],
) -> list[dict]:
    """One set of recognition rules for both historical and selected movements."""
    bt_date = BankTransaction.date
    bt_amount = BankTransaction.amount
    bt_direction = BankTransaction.direction
    bt_status = BankTransaction.status

    summary = await get_finance_summary(db, date_from, date_to, group_by, "cash", None)
    series = summary.get("series", [])

    if group_by == "day":
        grp_bt = func.strftime("%Y-%m-%d", bt_date)
    elif group_by == "month":
        grp_bt = func.strftime("%Y-%m", bt_date)
    else:
        grp_bt = func.strftime("%Y", bt_date)

    financing_by_period = {
        str(item["period"]): {
            "financing_inflow": ZERO_DECIMAL,
            "financing_outflow": ZERO_DECIMAL,
        }
        for item in series
    }
    for direction, key in (("in", "financing_inflow"), ("out", "financing_outflow")):
        amount_expr = bt_amount if direction == "in" else func.abs(bt_amount)
        financing_result = await db.execute(
            select(grp_bt.label("period"), func.coalesce(func.sum(amount_expr), 0).label("amount"))
            .where(
                bt_direction == direction,
                bt_status != "ignored",
                BankTransaction.matched_type == MATCH_TYPE_LOAN_MOVEMENT,
                bt_date >= date_from,
                bt_date <= date_to,
            )
            .group_by(grp_bt)
        )
        for row in financing_result.fetchall():
            period_values = financing_by_period.get(str(row.period))
            if period_values is not None:
                period_values[key] = to_decimal(row.amount or ZERO_DECIMAL)

    result_series = []
    for s in series:
        inflow = to_decimal(s.get("revenue_cash", ZERO_DECIMAL) or ZERO_DECIMAL)
        outflow = to_decimal(s.get("expense_cash", ZERO_DECIMAL) or ZERO_DECIMAL)
        financing = financing_by_period.get(str(s["period"]), {})
        financing_inflow = to_decimal(financing.get("financing_inflow", ZERO_DECIMAL))
        financing_outflow = to_decimal(financing.get("financing_outflow", ZERO_DECIMAL))
        result_series.append(
            {
                "period": s["period"],
                "inflow": inflow,
                "outflow": outflow,
                "financing_inflow": financing_inflow,
                "financing_outflow": financing_outflow,
                "operating_net": inflow - outflow,
                "financing_net": financing_inflow - financing_outflow,
                "net": inflow - outflow + financing_inflow - financing_outflow,
            }
        )

    return result_series


async def get_cashflow(
    db: AsyncSession,
    date_from: date,
    date_to: date,
    group_by: Literal["day", "month", "year"],
) -> dict:
    """Calculated balance from recognized payments, cash expenses and loan principal.

    The configured balance is at the START of its date. Internal bank-to-cash
    transfers and unrecognized bank movements are excluded throughout the timeline.
    This is not a reconciliation of actual bank and cash register balances.
    """
    today = date.today()
    if date_from > date_to:
        raise ValueError("Start date must not be after end date")
    if date_from > today:
        raise ValueError("Cash flow is available only for dates up to today")
    requested_to = date_to
    date_to = min(date_to, today)
    if group_by == "day" and (date_to - date_from).days >= 366:
        raise ValueError("Daily detail is limited to 366 days; use month or year")

    ent = await db.scalar(select(Enterprise).limit(1))
    reference_balance = to_decimal(ent.opening_cash_balance) if ent else ZERO_DECIMAL
    reference_date = ent.opening_cash_date if ent else None
    if reference_date is None:
        first_bank = await db.scalar(select(func.min(BankTransaction.date)))
        first_cash = await db.scalar(select(func.min(Expense.paid_date)).where(Expense.source == "cash"))
        reference_date = min(d for d in (first_bank, first_cash, date_from) if d is not None)

    opening = reference_balance
    if reference_date != date_from:
        history = await _cashflow_movements(
            db, min(reference_date, date_from), max(reference_date, date_from) - timedelta(days=1), "year"
        )
        history_net = sum((item["net"] for item in history), ZERO_DECIMAL)
        opening += history_net if reference_date < date_from else -history_net

    series = await _cashflow_movements(db, date_from, date_to, group_by)
    closing = opening
    for item in series:
        item["opening"] = closing
        closing += item["net"]
        item["closing"] = closing

    totals = {
        key: sum((item[key] for item in series), ZERO_DECIMAL)
        for key in (
            "inflow",
            "outflow",
            "financing_inflow",
            "financing_outflow",
            "operating_net",
            "financing_net",
            "net",
        )
    }
    unmatched_count = await db.scalar(
        select(func.count(BankTransaction.id)).where(
            BankTransaction.status == "unmatched",
            BankTransaction.date >= min(reference_date, date_from),
            BankTransaction.date <= max(date_to, reference_date - timedelta(days=1)),
        )
    )
    return {
        "range": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "requested_range": {"from": date_from.isoformat(), "to": requested_to.isoformat()},
        "as_of": today.isoformat(),
        "group_by": group_by,
        "opening_cash_balance": opening,
        "closing_cash_balance": closing,
        "totals": totals,
        "balance_basis": "recognized_movements",
        "opening_reference": {
            "date": ent.opening_cash_date.isoformat() if ent and ent.opening_cash_date else None,
            "amount": reference_balance,
        },
        "unmatched_bank_count": unmatched_count or 0,
        "series": series,
    }


async def get_finance_by_project(
    db: AsyncSession,
    date_from: date,
    date_to: date,
    mode: Literal["accrual", "cash"] = "accrual",
    include_inactive: bool = False,
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
        # Расходы: date в периоде, включая сторно (reversed). Обычные planned
        # исключаем, но документы из eFaktura и кассовых чеков учитываем сразу.
        expense_base = and_(
            _visible_expense_condition(),
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

    project_query = select(Project).order_by(Project.name)
    if not include_inactive:
        project_query = project_query.where(Project.status == "active")
    r = await db.execute(project_query)
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
                .join(
                    BankTransactionIncomeAllocation,
                    BankTransactionIncomeAllocation.bank_transaction_id == BankTransaction.id,
                )
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
                select(func.coalesce(func.sum(func.abs(BankTransaction.amount)), 0))
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

            q_cash_exp = select(func.coalesce(func.sum(expense_amount), 0)).where(
                and_(
                    expense_base,
                    Expense.source == "cash",
                    Expense.project_id == pid,
                )
            )
            r = await db.execute(q_cash_exp)
            expenses += to_decimal(r.scalar() or ZERO_DECIMAL)

        profit = revenue - expenses
        margin_percent = (
            float(((profit / revenue) * Decimal("100")).quantize(Decimal("0.1")))
            if revenue and revenue > ZERO_DECIMAL
            else 0.0
        )

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
        )
        .where(and_(*income_conditions))
        .group_by(Income.project_id)
    )

    for project_id, min_date, max_date in income_rows.fetchall():
        if project_id is None:
            continue
        entry = bounds.setdefault(project_id, {"first_movement_date": None, "last_movement_date": None})
        if min_date is not None and (entry["first_movement_date"] is None or min_date < entry["first_movement_date"]):
            entry["first_movement_date"] = min_date
        if max_date is not None and (entry["last_movement_date"] is None or max_date > entry["last_movement_date"]):
            entry["last_movement_date"] = max_date

    # Bounds are about WHEN documents exist on a project, not about their
    # cash-flow visibility, so we deliberately skip `_visible_expense_condition()`
    # here. Planned expenses (receipts waiting for bank match, incoming
    # invoices waiting for settlement) ARE real events and must extend
    # the project's date window — otherwise "all time" period in the
    # Projects page truncates and downstream filters (e.g. purchases-by-
    # receipts modal) silently hide rows.
    expense_conditions = [
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
        )
        .where(and_(*expense_conditions))
        .group_by(Expense.project_id)
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
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
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
        for (
            income_id,
            issued_date,
            invoice_number,
            client_name,
            description,
            amount_rsd,
            status,
        ) in income_rows.fetchall():
            items.append(
                {
                    "row_key": f"income-{income_id}",
                    "source_id": income_id,
                    "date": issued_date,
                    "direction": "in",
                    "movement_type": "income",
                    "source_kind": "income",
                    "document_number": invoice_number,
                    "counterparty_name": client_name,
                    "description": description,
                    "amount": to_decimal(amount_rsd or ZERO_DECIMAL),
                    "status": status,
                }
            )

        expense_rows = await db.execute(
            select(
                Expense.id,
                PurchaseReceipt.id,
                Expense.date,
                Expense.bank_reference,
                Expense.description,
                Expense.amount,
                Expense.status,
            )
            .outerjoin(PurchaseReceipt, PurchaseReceipt.expense_id == Expense.id)
            .where(
                and_(
                    _visible_expense_condition(),
                    Expense.project_id == project_id,
                    Expense.source != CASH_TRANSFER_SOURCE,
                    Expense.date >= date_from,
                    Expense.date <= date_to,
                )
            )
        )
        for (
            expense_id,
            receipt_id,
            expense_date,
            bank_reference,
            description,
            amount,
            status,
        ) in expense_rows.fetchall():
            items.append(
                {
                    "row_key": f"expense-{expense_id}",
                    "source_id": expense_id,
                    "receipt_id": receipt_id,
                    "date": expense_date,
                    "direction": "out",
                    "movement_type": "expense",
                    "source_kind": "expense",
                    "document_number": bank_reference,
                    "counterparty_name": None,
                    "description": description,
                    "amount": abs(to_decimal(amount or ZERO_DECIMAL)),
                    "status": status,
                }
            )
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
        for (
            tx_id,
            tx_date,
            invoice_number,
            counterparty_name,
            purpose,
            description,
            amount,
            status,
        ) in direct_income_rows.fetchall():
            items.append(
                {
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
                }
            )

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
            .join(
                BankTransactionIncomeAllocation,
                BankTransactionIncomeAllocation.bank_transaction_id == BankTransaction.id,
            )
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
        for (
            _tx_id,
            allocation_id,
            tx_date,
            invoice_number,
            counterparty_name,
            purpose,
            description,
            amount,
            status,
        ) in allocated_income_rows.fetchall():
            items.append(
                {
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
                }
            )

        expense_cash_rows = await db.execute(
            select(
                BankTransaction.id,
                Expense.id,
                PurchaseReceipt.id,
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
            .outerjoin(PurchaseReceipt, PurchaseReceipt.expense_id == Expense.id)
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
        for (
            tx_id,
            expense_id,
            receipt_id,
            tx_date,
            bank_reference,
            counterparty_name,
            purpose,
            description,
            amount,
            status,
        ) in expense_cash_rows.fetchall():
            items.append(
                {
                    "row_key": f"bank-expense-{tx_id}",
                    "source_id": expense_id,
                    "receipt_id": receipt_id,
                    "date": tx_date,
                    "direction": "out",
                    "movement_type": "expense",
                    "source_kind": "bank",
                    "document_number": bank_reference,
                    "counterparty_name": counterparty_name,
                    "description": purpose or description,
                    "amount": abs(to_decimal(amount or ZERO_DECIMAL)),
                    "status": status,
                }
            )

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
    """Accrual P&L shares recognition rules with the overview; taxes are a subset."""
    if not 1900 <= year <= date.today().year:
        raise ValueError("Select a year between 1900 and the current year")
    date_from = date(year, 1, 1)
    date_to = min(date(year, 12, 31), date.today())
    summary = await get_finance_summary(db, date_from, date_to, "month", "accrual")
    items = [
        {
            "month": int(row["period"][-2:]),
            "revenue": row["revenue_accrual"],
            "expenses": row["expense_accrual"] - row["taxes_accrual"],
            "taxes": row["taxes_accrual"],
            "profit": row["net_profit_accrual"],
        }
        for row in summary["series"]
    ]
    return {
        "year": year,
        "date_from": date_from,
        "date_to": date_to,
        "items": items,
        "totals": {
            key: sum((item[key] for item in items), ZERO_DECIMAL) for key in ("revenue", "expenses", "taxes", "profit")
        },
    }


async def get_finance_pnl_years(db: AsyncSession) -> list[int]:
    income_rows = await db.execute(
        select(func.distinct(func.strftime("%Y", Income.issued_date)).label("year")).where(
            Income.status != "cancelled",
            Income.issued_date.isnot(None),
        )
    )
    expense_rows = await db.execute(
        select(func.distinct(func.strftime("%Y", Expense.date)).label("year")).where(
            _visible_expense_condition(),
            Expense.source != CASH_TRANSFER_SOURCE,
            Expense.date.isnot(None),
        )
    )

    years = {int(row.year) for row in income_rows.fetchall() + expense_rows.fetchall() if row.year}
    return sorted(years, reverse=True)
