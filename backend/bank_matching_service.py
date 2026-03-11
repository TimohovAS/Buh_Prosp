from datetime import date
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.cash_service import is_cash_transfer_expense, revert_cash_transfer
from backend.obligation_payment_service import mark_obligation_paid, reset_obligation_payment
from backend.models import BankTransaction, CashEntry, Contract, Expense, Income, MonthlyObligation, Project
from backend.services import _extract_invoice_candidates, _normalize_invoice_number


def _safe_paid_amount(income: Income) -> float:
    return float(getattr(income, "paid_amount", None) or 0)


async def _get_unassigned_project_id(db: AsyncSession) -> int | None:
    result = await db.execute(select(Project).where(Project.code == "INT-UNASSIGNED"))
    project = result.scalar_one_or_none()
    return project.id if project else None


async def _get_project_or_404(db: AsyncSession, project_id: int) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise ValueError("Project not found")
    if project.status == "archived":
        raise ValueError("Cannot use archived project")
    return project


async def _get_contract_or_404(db: AsyncSession, contract_id: int) -> Contract:
    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()
    if not contract:
        raise ValueError("Contract not found")
    return contract


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


async def _sync_income_project(db: AsyncSession, income: Income, project_id: int | None) -> None:
    income.project_id = project_id
    if income.contract_id is None or project_id is None:
        return

    contract = await _get_contract_or_404(db, income.contract_id)
    if contract.project_id is None:
        await _get_project_or_404(db, project_id)
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
    scored: list[tuple[tuple[int, float, int], dict]] = []

    for obligation in obligations:
        decision = getattr(obligation, "decision", None)
        amount_diff = abs(float(obligation.amount or 0) - float(tx.amount or 0))
        deadline_diff = abs((tx.date - obligation.deadline).days)
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
                amount_diff,
                deadline_diff,
            ),
            {
                "id": obligation.id,
                "type": "obligation",
                "invoice_number": None,
                "client_name": getattr(decision, "recipient_account", None),
                "description": _build_obligation_description(obligation),
                "amount": float(obligation.amount or 0),
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


async def suggest_matches(db: AsyncSession, tx: BankTransaction) -> list[dict]:
    if tx.status not in {"unmatched", "ignored"}:
        return []

    if tx.direction == "out":
        return await _suggest_outgoing_matches(db, tx)

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
        project_id = tx.project_id or getattr(income, "project_id", None) or await _get_unassigned_project_id(db)
        if project_id is not None:
            await _sync_income_project(db, income, project_id)
            tx.project_id = project_id

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

    if match_type != "obligation":
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
            if is_cash_transfer_expense(expense):
                await revert_cash_transfer(db, tx, expense=expense)
                await db.flush()
                return tx
            expense.status = "planned"
            expense.paid_date = None

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

    await db.flush()
    return tx
