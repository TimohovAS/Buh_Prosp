"""Импорт доходов и расходов из банковских изводов."""
from datetime import date, timedelta
from typing import Optional, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import Income, Expense, User, CashTransaction, MonthlyObligation
from backend.auth import get_current_user_required, require_edit_access
from backend.services import allocate_next_invoice_number
from backend.bank_parser import parse_izvod_xls

router = APIRouter(prefix="/bank-import", tags=["bank-import"])


class ApplyItem(BaseModel):
    type: str  # income | expense
    tx: dict[str, Any]
    client_id: Optional[int] = None
    invoice_number: Optional[str] = None


class ApplyRequest(BaseModel):
    transactions: list[ApplyItem]


@router.post("/parse")
async def parse_izvod(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user_required),
):
    """Разобрать файл извода (.xls). Возвращает список транзакций."""
    if not file.filename or not file.filename.lower().endswith((".xls", ".xlsx")):
        raise HTTPException(400, "Нужен файл .xls или .xlsx")
    content = await file.read()
    try:
        transactions = parse_izvod_xls(content)
    except Exception as e:
        raise HTTPException(400, f"Ошибка чтения файла: {e}")
    return {"transactions": transactions}


@router.post("/apply")
async def apply_import(
    body: ApplyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """
    Создать доходы и расходы из выбранных транзакций.
    Формат: [{"type": "income"|"expense", "tx": {...}, "client_id": null, "invoice_number": null}]
    """
    created_income = 0
    created_expense = 0
    errors = []
    transactions = body.transactions

    for i, item in enumerate(transactions):
        tx = item.tx
        tx_type = item.type
        if not tx_type or tx_type not in ("income", "expense"):
            errors.append(f"Строка {i + 1}: неверный тип")
            continue

        ref = tx.get("reference") or ""
        date_str = tx.get("date")
        amount = tx.get("amount") or 0
        description = (tx.get("description") or "")[:500]
        payer = (tx.get("payer_beneficiary") or "")[:200]

        if not date_str or amount <= 0:
            errors.append(f"Строка {i + 1}: неверные дата или сумма")
            continue

        try:
            d = date.fromisoformat(date_str)
        except ValueError:
            errors.append(f"Строка {i + 1}: неверный формат даты")
            continue

        # Проверка дубликата по bank_reference
        if ref:
            if tx_type == "income":
                r = await db.execute(select(Income).where(Income.bank_reference == ref))
                if r.scalar_one_or_none():
                    errors.append(f"Строка {i + 1}: доход с референцией {ref} уже импортирован")
                    continue
            else:
                r = await db.execute(select(Expense).where(Expense.bank_reference == ref))
                if r.scalar_one_or_none():
                    errors.append(f"Строка {i + 1}: расход с референцией {ref} уже импортирован")
                    continue
                # Коллизия: платёж уже учтён вручную по номеру платёжного поручения (ID transakcije)
                r_ob = await db.execute(select(MonthlyObligation).where(MonthlyObligation.payment_reference == ref))
                if r_ob.scalar_one_or_none():
                    errors.append(f"Строка {i + 1}: расход с номером платёжного поручения {ref} уже учтён в обязательствах")
                    continue

        if tx_type == "income":
            invoice_number = item.invoice_number
            invoice_year_val = d.year
            if not invoice_number:
                next_n = await allocate_next_invoice_number(db, d.year)
                invoice_number = f"{d.year}-{next_n:04d}"
            income = Income(
                issued_date=d,
                invoice_number=invoice_number,
                invoice_year=invoice_year_val,
                client_id=item.client_id,
                client_name=payer or None,
                description=description or f"Банк: {payer}",
                amount_rsd=amount,
                bank_reference=ref or None,
                status="paid" if amount else "issued",
                paid_date=d if amount else None,
                is_paid=bool(amount),
                created_by=current_user.id,
            )
            db.add(income)
            await db.flush()  # чтобы получить income.id
            if amount:
                ct = CashTransaction(
                    type="income",
                    source="invoice",
                    reference_id=income.id,
                    amount=float(amount),
                    date=d,
                )
                db.add(ct)
            created_income += 1
        else:
            expense = Expense(
                date=d,
                description=description or f"Банк: {payer}",
                amount=amount,
                bank_reference=ref or None,
                paid_date=d,
                source="bank_import",
                created_by=current_user.id,
            )
            db.add(expense)
            await db.flush()
            created_expense += 1

            # Автосопоставление с MonthlyObligation
            date_min = d - timedelta(days=45)
            date_max = d + timedelta(days=45)
            r_ob = await db.execute(
                select(MonthlyObligation).where(
                    MonthlyObligation.status.in_(["unpaid", "overdue"]),
                    MonthlyObligation.deadline >= date_min,
                    MonthlyObligation.deadline <= date_max,
                )
            )
            candidates = [ob for ob in r_ob.scalars().all() if abs(ob.amount - float(amount)) <= 0.5]

            # При нескольких кандидатах (одинаковая сумма по месяцам) берём обязательство
            # с дедлайном, ближайшим к дате платежа (платим за ближайший к оплате срок)
            ob = None
            if len(candidates) == 1:
                ob = candidates[0]
            elif len(candidates) > 1:
                ob = min(candidates, key=lambda x: abs((x.deadline - d).days))

            if ob is not None:
                ob.status = "paid"
                ob.paid_date = d
                ob.payment_reference = ref or None
                ob.payment_method = "bank_import"
                ob.expense_id = expense.id
                expense.category = "tax"
                expense.is_tax_related = True
                expense.source = "obligation"

    await db.flush()

    return {
        "created_income": created_income,
        "created_expense": created_expense,
        "errors": errors,
    }
