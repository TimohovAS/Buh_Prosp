from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import BankTransaction, Contract, Expense, Income, MonthlyObligation
from backend.services import _extract_invoice_candidates, _normalize_invoice_number


def _safe_paid_amount(income: Income) -> float:
    return float(getattr(income, "paid_amount", None) or 0)


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


async def _clear_contract_if_project_mismatch(db: AsyncSession, expense: Expense, project_id: int | None) -> None:
    if not expense.contract_id or project_id is None:
        return
    result = await db.execute(select(Contract).where(Contract.id == expense.contract_id))
    contract = result.scalar_one_or_none()
    if contract and contract.project_id != project_id:
        expense.contract_id = None


async def suggest_matches(db: AsyncSession, tx: BankTransaction) -> list[dict]:
    if tx.status not in {"unmatched", "ignored"}:
        return []

    if tx.direction != "in":
        return []

    result: list[dict] = []
    query = select(Income).options(selectinload(Income.client)).where(Income.status.in_(["issued", "partial"]))
    response = await db.execute(query)
    incomes = response.scalars().all()

    extracted_invoices: list[str] = []
    if tx.purpose:
        extracted_invoices.extend(_extract_invoice_candidates(tx.purpose))
    if tx.bank_reference:
        extracted_invoices.extend(_extract_invoice_candidates(tx.bank_reference))
    normalized_extracted = {_normalize_invoice_number(item) for item in extracted_invoices if item}

    def score_income(income: Income) -> tuple[int, float, int]:
        invoice_score = 1
        if normalized_extracted:
            income_invoice = _normalize_invoice_number(income.invoice_number)
            if income_invoice in normalized_extracted:
                invoice_score = 0

        remaining = float(income.amount_rsd) - _safe_paid_amount(income)
        amount_diff = abs(remaining - float(tx.amount))
        date_diff = abs((tx.date - income.issued_date).days)
        return (invoice_score, amount_diff, date_diff)

    def make_income_item(income: Income, score_value: int | None, section: str) -> dict:
        paid = _safe_paid_amount(income)
        remaining = float(income.amount_rsd) - paid
        client_label = income.client_name or (income.client.name if income.client else "")
        return {
            "id": income.id,
            "type": "income",
            "invoice_number": income.invoice_number,
            "client_name": client_label,
            "description": (income.description or "")[:80],
            "amount": remaining,
            "amount_full": float(income.amount_rsd),
            "amount_paid": paid,
            "date": str(income.issued_date),
            "status": income.status,
            "score": score_value,
            "section": section,
        }

    scored: list[tuple[tuple[int, float, int], Income]] = []
    counterparty_matches: list[tuple[tuple[int, float, int], Income]] = []

    for income in incomes:
        score = score_income(income)
        if score[0] == 0 or score[1] <= 0.5:
            if not (score[0] == 1 and score[2] > 60):
                scored.append((score, income))
        if _matches_counterparty_name(tx, income):
            counterparty_matches.append((score, income))

    scored.sort(key=lambda item: item[0])
    picked_ids: set[int] = set()

    for score, income in scored[:5]:
        score_value = 100 if score[0] == 0 else max(10, 90 - score[2])
        result.append(make_income_item(income, score_value, "suggested"))
        picked_ids.add(income.id)

    counterparty_matches.sort(key=lambda item: item[0][2])
    for score, income in counterparty_matches:
        if income.id in picked_ids:
            continue
        result.append(make_income_item(income, None, "counterparty"))
        picked_ids.add(income.id)

    remaining = [(score_income(income), income) for income in incomes if income.id not in picked_ids]
    remaining.sort(key=lambda item: item[0][2])
    for _, income in remaining:
        result.append(make_income_item(income, None, "all"))

    return result


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

        new_paid = float(income.paid_amount or 0) + float(tx.amount)
        income.paid_amount = new_paid
        if new_paid >= float(income.amount_rsd):
            income.status = "paid"
            income.is_paid = True
            income.paid_date = tx.date
        else:
            income.status = "partial"
            income.is_paid = False

        if tx.bank_reference and not income.bank_reference:
            income.bank_reference = tx.bank_reference
        tx.project_id = getattr(income, "project_id", None) or tx.project_id

    elif match_type == "expense":
        expense_response = await db.execute(select(Expense).where(Expense.id == match_id))
        expense = expense_response.scalar_one_or_none()
        if not expense:
            raise ValueError("Expense not found")

        expense.status = "paid"
        expense.paid_date = tx.date
        if tx.bank_reference and not expense.bank_reference:
            expense.bank_reference = tx.bank_reference

        project_id = tx.project_id or getattr(expense, "project_id", None)
        if project_id is not None:
            expense.project_id = project_id
            tx.project_id = project_id
            await _clear_contract_if_project_mismatch(db, expense, project_id)

    elif match_type == "obligation":
        obligation_response = await db.execute(select(MonthlyObligation).where(MonthlyObligation.id == match_id))
        obligation = obligation_response.scalar_one_or_none()
        if not obligation:
            raise ValueError("MonthlyObligation not found")

        obligation.status = "paid"
        obligation.paid_date = tx.date

    else:
        raise ValueError("Unknown match type")

    tx.status = "matched"
    tx.matched_type = match_type
    tx.matched_id = match_id

    await db.flush()
    return tx


async def unmatch_transaction(db: AsyncSession, tx_id: int):
    response = await db.execute(select(BankTransaction).where(BankTransaction.id == tx_id))
    tx = response.scalar_one_or_none()

    if not tx:
        raise ValueError("BankTransaction not found")
    if tx.status != "matched" or not tx.matched_type or not tx.matched_id:
        raise ValueError("Transaction is not matched")

    if tx.matched_type == "income":
        income_response = await db.execute(select(Income).where(Income.id == tx.matched_id))
        income = income_response.scalar_one_or_none()
        if income:
            remaining_response = await db.execute(
                select(BankTransaction)
                .where(
                    BankTransaction.matched_type == "income",
                    BankTransaction.matched_id == income.id,
                    BankTransaction.id != tx.id,
                )
                .order_by(BankTransaction.date.desc(), BankTransaction.id.desc())
            )
            remaining_transactions = list(remaining_response.scalars().all())
            remaining_paid = sum(float(item.amount or 0) for item in remaining_transactions)
            amount_total = float(income.amount_rsd or 0)
            income.paid_amount = remaining_paid
            if remaining_paid >= amount_total and remaining_paid > 0:
                income.status = "paid"
                income.is_paid = True
                income.paid_date = remaining_transactions[0].date
            elif remaining_paid > 0:
                income.status = "partial"
                income.is_paid = False
                income.paid_date = None
            else:
                income.status = "issued"
                income.is_paid = False
                income.paid_date = None

            income.bank_reference = next((item.bank_reference for item in remaining_transactions if item.bank_reference), None)

    elif tx.matched_type == "expense":
        expense_response = await db.execute(select(Expense).where(Expense.id == tx.matched_id))
        expense = expense_response.scalar_one_or_none()
        if expense:
            expense.status = "planned"
            expense.paid_date = None

    elif tx.matched_type == "obligation":
        obligation_response = await db.execute(select(MonthlyObligation).where(MonthlyObligation.id == tx.matched_id))
        obligation = obligation_response.scalar_one_or_none()
        if obligation:
            obligation.status = "unpaid"
            obligation.paid_date = None
            if obligation.deadline < date.today():
                obligation.status = "overdue"

    tx.status = "unmatched"
    tx.matched_type = None
    tx.matched_id = None

    await db.flush()
    return tx
