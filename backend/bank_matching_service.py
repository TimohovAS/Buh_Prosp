from datetime import date, timedelta
import re

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.cash_service import is_cash_transfer_expense, revert_cash_transfer
from backend.date_utils import coerce_date, days_between
from backend.db_utils import (
    get_contract_or_404,
    get_project_or_404,
    get_unassigned_project_id,
)
from backend.decimal_utils import ZERO_DECIMAL, decimal_sum, money_abs, money_eq, to_decimal
from backend.obligation_payment_service import mark_obligation_paid, reset_obligation_payment
from backend.models import (
    BankTransaction,
    BankTransactionIncomeAllocation,
    CashEntry,
    Contract,
    Expense,
    Income,
    IncomingInvoice,
    IncomingInvoiceSettlement,
    MonthlyObligation,
    PlannedExpensePayment,
    Project,
    PurchaseReceipt,
)
from backend.receipt_service import sync_receipt_for_expense_match, sync_receipt_for_expense_unmatch
from backend.services import _extract_invoice_candidates, _normalize_invoice_number
from backend.state_machine import mark_expense_paid, reconcile_income_payment_state, reconcile_incoming_invoice_status, reopen_expense_for_unmatch

MATCH_TYPE_INCOME_ALLOCATION = "income_allocation"
MATCH_TYPE_OWNER_FUNDS = "owner_funds"


def _safe_paid_amount(income: Income):
    return to_decimal(getattr(income, "paid_amount", None) or ZERO_DECIMAL)


def _matches_counterparty_name(tx: BankTransaction, income: Income) -> bool:
    counterparty_norm = (tx.counterparty_name or "").lower().strip()
    if not counterparty_norm:
        return False

    raw_name = income.client_name or (income.client.name if income.client else "")
    client_norm = raw_name.lower().strip()
    if not client_norm:
        return False

    cp_words = counterparty_norm.split()[:4]
    cl_words = client_norm.split()[:4]
    common = sum(
        1
        for word in cp_words
        if any(word == client_word or word in client_word or client_word in word for client_word in cl_words)
    )
    return common >= 2 or client_norm in counterparty_norm or counterparty_norm in client_norm


def _matches_receipt_seller(tx: BankTransaction, receipt: PurchaseReceipt) -> bool:
    counterparty_norm = " ".join(filter(None, [tx.counterparty_name, tx.purpose, tx.bank_reference])).lower().strip()
    seller_norm = (getattr(receipt, "seller_name", None) or "").lower().strip()
    if not counterparty_norm or not seller_norm:
        return False
    seller_words = [word for word in seller_norm.split()[:5] if len(word) >= 3]
    common = sum(1 for word in seller_words if word in counterparty_norm)
    return common >= 2 or seller_norm in counterparty_norm or counterparty_norm in seller_norm


async def _suggest_receipt_expense_matches(db: AsyncSession, tx: BankTransaction) -> list[tuple[tuple[int, float, int], dict]]:
    window_start = tx.date - timedelta(days=31)
    window_end = tx.date + timedelta(days=7)
    result = await db.execute(
        select(Expense, PurchaseReceipt)
        .join(PurchaseReceipt, PurchaseReceipt.expense_id == Expense.id)
        .where(
            Expense.source == "receipt",
            Expense.status == "planned",
            Expense.reversal_of_id.is_(None),
            Expense.date >= window_start,
            Expense.date <= window_end,
        )
        .order_by(Expense.date.desc(), Expense.id.desc())
    )

    suggestions: list[tuple[tuple[int, float, int], dict]] = []
    for expense, receipt in result.fetchall():
        if not money_eq(money_abs(expense.amount or ZERO_DECIMAL), money_abs(tx.amount or ZERO_DECIMAL)):
            continue
        receipt_date = coerce_date(getattr(receipt, "receipt_datetime", None)) or coerce_date(expense.date)
        date_diff = days_between(tx.date, receipt_date, absolute=True)
        counterparty_match = _matches_receipt_seller(tx, receipt)
        section = "all"
        score_value = None
        if counterparty_match:
            section = "suggested"
            score_value = max(75, 98 - min(date_diff, 20))
        elif date_diff <= 3:
            section = "suggested"
            score_value = max(70, 90 - date_diff)

        suggestions.append(
            (
                (
                    0 if section == "suggested" else 1,
                    float(date_diff),
                    int(expense.id),
                ),
                {
                    "id": expense.id,
                    "type": "expense",
                    "invoice_number": receipt.invoice_number,
                    "client_name": receipt.seller_name,
                    "description": (expense.description or "")[:120],
                    "amount": to_decimal(expense.amount or ZERO_DECIMAL),
                    "amount_full": None,
                    "amount_paid": None,
                    "date": str(expense.date),
                    "status": expense.status,
                    "score": score_value,
                    "section": section,
                },
            )
        )
    return suggestions


async def _clear_contract_if_project_mismatch(db: AsyncSession, expense: Expense, project_id: int | None) -> None:
    if not expense.contract_id or project_id is None:
        return
    result = await db.execute(select(Contract).where(Contract.id == expense.contract_id))
    contract = result.scalar_one_or_none()
    if contract and contract.project_id != project_id:
        expense.contract_id = None


async def _sync_income_project(db: AsyncSession, income: Income, project_id: int | None) -> None:
    income.project_id = project_id
    if income.contract_id is None or project_id is None:
        return

    contract = await get_contract_or_404(db, income.contract_id, exc_cls=ValueError)
    if contract.project_id is None:
        await get_project_or_404(db, project_id, exc_cls=ValueError)
        contract.project_id = project_id
        await db.flush()
        return

    if contract.project_id != project_id:
        income.contract_id = None
        income.contract_payment_type = None


def _normalize_digits(value: str | None) -> str:
    return re.sub(r"\D+", "", value or "")


def _build_obligation_description(obligation: MonthlyObligation) -> str:
    payment_type = getattr(obligation, "payment_type", None)
    payment_type_name = getattr(payment_type, "name_sr", None) or "Плаћање"
    return f"{payment_type_name} {obligation.month:02d}/{obligation.year}"


def _obligation_terms(obligation: MonthlyObligation) -> list[str]:
    payment_type = getattr(obligation, "payment_type", None)
    decision = getattr(obligation, "decision", None)
    values = [
        getattr(payment_type, "name_sr", None),
        getattr(payment_type, "name_ru", None),
        getattr(payment_type, "code", None),
        getattr(decision, "payment_purpose", None),
    ]
    return [str(value).lower() for value in values if value]


async def _suggest_outgoing_matches(db: AsyncSession, tx: BankTransaction) -> list[dict]:
    scored: list[tuple[tuple[int, float, int], dict]] = []
    scored.extend(await _suggest_receipt_expense_matches(db, tx))

    query = (
        select(MonthlyObligation)
        .options(
            selectinload(MonthlyObligation.payment_type),
            selectinload(MonthlyObligation.decision),
        )
        .where(MonthlyObligation.status.in_(["unpaid", "overdue"]))
        .order_by(MonthlyObligation.deadline.asc(), MonthlyObligation.id.asc())
    )
    response = await db.execute(query)
    obligations = list(response.scalars().all())

    tx_text = " ".join(filter(None, [tx.counterparty_name, tx.purpose, tx.bank_reference])).lower()
    tx_digits = _normalize_digits(tx_text)

    for obligation in obligations:
        decision = getattr(obligation, "decision", None)
        amount_diff = money_abs(money_abs(obligation.amount or ZERO_DECIMAL) - money_abs(tx.amount or ZERO_DECIMAL))
        deadline_diff = days_between(tx.date, obligation.deadline, absolute=True)
        reference_match = False
        for candidate in (
            getattr(decision, "poziv_na_broj", None),
            getattr(decision, "poziv_na_broj_next", None),
        ):
            digits = _normalize_digits(candidate)
            if digits and digits in tx_digits:
                reference_match = True
                break
        account_digits = _normalize_digits(getattr(decision, "recipient_account", None))
        account_match = bool(account_digits and account_digits in tx_digits)
        term_match = any(term and term in tx_text for term in _obligation_terms(obligation))
        exact_amount_match = amount_diff <= 0.5

        section = "all"
        score_value = None
        if exact_amount_match and reference_match:
            section = "suggested"
            score_value = 100
        elif exact_amount_match and account_match:
            section = "suggested"
            score_value = 96
        elif exact_amount_match and term_match:
            section = "suggested"
            score_value = max(70, 88 - min(deadline_diff, 18))
        elif reference_match or account_match:
            score_value = 60

        scored.append((
            (
                0 if section == "suggested" else 1,
                float(amount_diff),
                int(obligation.id),
            ),
            {
                "id": obligation.id,
                "type": "obligation",
                "invoice_number": None,
                "client_name": getattr(decision, "recipient_account", None),
                "description": _build_obligation_description(obligation),
                "amount": to_decimal(obligation.amount or ZERO_DECIMAL),
                "amount_full": None,
                "amount_paid": None,
                "date": str(obligation.deadline),
                "status": obligation.status,
                "score": score_value,
                "section": section,
            },
        ))

    scored.sort(key=lambda item: item[0])
    return [item for _, item in scored]


def _merge_income_payment_summary(
    summary: dict[int, dict],
    *,
    income_id: int | None,
    tx_id: int,
    tx_date: date | None,
    amount,
    bank_reference: str | None,
) -> None:
    if income_id is None:
        return
    entry = summary.setdefault(
        int(income_id),
        {
            "paid_amount": ZERO_DECIMAL,
            "latest_date": None,
            "latest_tx_id": -1,
            "bank_reference": None,
        },
    )
    entry["paid_amount"] = to_decimal(entry["paid_amount"]) + to_decimal(amount or ZERO_DECIMAL)
    if tx_date is None:
        return
    latest_date = entry.get("latest_date")
    latest_tx_id = int(entry.get("latest_tx_id") or -1)
    if latest_date is None or tx_date > latest_date or (tx_date == latest_date and tx_id > latest_tx_id):
        entry["latest_date"] = tx_date
        entry["latest_tx_id"] = tx_id
        entry["bank_reference"] = bank_reference


async def _build_income_payment_summary_map(
    db: AsyncSession,
    income_ids: list[int] | set[int] | None = None,
    *,
    exclude_tx_id: int | None = None,
) -> dict[int, dict]:
    restrict_income_ids = income_ids is not None
    normalized_income_ids = {int(value) for value in (income_ids or []) if value is not None}
    if restrict_income_ids and not normalized_income_ids:
        return {}

    summary: dict[int, dict] = {}

    direct_query = (
        select(
            BankTransaction.id,
            BankTransaction.matched_id,
            BankTransaction.date,
            BankTransaction.amount,
            BankTransaction.bank_reference,
        )
        .where(
            BankTransaction.status == "matched",
            BankTransaction.matched_type == "income",
        )
    )
    if normalized_income_ids:
        direct_query = direct_query.where(BankTransaction.matched_id.in_(normalized_income_ids))
    if exclude_tx_id is not None:
        direct_query = direct_query.where(BankTransaction.id != exclude_tx_id)
    direct_result = await db.execute(direct_query)
    for tx_id, income_id, tx_date, amount, bank_reference in direct_result.fetchall():
        _merge_income_payment_summary(
            summary,
            income_id=income_id,
            tx_id=int(tx_id),
            tx_date=tx_date,
            amount=amount,
            bank_reference=bank_reference,
        )

    allocation_query = (
        select(
            BankTransactionIncomeAllocation.income_id,
            BankTransaction.id,
            BankTransaction.date,
            BankTransactionIncomeAllocation.amount,
            BankTransaction.bank_reference,
        )
        .join(BankTransaction, BankTransaction.id == BankTransactionIncomeAllocation.bank_transaction_id)
        .where(
            BankTransaction.status == "matched",
            BankTransaction.matched_type == MATCH_TYPE_INCOME_ALLOCATION,
        )
    )
    if normalized_income_ids:
        allocation_query = allocation_query.where(BankTransactionIncomeAllocation.income_id.in_(normalized_income_ids))
    if exclude_tx_id is not None:
        allocation_query = allocation_query.where(BankTransaction.id != exclude_tx_id)
    allocation_result = await db.execute(allocation_query)
    for income_id, tx_id, tx_date, amount, bank_reference in allocation_result.fetchall():
        _merge_income_payment_summary(
            summary,
            income_id=income_id,
            tx_id=int(tx_id),
            tx_date=tx_date,
            amount=amount,
            bank_reference=bank_reference,
        )

    return summary


def _get_income_available_amount(income: Income, summary_map: dict[int, dict]):
    total = to_decimal(income.amount_rsd or ZERO_DECIMAL)
    paid = to_decimal(summary_map.get(int(income.id), {}).get("paid_amount", ZERO_DECIMAL))
    remaining = total - paid
    return remaining if remaining > ZERO_DECIMAL else ZERO_DECIMAL


async def reconcile_income_payment_links(
    db: AsyncSession,
    income_ids: list[int] | set[int],
) -> None:
    normalized_income_ids = {int(value) for value in income_ids if value is not None}
    if not normalized_income_ids:
        return

    income_result = await db.execute(select(Income).where(Income.id.in_(normalized_income_ids)))
    incomes = list(income_result.scalars().all())
    if not incomes:
        return

    summary_map = await _build_income_payment_summary_map(db, normalized_income_ids)
    for income in incomes:
        if income.status == "cancelled":
            continue
        linked = summary_map.get(int(income.id), {})
        linked_paid = to_decimal(linked.get("paid_amount", ZERO_DECIMAL))
        reconcile_income_payment_state(
            income,
            total_amount=to_decimal(income.amount_rsd or ZERO_DECIMAL),
            paid_amount=linked_paid,
            paid_date=linked.get("latest_date"),
        )
        income.bank_reference = linked.get("bank_reference") if linked_paid > ZERO_DECIMAL else None

    await db.flush()


async def get_income_linked_payment_entries(db: AsyncSession, income_id: int) -> list[dict]:
    direct_query = (
        select(BankTransaction)
        .where(
            BankTransaction.status == "matched",
            BankTransaction.matched_type == "income",
            BankTransaction.matched_id == income_id,
        )
        .order_by(BankTransaction.date.desc(), BankTransaction.id.desc())
    )
    direct_result = await db.execute(direct_query)
    direct_transactions = list(direct_result.scalars().all())

    allocation_query = (
        select(BankTransactionIncomeAllocation, BankTransaction)
        .join(BankTransaction, BankTransaction.id == BankTransactionIncomeAllocation.bank_transaction_id)
        .where(
            BankTransaction.status == "matched",
            BankTransaction.matched_type == MATCH_TYPE_INCOME_ALLOCATION,
            BankTransactionIncomeAllocation.income_id == income_id,
        )
        .order_by(BankTransaction.date.desc(), BankTransaction.id.desc(), BankTransactionIncomeAllocation.id.desc())
    )
    allocation_result = await db.execute(allocation_query)
    allocation_rows = list(allocation_result.fetchall())

    allocation_count_map: dict[int, int] = {}
    if allocation_rows:
        tx_ids = [int(tx.id) for _, tx in allocation_rows]
        stats = await get_bank_transaction_allocation_stats(db, tx_ids)
        allocation_count_map = {
            tx_id: int(info.get("allocation_count", 0))
            for tx_id, info in stats.items()
        }

    entries: list[dict] = []
    for tx in direct_transactions:
        entries.append(
            {
                "id": tx.id,
                "date": tx.date,
                "amount": to_decimal(tx.amount or ZERO_DECIMAL),
                "transaction_amount": to_decimal(tx.amount or ZERO_DECIMAL),
                "currency": tx.currency or "RSD",
                "counterparty_name": tx.counterparty_name,
                "purpose": tx.purpose,
                "bank_reference": tx.bank_reference,
                "project_id": tx.project_id,
                "link_kind": "direct",
                "allocation_count": 1,
                "can_unlink": True,
            }
        )

    for allocation, tx in allocation_rows:
        allocation_count = int(allocation_count_map.get(int(tx.id), 1) or 1)
        entries.append(
            {
                "id": tx.id,
                "date": tx.date,
                "amount": to_decimal(allocation.amount or ZERO_DECIMAL),
                "transaction_amount": to_decimal(tx.amount or ZERO_DECIMAL),
                "currency": tx.currency or "RSD",
                "counterparty_name": tx.counterparty_name,
                "purpose": tx.purpose,
                "bank_reference": tx.bank_reference,
                "project_id": tx.project_id,
                "link_kind": "allocation",
                "allocation_count": allocation_count,
                "can_unlink": allocation_count <= 1,
            }
        )

    entries.sort(key=lambda item: (item["date"], item["id"]), reverse=True)
    return entries


async def get_bank_transaction_allocation_stats(
    db: AsyncSession,
    tx_ids: list[int] | set[int],
) -> dict[int, dict]:
    normalized_tx_ids = {int(value) for value in tx_ids if value is not None}
    if not normalized_tx_ids:
        return {}

    stats_query = (
        select(
            BankTransactionIncomeAllocation.bank_transaction_id,
            func.count(BankTransactionIncomeAllocation.id),
            func.coalesce(func.sum(BankTransactionIncomeAllocation.amount), 0),
        )
        .where(BankTransactionIncomeAllocation.bank_transaction_id.in_(normalized_tx_ids))
        .group_by(BankTransactionIncomeAllocation.bank_transaction_id)
    )
    stats_result = await db.execute(stats_query)
    stats: dict[int, dict] = {}
    for tx_id, allocation_count, allocated_amount in stats_result.fetchall():
        stats[int(tx_id)] = {
            "allocation_count": int(allocation_count or 0),
            "allocated_amount": to_decimal(allocated_amount or ZERO_DECIMAL),
            "project_ids": set(),
        }

    project_query = (
        select(
            BankTransactionIncomeAllocation.bank_transaction_id,
            Income.project_id,
        )
        .join(Income, Income.id == BankTransactionIncomeAllocation.income_id)
        .where(BankTransactionIncomeAllocation.bank_transaction_id.in_(normalized_tx_ids))
    )
    project_result = await db.execute(project_query)
    for tx_id, project_id in project_result.fetchall():
        info = stats.setdefault(
            int(tx_id),
            {
                "allocation_count": 0,
                "allocated_amount": ZERO_DECIMAL,
                "project_ids": set(),
            },
        )
        info["project_ids"].add(project_id)

    for info in stats.values():
        project_ids = {project_id for project_id in info["project_ids"]}
        info["resolved_project_id"] = next(iter(project_ids)) if len(project_ids) == 1 else None
        del info["project_ids"]

    return stats


async def _suggest_income_matches(
    db: AsyncSession,
    tx: BankTransaction,
    *,
    exclude_tx_id: int | None = None,
    include_income_ids: list[int] | set[int] | None = None,
) -> list[dict]:
    include_ids = {int(value) for value in (include_income_ids or []) if value is not None}
    query = select(Income).options(
        selectinload(Income.client),
        selectinload(Income.project),
    )
    if include_ids:
        query = query.where(or_(Income.status.in_(["issued", "partial"]), Income.id.in_(include_ids)))
    else:
        query = query.where(Income.status.in_(["issued", "partial"]))

    response = await db.execute(query)
    incomes = list(response.scalars().all())
    if not incomes:
        return []

    summary_map = await _build_income_payment_summary_map(
        db,
        [income.id for income in incomes],
        exclude_tx_id=exclude_tx_id,
    )

    extracted_invoices: list[str] = []
    if tx.purpose:
        extracted_invoices.extend(_extract_invoice_candidates(tx.purpose))
    if tx.bank_reference:
        extracted_invoices.extend(_extract_invoice_candidates(tx.bank_reference))
    normalized_extracted = {_normalize_invoice_number(item) for item in extracted_invoices if item}

    def score_income(income: Income, remaining) -> tuple[int, float, int]:
        invoice_score = 1
        if normalized_extracted:
            income_invoice = _normalize_invoice_number(income.invoice_number)
            if income_invoice in normalized_extracted:
                invoice_score = 0

        amount_diff = money_abs(remaining - money_abs(tx.amount or ZERO_DECIMAL))
        date_diff = days_between(tx.date, income.issued_date, absolute=True)
        return (invoice_score, amount_diff, date_diff)

    def make_income_item(income: Income, remaining, score_value: int | None, section: str) -> dict:
        total = to_decimal(income.amount_rsd or ZERO_DECIMAL)
        paid = total - remaining
        client_label = income.client_name or (income.client.name if income.client else "")
        return {
            "id": income.id,
            "type": "income",
            "invoice_number": income.invoice_number,
            "client_name": client_label,
            "description": (income.description or "")[:80],
            "amount": remaining,
            "amount_full": total,
            "amount_paid": paid if paid > ZERO_DECIMAL else ZERO_DECIMAL,
            "date": str(income.issued_date),
            "status": income.status,
            "score": score_value,
            "section": section,
        }

    candidate_items: list[tuple[Income, float]] = []
    for income in incomes:
        remaining = _get_income_available_amount(income, summary_map)
        if remaining <= ZERO_DECIMAL and income.id not in include_ids:
            continue
        candidate_items.append((income, remaining))

    result: list[dict] = []
    scored: list[tuple[tuple[int, float, int], Income, float]] = []
    counterparty_matches: list[tuple[tuple[int, float, int], Income, float]] = []

    for income, remaining in candidate_items:
        score = score_income(income, remaining)
        if score[0] == 0 or score[1] <= 0.5:
            if not (score[0] == 1 and score[2] > 60):
                scored.append((score, income, remaining))
        if _matches_counterparty_name(tx, income):
            counterparty_matches.append((score, income, remaining))

    scored.sort(key=lambda item: item[0])
    picked_ids: set[int] = set()

    for score, income, remaining in scored[:5]:
        score_value = 100 if score[0] == 0 else max(10, 90 - score[2])
        result.append(make_income_item(income, remaining, score_value, "suggested"))
        picked_ids.add(income.id)

    counterparty_matches.sort(key=lambda item: item[0][2])
    for score, income, remaining in counterparty_matches:
        if income.id in picked_ids:
            continue
        result.append(make_income_item(income, remaining, None, "counterparty"))
        picked_ids.add(income.id)

    remaining_items = [
        (score_income(income, remaining), income, remaining)
        for income, remaining in candidate_items
        if income.id not in picked_ids
    ]
    remaining_items.sort(key=lambda item: item[0][2])
    for _, income, remaining in remaining_items:
        result.append(make_income_item(income, remaining, None, "all"))

    return result


async def suggest_matches(db: AsyncSession, tx: BankTransaction) -> list[dict]:
    if tx.direction == "out":
        if tx.status not in {"unmatched", "ignored"}:
            return []
        return await _suggest_outgoing_matches(db, tx)

    if tx.status not in {"unmatched", "ignored", "matched"}:
        return []
    if tx.status == "matched" and tx.matched_type not in {"income", MATCH_TYPE_INCOME_ALLOCATION}:
        return []

    exclude_tx_id = tx.id if tx.status == "matched" else None
    include_income_ids: set[int] = set()
    if tx.status == "matched" and tx.matched_type == "income" and tx.matched_id:
        include_income_ids.add(int(tx.matched_id))

    return await _suggest_income_matches(
        db,
        tx,
        exclude_tx_id=exclude_tx_id,
        include_income_ids=include_income_ids,
    )


def _build_income_allocation_line(
    income: Income,
    *,
    allocated_amount,
    available_amount,
) -> dict:
    client_label = income.client_name or (income.client.name if income.client else "")
    project = getattr(income, "project", None)
    total = to_decimal(income.amount_rsd or ZERO_DECIMAL)
    available = to_decimal(available_amount or ZERO_DECIMAL)
    allocated = to_decimal(allocated_amount or ZERO_DECIMAL)
    paid_excluding_current_tx = total - available
    return {
        "income_id": income.id,
        "invoice_number": income.invoice_number,
        "client_name": client_label,
        "description": income.description or "",
        "date": income.issued_date,
        "status": income.status,
        "amount_full": total,
        "amount_paid": paid_excluding_current_tx if paid_excluding_current_tx > ZERO_DECIMAL else ZERO_DECIMAL,
        "available_amount": available,
        "allocated_amount": allocated,
        "project_id": income.project_id,
        "project_name": getattr(project, "name", None),
        "project_code": getattr(project, "code", None),
    }


async def _get_transaction_income_allocations(
    db: AsyncSession,
    tx_id: int,
) -> list[BankTransactionIncomeAllocation]:
    result = await db.execute(
        select(BankTransactionIncomeAllocation)
        .options(
            selectinload(BankTransactionIncomeAllocation.income).selectinload(Income.client),
            selectinload(BankTransactionIncomeAllocation.income).selectinload(Income.project),
        )
        .where(BankTransactionIncomeAllocation.bank_transaction_id == tx_id)
        .order_by(BankTransactionIncomeAllocation.id.asc())
    )
    return list(result.scalars().all())


async def get_income_allocation_editor_state(db: AsyncSession, tx: BankTransaction) -> dict:
    if tx.direction != "in":
        raise ValueError("Income allocation is only available for incoming transactions")
    if tx.status == "matched" and tx.matched_type not in {"income", MATCH_TYPE_INCOME_ALLOCATION}:
        raise ValueError("Transaction is matched to another entity")

    current_income_ids: set[int] = set()
    current_allocations = await _get_transaction_income_allocations(db, tx.id)
    if current_allocations:
        current_income_ids.update(int(item.income_id) for item in current_allocations)
    elif tx.status == "matched" and tx.matched_type == "income" and tx.matched_id:
        current_income_ids.add(int(tx.matched_id))

    candidates = await _suggest_income_matches(
        db,
        tx,
        exclude_tx_id=tx.id if tx.status == "matched" else None,
        include_income_ids=current_income_ids,
    )
    candidate_map = {int(item["id"]): item for item in candidates}

    allocations: list[dict] = []
    if current_income_ids:
        income_result = await db.execute(
            select(Income)
            .options(selectinload(Income.client), selectinload(Income.project))
            .where(Income.id.in_(current_income_ids))
        )
        income_map = {int(income.id): income for income in income_result.scalars().all()}
    else:
        income_map = {}

    if current_allocations:
        for allocation in current_allocations:
            income = allocation.income
            if not income:
                continue
            available_amount = to_decimal(candidate_map.get(int(income.id), {}).get("amount", ZERO_DECIMAL))
            allocations.append(
                _build_income_allocation_line(
                    income,
                    allocated_amount=allocation.amount,
                    available_amount=available_amount,
                )
            )
    elif tx.status == "matched" and tx.matched_type == "income" and tx.matched_id:
        income = income_map.get(int(tx.matched_id))
        if income:
            available_amount = to_decimal(candidate_map.get(int(income.id), {}).get("amount", tx.amount or ZERO_DECIMAL))
            allocations.append(
                _build_income_allocation_line(
                    income,
                    allocated_amount=tx.amount,
                    available_amount=available_amount,
                )
            )

    allocated_amount = decimal_sum([item["allocated_amount"] for item in allocations])
    total_amount = to_decimal(tx.amount or ZERO_DECIMAL)
    remaining_amount = total_amount - allocated_amount
    if remaining_amount < ZERO_DECIMAL:
        remaining_amount = ZERO_DECIMAL

    return {
        "tx_id": tx.id,
        "total_amount": total_amount,
        "allocated_amount": allocated_amount,
        "remaining_amount": remaining_amount,
        "allocations": allocations,
        "candidates": candidates,
    }


async def save_income_allocation(
    db: AsyncSession,
    tx_id: int,
    allocations: list,
    *,
    current_user_id: int | None = None,
):
    response = await db.execute(select(BankTransaction).where(BankTransaction.id == tx_id))
    tx = response.scalar_one_or_none()
    if not tx:
        raise ValueError("BankTransaction not found")
    if tx.direction != "in":
        raise ValueError("Only incoming transactions can be distributed")
    if tx.status == "matched" and tx.matched_type not in {"income", MATCH_TYPE_INCOME_ALLOCATION}:
        raise ValueError("Transaction is matched to another entity")

    normalized_allocations: list[tuple[int, object]] = []
    seen_income_ids: set[int] = set()
    total_allocated = ZERO_DECIMAL
    for item in allocations:
        income_id = int(getattr(item, "income_id", None) if not isinstance(item, dict) else item.get("income_id"))
        amount = to_decimal(getattr(item, "amount", None) if not isinstance(item, dict) else item.get("amount"))
        if income_id in seen_income_ids:
            raise ValueError("Duplicate invoice in allocation")
        if amount <= ZERO_DECIMAL:
            raise ValueError("Allocation amount must be greater than zero")
        normalized_allocations.append((income_id, amount))
        seen_income_ids.add(income_id)
        total_allocated += amount

    if not normalized_allocations:
        raise ValueError("Select at least one invoice")
    if total_allocated > to_decimal(tx.amount or ZERO_DECIMAL) + to_decimal("0.01"):
        raise ValueError("Allocated amount exceeds transaction amount")

    affected_income_ids: set[int] = set()
    existing_allocations = await _get_transaction_income_allocations(db, tx.id)
    if existing_allocations:
        affected_income_ids.update(int(item.income_id) for item in existing_allocations)
    elif tx.status == "matched" and tx.matched_type == "income" and tx.matched_id:
        affected_income_ids.add(int(tx.matched_id))

    requested_income_ids = {income_id for income_id, _ in normalized_allocations}
    validation_ids = affected_income_ids | requested_income_ids
    income_result = await db.execute(
        select(Income)
        .options(selectinload(Income.client), selectinload(Income.project))
        .where(Income.id.in_(validation_ids))
    )
    income_map = {int(income.id): income for income in income_result.scalars().all()}
    missing_income_ids = validation_ids.difference(income_map.keys())
    if missing_income_ids:
        raise ValueError("Income not found")

    summary_map = await _build_income_payment_summary_map(
        db,
        validation_ids,
        exclude_tx_id=tx.id if tx.status == "matched" else None,
    )

    for income_id, amount in normalized_allocations:
        income = income_map[income_id]
        if income.status == "cancelled":
            raise ValueError(f"Invoice {income.invoice_number} is cancelled")
        available_amount = _get_income_available_amount(income, summary_map)
        if amount > available_amount + to_decimal("0.01"):
            raise ValueError(f"Allocation exceeds open amount for invoice {income.invoice_number}")

    for allocation in existing_allocations:
        await db.delete(allocation)
    await db.flush()

    tx.status = "matched"
    tx.matched_type = MATCH_TYPE_INCOME_ALLOCATION
    tx.matched_id = None

    for income_id, amount in normalized_allocations:
        db.add(
            BankTransactionIncomeAllocation(
                bank_transaction_id=tx.id,
                income_id=income_id,
                amount=amount,
                created_by=current_user_id,
            )
        )

    project_values = {income_map[income_id].project_id for income_id, _ in normalized_allocations}
    tx.project_id = next(iter(project_values)) if len(project_values) == 1 else None

    await db.flush()
    await reconcile_income_payment_links(db, affected_income_ids | requested_income_ids)
    return tx


async def detach_income_transaction_link(
    db: AsyncSession,
    tx_id: int,
    income_id: int,
    *,
    current_user_id: int | None = None,
) -> None:
    response = await db.execute(select(BankTransaction).where(BankTransaction.id == tx_id))
    tx = response.scalar_one_or_none()
    if not tx or tx.status != "matched":
        return

    normalized_income_id = int(income_id)

    if tx.matched_type == "income":
        if int(tx.matched_id or 0) == normalized_income_id:
            await unmatch_transaction(db, tx_id, current_user_id=current_user_id)
        return

    if tx.matched_type != MATCH_TYPE_INCOME_ALLOCATION:
        return

    existing_allocations = await _get_transaction_income_allocations(db, tx.id)
    target_allocations = [item for item in existing_allocations if int(item.income_id) == normalized_income_id]
    if not target_allocations:
        return

    if len(existing_allocations) <= 1:
        await unmatch_transaction(db, tx_id, current_user_id=current_user_id)
        return

    affected_income_ids = {int(item.income_id) for item in existing_allocations}
    remaining_allocations = [item for item in existing_allocations if int(item.income_id) != normalized_income_id]

    for allocation in target_allocations:
        await db.delete(allocation)
    await db.flush()

    if remaining_allocations:
        tx.status = "matched"
        tx.matched_type = MATCH_TYPE_INCOME_ALLOCATION
        tx.matched_id = None
        project_values = {item.income.project_id for item in remaining_allocations if item.income}
        tx.project_id = next(iter(project_values)) if len(project_values) == 1 else None
    else:
        tx.status = "unmatched"
        tx.matched_type = None
        tx.matched_id = None
        if tx.direction == "in":
            tx.project_id = None

    await db.flush()
    await reconcile_income_payment_links(db, affected_income_ids)


async def _find_incoming_invoice_by_expense(db: AsyncSession, expense_id: int) -> IncomingInvoice | None:
    result = await db.execute(
        select(IncomingInvoice).where(IncomingInvoice.expense_id == expense_id)
    )
    return result.scalar_one_or_none()


async def _ensure_expense_can_reclassify_to_owner_funds(
    db: AsyncSession,
    tx: BankTransaction,
    expense: Expense,
) -> None:
    if is_cash_transfer_expense(expense):
        raise ValueError("Cash transfer operations must stay in bank/cash workflow")
    if getattr(expense, "source", None) == "cash":
        raise ValueError("Cash expenses must be managed from the cash register")
    if getattr(expense, "reversal_of_id", None) or getattr(expense, "reversed_expense_id", None):
        raise ValueError("Reversed expenses cannot be converted to owner funds")

    invoice = await _find_incoming_invoice_by_expense(db, expense.id)
    if invoice:
        raise ValueError("This expense is linked to an incoming invoice")

    obligation_result = await db.execute(
        select(MonthlyObligation.id).where(MonthlyObligation.expense_id == expense.id).limit(1)
    )
    if obligation_result.scalar_one_or_none():
        raise ValueError("This expense is linked to a tax/obligation payment")

    cash_entry_result = await db.execute(
        select(func.count()).select_from(CashEntry).where(CashEntry.expense_id == expense.id)
    )
    cash_entry_count = int(cash_entry_result.scalar() or 0)
    if cash_entry_count > 0:
        raise ValueError("This expense is linked to cash register entries")

    planned_payment_result = await db.execute(
        select(func.count()).select_from(PlannedExpensePayment).where(PlannedExpensePayment.expense_id == expense.id)
    )
    if int(planned_payment_result.scalar() or 0) > 0:
        raise ValueError("This expense is linked to recurring expense payments")

    recurring_payment_result = await db.execute(
        select(func.count()).select_from(BankTransaction).where(
            BankTransaction.matched_type == "expense",
            BankTransaction.matched_id == expense.id,
            BankTransaction.id != tx.id,
        )
    )
    if int(recurring_payment_result.scalar() or 0) > 0:
        raise ValueError("This expense is linked to multiple bank transactions")


async def classify_transaction_as_owner_funds(
    db: AsyncSession,
    tx_id: int,
):
    response = await db.execute(select(BankTransaction).where(BankTransaction.id == tx_id))
    tx = response.scalar_one_or_none()
    if not tx:
        raise ValueError("BankTransaction not found")

    if tx.status == "matched":
        if tx.matched_type == MATCH_TYPE_OWNER_FUNDS:
            tx.project_id = None
            await db.flush()
            return tx
        if tx.matched_type == "expense" and tx.matched_id:
            expense_response = await db.execute(select(Expense).where(Expense.id == tx.matched_id))
            expense = expense_response.scalar_one_or_none()
            if not expense:
                raise ValueError("Expense not found")
            await _ensure_expense_can_reclassify_to_owner_funds(db, tx, expense)
            await db.delete(expense)
            await db.flush()
        else:
            raise ValueError("Only unmatched transactions or simple expense matches can be classified as owner funds")
    elif tx.status not in {"unmatched", "ignored"}:
        raise ValueError("Transaction cannot be classified as owner funds in the current state")

    tx.status = "matched"
    tx.matched_type = MATCH_TYPE_OWNER_FUNDS
    tx.matched_id = None
    tx.project_id = None
    await db.flush()
    return tx


async def _sync_incoming_invoice_on_match(db: AsyncSession, expense: Expense, tx: BankTransaction) -> None:
    if getattr(expense, "source", None) != "incoming_invoice":
        return
    invoice = await _find_incoming_invoice_by_expense(db, expense.id)
    if not invoice or invoice.status in {"paid", "cancelled"}:
        return
    existing = await db.execute(
        select(IncomingInvoiceSettlement).where(
            IncomingInvoiceSettlement.incoming_invoice_id == invoice.id,
            IncomingInvoiceSettlement.bank_transaction_id == tx.id,
        )
    )
    if existing.scalar_one_or_none():
        return
    settlement = IncomingInvoiceSettlement(
        incoming_invoice_id=invoice.id,
        settlement_type="bank",
        amount=to_decimal(tx.amount),
        date=tx.date,
        bank_transaction_id=tx.id,
    )
    db.add(settlement)
    await db.flush()
    all_q = await db.execute(
        select(IncomingInvoiceSettlement).where(
            IncomingInvoiceSettlement.incoming_invoice_id == invoice.id
        )
    )
    all_settlements = list(all_q.scalars().all())
    total = sum((to_decimal(s.amount) for s in all_settlements), ZERO_DECIMAL)
    invoice.settled_amount = total
    reconcile_incoming_invoice_status(invoice)


async def _sync_incoming_invoice_on_unmatch(db: AsyncSession, expense: Expense, tx: BankTransaction) -> None:
    if getattr(expense, "source", None) != "incoming_invoice":
        return
    invoice = await _find_incoming_invoice_by_expense(db, expense.id)
    if not invoice:
        return
    result = await db.execute(
        select(IncomingInvoiceSettlement).where(
            IncomingInvoiceSettlement.incoming_invoice_id == invoice.id,
            IncomingInvoiceSettlement.bank_transaction_id == tx.id,
        )
    )
    settlement = result.scalar_one_or_none()
    if settlement:
        await db.delete(settlement)
        await db.flush()
    all_q = await db.execute(
        select(IncomingInvoiceSettlement).where(
            IncomingInvoiceSettlement.incoming_invoice_id == invoice.id
        )
    )
    all_settlements = list(all_q.scalars().all())
    total = sum((to_decimal(s.amount) for s in all_settlements), ZERO_DECIMAL)
    invoice.settled_amount = total
    reconcile_incoming_invoice_status(invoice)


async def match_transaction(db: AsyncSession, tx_id: int, match_type: str, match_id: int):
    response = await db.execute(select(BankTransaction).where(BankTransaction.id == tx_id))
    tx = response.scalar_one_or_none()

    if not tx:
        raise ValueError("BankTransaction not found")
    if tx.status not in {"unmatched", "ignored"}:
        raise ValueError("Transaction is already matched")

    if match_type == "income":
        income_response = await db.execute(select(Income).where(Income.id == match_id))
        income = income_response.scalar_one_or_none()
        if not income:
            raise ValueError("Income not found")
        project_id = tx.project_id or getattr(income, "project_id", None) or await get_unassigned_project_id(db)
        if project_id is not None:
            await _sync_income_project(db, income, project_id)
            tx.project_id = project_id
        tx.status = "matched"
        tx.matched_type = match_type
        tx.matched_id = match_id
        await db.flush()
        await reconcile_income_payment_links(db, {income.id})

    elif match_type == "expense":
        expense_response = await db.execute(select(Expense).where(Expense.id == match_id))
        expense = expense_response.scalar_one_or_none()
        if not expense:
            raise ValueError("Expense not found")

        mark_expense_paid(expense, paid_date=tx.date, allow_same=True)
        if tx.bank_reference and not expense.bank_reference:
            expense.bank_reference = tx.bank_reference

        project_id = tx.project_id or getattr(expense, "project_id", None)
        if project_id is not None:
            expense.project_id = project_id
            tx.project_id = project_id
            await _clear_contract_if_project_mismatch(db, expense, project_id)

        await _sync_incoming_invoice_on_match(db, expense, tx)
        await sync_receipt_for_expense_match(db, expense, tx)

    elif match_type == "obligation":
        obligation_response = await db.execute(select(MonthlyObligation).where(MonthlyObligation.id == match_id))
        obligation = obligation_response.scalar_one_or_none()
        if not obligation:
            raise ValueError("MonthlyObligation not found")
        await mark_obligation_paid(
            db,
            obligation,
            tx.date,
            payment_reference=tx.bank_reference,
            payment_method="bank_import",
            bank_transaction=tx,
        )

    else:
        raise ValueError("Unknown match type")

    if match_type not in {"obligation", "income"}:
        tx.status = "matched"
        tx.matched_type = match_type
        tx.matched_id = match_id

    await db.flush()
    return tx


async def unmatch_transaction(db: AsyncSession, tx_id: int, current_user_id: int | None = None):
    response = await db.execute(select(BankTransaction).where(BankTransaction.id == tx_id))
    tx = response.scalar_one_or_none()

    if not tx:
        raise ValueError("BankTransaction not found")
    if tx.status != "matched" or not tx.matched_type or (
        tx.matched_type not in {MATCH_TYPE_INCOME_ALLOCATION, MATCH_TYPE_OWNER_FUNDS} and not tx.matched_id
    ):
        raise ValueError("Transaction is not matched")

    affected_income_ids: set[int] = set()

    if tx.matched_type == "income":
        if tx.matched_id:
            affected_income_ids.add(int(tx.matched_id))

    elif tx.matched_type == MATCH_TYPE_INCOME_ALLOCATION:
        existing_allocations = await _get_transaction_income_allocations(db, tx.id)
        affected_income_ids.update(int(item.income_id) for item in existing_allocations)
        for allocation in existing_allocations:
            await db.delete(allocation)
        await db.flush()

    elif tx.matched_type == "expense":
        expense_response = await db.execute(select(Expense).where(Expense.id == tx.matched_id))
        expense = expense_response.scalar_one_or_none()
        if expense:
            if is_cash_transfer_expense(expense):
                await revert_cash_transfer(db, tx, expense=expense)
                await db.flush()
                return tx
            await _sync_incoming_invoice_on_unmatch(db, expense, tx)
            await sync_receipt_for_expense_unmatch(db, expense)
            reopen_expense_for_unmatch(expense)

    elif tx.matched_type == MATCH_TYPE_OWNER_FUNDS:
        pass

    elif tx.matched_type == "obligation":
        obligation_response = await db.execute(select(MonthlyObligation).where(MonthlyObligation.id == tx.matched_id))
        obligation = obligation_response.scalar_one_or_none()
        if obligation:
            await reset_obligation_payment(db, obligation, created_by=current_user_id)
    elif tx.matched_type == "cash":
        cash_entry_response = await db.execute(select(CashEntry).where(CashEntry.id == tx.matched_id))
        cash_entry = cash_entry_response.scalar_one_or_none()
        if cash_entry:
            await revert_cash_transfer(db, tx, cash_entry=cash_entry)
            await db.flush()
            return tx

    tx.status = "unmatched"
    tx.matched_type = None
    tx.matched_id = None
    if tx.direction == "in":
        tx.project_id = None

    await db.flush()
    if affected_income_ids:
        await reconcile_income_payment_links(db, affected_income_ids)
    return tx


