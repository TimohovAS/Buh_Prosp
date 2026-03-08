from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import BankTransaction, Expense, Income, MonthlyObligation
from backend.services import _extract_invoice_candidates, _normalize_invoice_number


def _safe_paid_amount(income: Income) -> float:
    return float(getattr(income, 'paid_amount', None) or 0)


def _matches_counterparty_name(tx: BankTransaction, income: Income) -> bool:
    counterparty_norm = (tx.counterparty_name or '').lower().strip()
    if not counterparty_norm:
        return False

    raw_name = income.client_name or (income.client.name if income.client else '')
    client_norm = raw_name.lower().strip()
    if not client_norm:
        return False

    cp_words = counterparty_norm.split()[:4]
    cl_words = client_norm.split()[:4]
    common = sum(1 for word in cp_words if any(word == client_word or word in client_word or client_word in word for client_word in cl_words))
    return common >= 2 or client_norm in counterparty_norm or counterparty_norm in client_norm


async def suggest_matches(db: AsyncSession, tx: BankTransaction) -> list[dict]:
    if tx.status != 'unmatched':
        return []

    result: list[dict] = []

    if tx.direction == 'in':
        query = select(Income).options(selectinload(Income.client)).where(
            Income.status.in_(['issued', 'partial'])
        )
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
            client_label = income.client_name or (income.client.name if income.client else '')
            return {
                'id': income.id,
                'type': 'income',
                'invoice_number': income.invoice_number,
                'client_name': client_label,
                'description': (income.description or '')[:80],
                'amount': remaining,
                'amount_full': float(income.amount_rsd),
                'amount_paid': paid,
                'date': str(income.issued_date),
                'status': income.status,
                'score': score_value,
                'section': section,
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
            result.append(make_income_item(income, score_value, 'suggested'))
            picked_ids.add(income.id)

        counterparty_matches.sort(key=lambda item: item[0][2])
        for score, income in counterparty_matches:
            if income.id in picked_ids:
                continue
            result.append(make_income_item(income, None, 'counterparty'))
            picked_ids.add(income.id)

        remaining = [(score_income(income), income) for income in incomes if income.id not in picked_ids]
        remaining.sort(key=lambda item: item[0][2])
        for _, income in remaining:
            result.append(make_income_item(income, None, 'all'))

    elif tx.direction == 'out':
        query = select(Expense).options(selectinload(Expense.project)).where(Expense.status != 'reversed')
        response = await db.execute(query)
        expenses = response.scalars().all()

        def score_expense(expense: Expense) -> tuple[int, int, float, int]:
            reference_score = 1
            if tx.bank_reference and expense.bank_reference and tx.bank_reference == expense.bank_reference:
                reference_score = 0
            project_score = 0 if tx.project_id and expense.project_id == tx.project_id else 1
            amount_diff = abs(float(expense.amount or 0) - float(tx.amount or 0))
            compare_date = expense.paid_date or expense.date or tx.date
            date_diff = abs((tx.date - compare_date).days)
            return (reference_score, project_score, amount_diff, date_diff)

        matches: list[tuple[tuple[int, int, float, int], Expense]] = []
        for expense in expenses:
            if getattr(expense, 'reversal_of_id', None) or getattr(expense, 'reversed_expense_id', None):
                continue
            score = score_expense(expense)
            if score[0] == 0 or score[2] <= 0.5 or score[3] <= 14:
                matches.append((score, expense))

        matches.sort(key=lambda item: item[0])
        for score, expense in matches[:10]:
            score_value = 100 if score[0] == 0 else max(10, 95 - min(score[3], 45) - int(score[2] * 10))
            result.append({
                'id': expense.id,
                'type': 'expense',
                'invoice_number': None,
                'client_name': expense.project.name if getattr(expense, 'project', None) else None,
                'description': (expense.description or '')[:80],
                'amount': float(expense.amount or 0),
                'amount_full': float(expense.amount or 0),
                'amount_paid': None,
                'date': str(expense.date),
                'status': expense.status,
                'score': score_value,
                'section': 'suggested',
            })

    return result


async def match_transaction(db: AsyncSession, tx_id: int, match_type: str, match_id: int):
    response = await db.execute(select(BankTransaction).where(BankTransaction.id == tx_id))
    tx = response.scalar_one_or_none()

    if not tx:
        raise ValueError('BankTransaction не найдена')
    if tx.status != 'unmatched':
        raise ValueError('Транзакция уже сопоставлена или проигнорирована')

    if match_type == 'income':
        income_response = await db.execute(select(Income).where(Income.id == match_id))
        income = income_response.scalar_one_or_none()
        if not income:
            raise ValueError('Income не найден')

        new_paid = float(income.paid_amount or 0) + float(tx.amount)
        income.paid_amount = new_paid
        if new_paid >= float(income.amount_rsd):
            income.status = 'paid'
            income.is_paid = True
            income.paid_date = tx.date
        else:
            income.status = 'partial'
            income.is_paid = False

        if tx.bank_reference and not income.bank_reference:
            income.bank_reference = tx.bank_reference
        tx.project_id = getattr(income, 'project_id', None) or tx.project_id

    elif match_type == 'expense':
        expense_response = await db.execute(select(Expense).where(Expense.id == match_id))
        expense = expense_response.scalar_one_or_none()
        if not expense:
            raise ValueError('Expense не найден')

        expense.status = 'paid'
        expense.paid_date = tx.date
        if tx.bank_reference and not expense.bank_reference:
            expense.bank_reference = tx.bank_reference

        project_id = tx.project_id or getattr(expense, 'project_id', None)
        if project_id is not None:
            expense.project_id = project_id
            tx.project_id = project_id

    elif match_type == 'obligation':
        obligation_response = await db.execute(select(MonthlyObligation).where(MonthlyObligation.id == match_id))
        obligation = obligation_response.scalar_one_or_none()
        if not obligation:
            raise ValueError('MonthlyObligation не найдено')

        obligation.status = 'paid'
        obligation.paid_date = tx.date

    else:
        raise ValueError('Неизвестный тип сопоставления')

    tx.status = 'matched'
    tx.matched_type = match_type
    tx.matched_id = match_id

    await db.flush()
    return tx


async def unmatch_transaction(db: AsyncSession, tx_id: int):
    response = await db.execute(select(BankTransaction).where(BankTransaction.id == tx_id))
    tx = response.scalar_one_or_none()

    if not tx:
        raise ValueError('BankTransaction не найдена')
    if tx.status != 'matched' or not tx.matched_type or not tx.matched_id:
        raise ValueError('Транзакция не сопоставлена')

    if tx.matched_type == 'income':
        income_response = await db.execute(select(Income).where(Income.id == tx.matched_id))
        income = income_response.scalar_one_or_none()
        if income:
            new_paid = max(0.0, float(income.paid_amount or 0) - float(tx.amount))
            income.paid_amount = new_paid
            if new_paid <= 0:
                income.status = 'issued'
                income.is_paid = False
                income.paid_date = None
            else:
                income.status = 'partial'
                income.is_paid = False
                income.paid_date = None

    elif tx.matched_type == 'expense':
        expense_response = await db.execute(select(Expense).where(Expense.id == tx.matched_id))
        expense = expense_response.scalar_one_or_none()
        if expense:
            expense.status = 'planned'
            expense.paid_date = None

    elif tx.matched_type == 'obligation':
        obligation_response = await db.execute(select(MonthlyObligation).where(MonthlyObligation.id == tx.matched_id))
        obligation = obligation_response.scalar_one_or_none()
        if obligation:
            obligation.status = 'unpaid'
            obligation.paid_date = None
            if obligation.deadline < date.today():
                obligation.status = 'overdue'

    tx.status = 'unmatched'
    tx.matched_type = None
    tx.matched_id = None

    await db.flush()
    return tx
