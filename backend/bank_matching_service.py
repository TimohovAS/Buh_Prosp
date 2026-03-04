"""Модуль сопоставления банковских транзакций с документами системы (invoices, expenses, obligations)."""
from datetime import date
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import BankTransaction, Income, Expense, MonthlyObligation
from backend.services import _normalize_invoice_number, _extract_invoice_candidates


async def suggest_matches(db: AsyncSession, tx: BankTransaction) -> list[dict]:
    """Вернуть до 5 подходящих кандидатов для сопоставления с банковской транзакцией."""
    if tx.status != "unmatched":
        return []

    candidates = []

    if tx.direction == "in":
        # Ищем Income (счета), которые не оплачены или оплачены частично
        q = select(Income).where(
            Income.status != "cancelled",
            Income.status != "paid",   # полностью оплаченные пропускаем
        )
        r = await db.execute(q)
        incomes = r.scalars().all()

        extracted_invoices = []
        if tx.purpose:
            extracted_invoices.extend(_extract_invoice_candidates(tx.purpose))
        if tx.bank_reference:
            extracted_invoices.extend(_extract_invoice_candidates(tx.bank_reference))
        
        normalized_extracted = {_normalize_invoice_number(x) for x in extracted_invoices if x}

        def score_income(inc: Income) -> tuple[int, float, int]:
            score_inv = 1
            if normalized_extracted:
                inv_norm = _normalize_invoice_number(inc.invoice_number)
                if inv_norm in normalized_extracted:
                    score_inv = 0
            
            # Остаток для доплаты
            remaining = float(inc.amount_rsd) - float(inc.paid_amount or 0)
            amount_diff = abs(remaining - float(tx.amount))
            date_diff = abs((tx.date - inc.issued_date).days)
            
            return (score_inv, amount_diff, date_diff)

        valid_incomes = []
        for inc in incomes:
            sc = score_income(inc)
            if sc[0] == 0 or sc[1] <= 0.5:
                if sc[0] == 1 and sc[2] > 60:
                    continue
                valid_incomes.append((sc, inc))
        
        valid_incomes.sort(key=lambda x: x[0])
        
        for sc, inc in valid_incomes[:5]:
            paid = float(inc.paid_amount or 0)
            remaining = float(inc.amount_rsd) - paid
            is_partial = inc.status == "partial"
            desc = f"Счёт {inc.invoice_number} ({inc.client_name or 'Без клиента'})"
            if is_partial:
                desc += f" — остаток {remaining:,.0f} RSD"
            candidates.append({
                "type": "income",
                "id": inc.id,
                "description": desc,
                "amount": remaining,  # показываем остаток
                "amount_full": inc.amount_rsd,
                "amount_paid": paid,
                "date": inc.issued_date,
                "score": sc
            })
            
    elif tx.direction == "out":
        # TODO: Логика для расходов и налогов (MonthlyObligation). 
        pass

    return [
        {
            "id": c["id"],
            "type": c["type"],
            "description": c["description"],
            "amount": c["amount"],
            "amount_full": c.get("amount_full"),
            "amount_paid": c.get("amount_paid"),
            "date": c["date"],
            "score": 100 if c["score"][0] == 0 else max(10, 90 - c["score"][2])
        } for c in candidates
    ]


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
