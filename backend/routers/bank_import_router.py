"""Импорт доходов и расходов из банковских изводов."""
from datetime import date, timedelta
from typing import Optional, Any
import hashlib
import re

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


def _normalize_invoice_number(value: Optional[str]) -> str:
    if not value:
        return ""
    s = re.sub(r"\s+", "", str(value).strip().upper())
    m_year_first = re.fullmatch(r"(20\d{2})-(\d{1,10})", s)
    if m_year_first:
        return f"{m_year_first.group(1)}:{int(m_year_first.group(2))}"
    m_num_first = re.fullmatch(r"(\d{1,10})-(20\d{2})", s)
    if m_num_first:
        return f"{m_num_first.group(2)}:{int(m_num_first.group(1))}"
    return s


def _to_number_year_format(value: Optional[str], fallback_year: Optional[int]) -> str:
    s = re.sub(r"\s+", "", str(value or "").strip().upper())
    m_year_first = re.fullmatch(r"(20\d{2})-(\d{1,10})", s)
    if m_year_first:
        return f"{int(m_year_first.group(2)):04d}-{m_year_first.group(1)}"
    m_num_first = re.fullmatch(r"(\d{1,10})-(20\d{2})", s)
    if m_num_first:
        return f"{int(m_num_first.group(1)):04d}-{m_num_first.group(2)}"
    if fallback_year is not None and s.isdigit():
        return f"{int(s):04d}-{fallback_year}"
    return s


def _extract_invoice_candidates(*parts: Optional[str]) -> list[str]:
    """
    Достаём возможные номера фактур из текста назначения/референции.
    Поддерживаем оба частых формата: YYYY-NNNN и NNN-YYYY.
    """
    text = " ".join([str(p or "") for p in parts]).upper()
    patterns = [
        r"\b20\d{2}-\d{1,6}\b",   # 2026-0008
        r"\b\d{1,6}-20\d{2}\b",   # 008-2026
    ]
    out: list[str] = []
    seen: set[str] = set()
    for pat in patterns:
        for m in re.findall(pat, text):
            v = m.strip()
            if v and v not in seen:
                seen.add(v)
                out.append(v)
    return out


async def _find_unpaid_income_match(
    db: AsyncSession,
    item: ApplyItem,
    tx_date: date,
    amount: float,
    payer: str,
    description: str,
    ref: str,
) -> tuple[Optional[Income], Optional[str]]:
    """
    Пытаемся сопоставить банковский платёж с уже существующей неоплаченной фактурой.
    reason:
      - "invoice" — надёжно по номеру фактуры
      - "invoice-ambiguous" — найдено несколько кандидатов по номеру (нужно уточнение)
      - "client+amount" — слабое совпадение (клиент+сумма), нужно уточнение
    """
    base_filters = [
        Income.status != "cancelled",
        Income.paid_date.is_(None),
    ]
    if item.client_id:
        base_filters.append(Income.client_id == item.client_id)

    invoice_candidates: list[str] = []
    if item.invoice_number:
        invoice_candidates.append(item.invoice_number.strip())
    invoice_candidates.extend(_extract_invoice_candidates(description, ref))
    # Убираем дубликаты при сохранении порядка.
    deduped: list[str] = []
    seen_norm: set[str] = set()
    for inv in invoice_candidates:
        n = _normalize_invoice_number(inv)
        if n and n not in seen_norm:
            seen_norm.add(n)
            deduped.append(inv)

    if deduped:
        normalized = [_normalize_invoice_number(x) for x in deduped]
        normalized_set = set(normalized)
        r = await db.execute(
            select(Income).where(*base_filters)
        )
        rows = [
            inc for inc in r.scalars().all()
            if _normalize_invoice_number(inc.invoice_number) in normalized_set
        ]
        if rows:
            # Если совпадений несколько — сортируем кандидатов, но не считаем это
            # автоматически безопасным действием (в apply вернём запрос на уточнение).
            def rank(inc: Income):
                inv_norm = _normalize_invoice_number(inc.invoice_number)
                idx = normalized.index(inv_norm) if inv_norm in normalized else 999
                amount_diff = abs(float(inc.amount_rsd) - float(amount))
                date_diff = abs((tx_date - inc.issued_date).days)
                return (idx, amount_diff, date_diff, -inc.id)

            rows = sorted(rows, key=rank)
            if len(rows) == 1:
                return rows[0], "invoice"
            return rows[0], "invoice-ambiguous"

    # Осторожный fallback: по клиенту+сумме, только если найден ровно один кандидат.
    if item.client_id:
        r = await db.execute(
            select(Income).where(*base_filters, Income.client_id == item.client_id)
        )
        rows = [
            inc
            for inc in r.scalars().all()
            if abs(float(inc.amount_rsd) - float(amount)) <= 0.5
            and inc.issued_date <= tx_date
            and (tx_date - inc.issued_date).days <= 365
        ]
        if len(rows) == 1:
            return rows[0], "client+amount"

    return None, None


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
    matched_income_paid = 0
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
                income_by_ref = r.scalar_one_or_none()
                if income_by_ref and (income_by_ref.paid_date is not None or income_by_ref.status == "paid"):
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
            matched_income = None
            match_reason: Optional[str] = None

            # 1) Если есть референция и по ней уже есть неоплаченный income — закрываем его.
            if ref:
                r_ref = await db.execute(
                    select(Income).where(
                        Income.bank_reference == ref,
                        Income.status != "cancelled",
                        Income.paid_date.is_(None),
                    )
                )
                ref_candidates = r_ref.scalars().all()
                if len(ref_candidates) > 1:
                    errors.append(
                        f"Строка {i + 1}: по референции {ref} найдено несколько неоплаченных фактур. Уточните вручную перед импортом."
                    )
                    continue
                if len(ref_candidates) == 1:
                    matched_income = ref_candidates[0]
                    match_reason = "reference"

            # 2) Иначе пробуем сопоставить по номеру фактуры/клиенту+сумме.
            if matched_income is None:
                matched_income, match_reason = await _find_unpaid_income_match(
                    db=db,
                    item=item,
                    tx_date=d,
                    amount=float(amount),
                    payer=payer,
                    description=description,
                    ref=ref,
                )

            if matched_income is not None:
                if match_reason == "invoice-ambiguous":
                    errors.append(
                        f"Строка {i + 1}: найдено несколько кандидатов фактуры ({matched_income.invoice_number}) по номеру. Уточните вручную перед импортом."
                    )
                    continue
                if match_reason == "client+amount":
                    errors.append(
                        f"Строка {i + 1}: найдено вероятное совпадение по клиенту и сумме ({matched_income.invoice_number}). Для безопасности уточните вручную перед импортом."
                    )
                    continue
                matched_income.status = "paid"
                matched_income.paid_date = d
                matched_income.is_paid = True
                if ref and not matched_income.bank_reference:
                    matched_income.bank_reference = ref
                if item.client_id and not matched_income.client_id:
                    matched_income.client_id = item.client_id
                if payer and not matched_income.client_name:
                    matched_income.client_name = payer

                r_ct = await db.execute(
                    select(CashTransaction).where(
                        CashTransaction.source == "invoice",
                        CashTransaction.reference_id == matched_income.id,
                    )
                )
                existing_ct = r_ct.scalar_one_or_none()
                if existing_ct:
                    existing_ct.amount = float(amount)
                    existing_ct.date = d
                else:
                    db.add(
                        CashTransaction(
                            type="income",
                            source="invoice",
                            reference_id=matched_income.id,
                            amount=float(amount),
                            date=d,
                        )
                    )
                matched_income_paid += 1
            else:
                invoice_number = _to_number_year_format(item.invoice_number, d.year) if item.invoice_number else None
                invoice_year_val = d.year
                if not invoice_number:
                    next_n = await allocate_next_invoice_number(db, d.year)
                    invoice_number = f"{next_n:04d}-{d.year}"
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
        "matched_income_paid": matched_income_paid,
        "created_expense": created_expense,
        "errors": errors,
        "recent_files": await _recent_files(db, 10),
    }
