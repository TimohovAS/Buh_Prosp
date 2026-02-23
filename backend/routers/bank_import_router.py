"""Импорт доходов и расходов из банковских изводов."""
from datetime import date, timedelta
from typing import Optional, Any
import hashlib

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import Income, Expense, User, CashTransaction, MonthlyObligation, BankImportFile
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
    file_hash: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    transaction_count: Optional[int] = None


async def _recent_files(db: AsyncSession, limit: int = 10) -> list[dict[str, Any]]:
    r = await db.execute(
        select(BankImportFile).order_by(BankImportFile.imported_at.desc()).limit(limit)
    )
    items = r.scalars().all()
    user_map: dict[int, str] = {}
    user_ids = [x.imported_by for x in items if x.imported_by is not None]
    if user_ids:
        r_users = await db.execute(select(User.id, User.username).where(User.id.in_(user_ids)))
        user_map = {int(row[0]): str(row[1]) for row in r_users.fetchall()}
    return [
        {
            "id": x.id,
            "file_name": x.file_name,
            "file_hash": x.file_hash,
            "file_size": x.file_size,
            "transaction_count": x.transaction_count,
            "created_income": x.created_income,
            "created_expense": x.created_expense,
            "errors_count": x.errors_count,
            "imported_by": user_map.get(x.imported_by) if x.imported_by else None,
            "imported_at": x.imported_at.isoformat() if x.imported_at else None,
        }
        for x in items
    ]


@router.get("/files")
async def list_recent_import_files(
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Последние импортированные файлы выписок."""
    safe_limit = max(1, min(int(limit or 10), 50))
    return {"items": await _recent_files(db, safe_limit)}


@router.post("/parse")
async def parse_izvod(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Разобрать файл извода (.xls). Возвращает список транзакций."""
    if not file.filename or not file.filename.lower().endswith((".xls", ".xlsx")):
        raise HTTPException(400, "Нужен файл .xls или .xlsx")
    content = await file.read()
    file_hash = hashlib.sha256(content).hexdigest()
    try:
        transactions = parse_izvod_xls(content)
    except Exception as e:
        raise HTTPException(400, f"Ошибка чтения файла: {e}")
    r = await db.execute(select(BankImportFile).where(BankImportFile.file_hash == file_hash))
    existing = r.scalar_one_or_none()
    existing_data = None
    if existing:
        username = None
        if existing.imported_by:
            r_user = await db.execute(select(User.username).where(User.id == existing.imported_by))
            username = r_user.scalar_one_or_none()
        existing_data = {
            "id": existing.id,
            "file_name": existing.file_name,
            "file_hash": existing.file_hash,
            "transaction_count": existing.transaction_count,
            "created_income": existing.created_income,
            "created_expense": existing.created_expense,
            "errors_count": existing.errors_count,
            "imported_by": username,
            "imported_at": existing.imported_at.isoformat() if existing.imported_at else None,
        }
    return {
        "transactions": transactions,
        "file_name": file.filename,
        "file_hash": file_hash,
        "already_imported": existing is not None,
        "imported_file": existing_data,
        "recent_files": await _recent_files(db, 10),
    }


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
    if body.file_hash:
        r_file = await db.execute(select(BankImportFile).where(BankImportFile.file_hash == body.file_hash))
        existing = r_file.scalar_one_or_none()
        if existing:
            raise HTTPException(
                409,
                f"Файл уже был импортирован: {existing.file_name} ({existing.imported_at.date() if existing.imported_at else 'unknown'})",
            )

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

    if body.file_hash:
        file_entry = BankImportFile(
            file_name=(body.file_name or "unknown").strip() or "unknown",
            file_hash=body.file_hash,
            file_size=body.file_size,
            transaction_count=body.transaction_count if body.transaction_count is not None else len(transactions),
            created_income=created_income,
            created_expense=created_expense,
            errors_count=len(errors),
            imported_by=current_user.id,
        )
        db.add(file_entry)
        await db.flush()

    return {
        "created_income": created_income,
        "created_expense": created_expense,
        "errors": errors,
        "recent_files": await _recent_files(db, 10),
    }
