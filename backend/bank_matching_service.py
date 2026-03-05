"""Модуль сопоставления банковских транзакций с документами системы (invoices, expenses, obligations)."""
from datetime import date
from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import BankTransaction, Income, Expense, MonthlyObligation
from backend.services import _normalize_invoice_number, _extract_invoice_candidates


async def suggest_matches(db: AsyncSession, tx: BankTransaction) -> list[dict]:
    """Вернуть кандидатов для сопоставления с банковской транзакцией.
    
    Возвращает:
    - Топ кандидатов по сумме/номеру (section='suggested')
    - Все открытые фактуры контрагента (section='counterparty')
    """
    if tx.status != "unmatched":
        return []

    result = []

    if tx.direction == "in":
        # Все незакрытые фактуры — загружаем клиента сразу, чтобы использовать client.name
        q = select(Income).options(selectinload(Income.client)).where(
            Income.status.in_(["issued", "partial"]),
        )
        r = await db.execute(q)
        incomes = r.scalars().all()

        extracted_invoices = []
        if tx.purpose:
            extracted_invoices.extend(_extract_invoice_candidates(tx.purpose))
        if tx.bank_reference:
            extracted_invoices.extend(_extract_invoice_candidates(tx.bank_reference))

        normalized_extracted = {_normalize_invoice_number(x) for x in extracted_invoices if x}

        # Нормализованное имя контрагента для нечёткого поиска
        counterparty_norm = (tx.counterparty_name or "").lower().strip()

        def score_income(inc: Income) -> tuple[int, float, int]:
            score_inv = 1
            if normalized_extracted:
                inv_norm = _normalize_invoice_number(inc.invoice_number)
                if inv_norm in normalized_extracted:
                    score_inv = 0

            remaining = float(inc.amount_rsd) - float(inc.paid_amount or 0)
            amount_diff = abs(remaining - float(tx.amount))
            date_diff = abs((tx.date - inc.issued_date).days)

            return (score_inv, amount_diff, date_diff)

        def matches_counterparty(inc: Income) -> bool:
            """Проверяет совпадение контрагента по имени клиента.
            Использует client_name (свободный текст) или client.name (из справочника)."""
            if not counterparty_norm:
                return False
            # Берём имя из поля или из связанного клиента
            raw_name = inc.client_name or (inc.client.name if inc.client else "")
            client_norm = raw_name.lower().strip()
            if not client_norm:
                return False
            # Первые слова банковского контрагента vs. клиента
            cp_words = counterparty_norm.split()[:4]
            cl_words = client_norm.split()[:4]
            common = sum(1 for w in cp_words if any(w == cw or w in cw or cw in w for cw in cl_words))
            return common >= 2 or client_norm in counterparty_norm or counterparty_norm in client_norm

        # 1. Находим топ-5 scored кандидатов (по сумме + номеру)
        valid_incomes = []
        counterparty_incomes = []

        for inc in incomes:
            sc = score_income(inc)
            is_cp_match = matches_counterparty(inc)

            # Добавляем в scored если хорошее совпадение
            if sc[0] == 0 or sc[1] <= 0.5:
                if not (sc[0] == 1 and sc[2] > 60):
                    valid_incomes.append((sc, inc))
            
            # Добавляем в список по контрагенту
            if is_cp_match:
                counterparty_incomes.append((sc, inc))

        valid_incomes.sort(key=lambda x: x[0])

        scored_ids = set()
        for sc, inc in valid_incomes[:5]:
            paid = float(inc.paid_amount or 0)
            remaining = float(inc.amount_rsd) - paid
            desc = f"Счёт {inc.invoice_number}"
            if inc.status == "partial":
                desc += f" — остаток {remaining:,.0f} RSD"
            result.append({
                "id": inc.id,
                "type": "income",
                "description": desc,
                "amount": remaining,
                "amount_full": float(inc.amount_rsd),
                "amount_paid": paid,
                "date": inc.issued_date,
                "score": 100 if sc[0] == 0 else max(10, 90 - sc[2]),
                "section": "suggested",
            })
            scored_ids.add(inc.id)

        # 2. Добавляем остальные фактуры контрагента (не попавшие в топ)
        counterparty_incomes.sort(key=lambda x: x[0][2])  # по дате
        for sc, inc in counterparty_incomes:
            if inc.id in scored_ids:
                continue  # уже в топ
            paid = float(inc.paid_amount or 0)
            remaining = float(inc.amount_rsd) - paid
            desc = f"Счёт {inc.invoice_number}"
            if inc.status == "partial":
                desc += f" — остаток {remaining:,.0f} RSD"
            result.append({
                "id": inc.id,
                "type": "income",
                "description": desc,
                "amount": remaining,
                "amount_full": float(inc.amount_rsd),
                "amount_paid": paid,
                "date": inc.issued_date,
                "score": None,
                "section": "counterparty",
            })

    elif tx.direction == "out":
        pass

    return result


async def match_transaction(db: AsyncSession, tx_id: int, match_type: str, match_id: int):
    """Связать BankTransaction с сущностью. Поддерживает частичную оплату фактур."""
    r = await db.execute(select(BankTransaction).where(BankTransaction.id == tx_id))
    tx = r.scalar_one_or_none()
    
    if not tx:
        raise ValueError("BankTransaction не найдена")
    if tx.status != "unmatched":
        raise ValueError("Транзакция уже сопоставлена или проигнорирована")

    if match_type == "income":
        r_inc = await db.execute(select(Income).where(Income.id == match_id))
        inc = r_inc.scalar_one_or_none()
        if not inc:
            raise ValueError("Income не найден")
        
        # Суммируем уже полученные платежи
        new_paid = float(inc.paid_amount or 0) + float(tx.amount)
        inc.paid_amount = new_paid
        
        if new_paid >= float(inc.amount_rsd):
            # Полностью оплачен
            inc.status = "paid"
            inc.is_paid = True
            inc.paid_date = tx.date
        else:
            # Частичная оплата
            inc.status = "partial"
            inc.is_paid = False
            # paid_date не устанавливаем — не полностью оплачено
            
        if tx.bank_reference and not inc.bank_reference:
            inc.bank_reference = tx.bank_reference
            
        tx.project_id = getattr(inc, "project_id", None)
            
    elif match_type == "expense":
        r_exp = await db.execute(select(Expense).where(Expense.id == match_id))
        exp = r_exp.scalar_one_or_none()
        if not exp:
            raise ValueError("Expense не найден")
            
        exp.status = "paid"
        exp.paid_date = tx.date

        tx.project_id = getattr(exp, "project_id", None)
        
    elif match_type == "obligation":
        r_ob = await db.execute(select(MonthlyObligation).where(MonthlyObligation.id == match_id))
        ob = r_ob.scalar_one_or_none()
        if not ob:
            raise ValueError("MonthlyObligation не найдено")
            
        ob.status = "paid"
        ob.paid_date = tx.date
        
    else:
        raise ValueError("Неизвестный тип сопоставления")

    tx.status = "matched"
    tx.matched_type = match_type
    tx.matched_id = match_id
    
    await db.flush()
    return tx


async def unmatch_transaction(db: AsyncSession, tx_id: int):
    """Отменить связь BankTransaction. При частичной оплате вычитает сумму транзакции."""
    r = await db.execute(select(BankTransaction).where(BankTransaction.id == tx_id))
    tx = r.scalar_one_or_none()
    
    if not tx:
        raise ValueError("BankTransaction не найдена")
    if tx.status != "matched" or not tx.matched_type or not tx.matched_id:
        raise ValueError("Транзакция не сопоставлена")

    if tx.matched_type == "income":
        r_inc = await db.execute(select(Income).where(Income.id == tx.matched_id))
        inc = r_inc.scalar_one_or_none()
        if inc:
            # Вычитаем сумму этой транзакции из суммы оплат
            new_paid = max(0.0, float(inc.paid_amount or 0) - float(tx.amount))
            inc.paid_amount = new_paid
            
            if new_paid <= 0:
                inc.status = "issued"
                inc.is_paid = False
                inc.paid_date = None
            else:
                # Ещё есть другие платежи — статус partial
                inc.status = "partial"
                inc.is_paid = False
                inc.paid_date = None
            
    elif tx.matched_type == "expense":
        r_exp = await db.execute(select(Expense).where(Expense.id == tx.matched_id))
        exp = r_exp.scalar_one_or_none()
        if exp:
            exp.status = "planned"
            exp.paid_date = None
            
    elif tx.matched_type == "obligation":
        r_ob = await db.execute(select(MonthlyObligation).where(MonthlyObligation.id == tx.matched_id))
        ob = r_ob.scalar_one_or_none()
        if ob:
            ob.status = "unpaid"
            ob.paid_date = None
            if ob.deadline < date.today():
                ob.status = "overdue"

    tx.status = "unmatched"
    tx.matched_type = None
    tx.matched_id = None
    tx.project_id = None
    
    await db.flush()
    return tx
