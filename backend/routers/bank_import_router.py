"""Импорт банковских изводов в BankTransaction."""
from datetime import date
from typing import Optional, Any
import hashlib

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import User, BankImportFile, BankTransaction
from backend.auth import get_current_user_required, require_edit_access
from backend.bank_parser import parse_izvod_xls

router = APIRouter(prefix="/bank-import", tags=["bank-import"])


class ApplyItem(BaseModel):
    type: str  # income | expense
    tx: dict[str, Any]
    file_hash: Optional[str] = None


class ImportFileMeta(BaseModel):
    file_hash: str
    file_name: str
    file_size: int
    transaction_count: int


class ApplyRequest(BaseModel):
    transactions: list[ApplyItem]
    files: list[ImportFileMeta] = []


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


@router.get("/files/all")
async def list_all_import_files(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Все импортированные файлы с флагом ghost (created=0 but tx_count>0)."""
    from sqlalchemy import select as _select
    r = await db.execute(_select(BankImportFile).order_by(BankImportFile.id))
    items = r.scalars().all()
    result = []
    for f in items:
        created = (f.created_income or 0) + (f.created_expense or 0)
        is_ghost = created == 0 and (f.transaction_count or 0) > 0
        result.append({
            "id": f.id,
            "file_name": f.file_name,
            "file_hash": f.file_hash,
            "transaction_count": f.transaction_count,
            "created_income": f.created_income,
            "created_expense": f.created_expense,
            "imported_at": f.imported_at.isoformat() if f.imported_at else None,
            "is_ghost": is_ghost,
        })
    return {"items": result, "total": len(result)}


@router.delete("/files/{file_id}")
async def delete_import_file_record(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Удалить запись об импорте файла (чтобы можно было переимпортировать)."""
    from sqlalchemy import delete as _delete
    r = await db.execute(_select(BankImportFile).where(BankImportFile.id == file_id))
    rec = r.scalar_one_or_none()
    if not rec:
        raise HTTPException(404, "Запись не найдена")
    created = (rec.created_income or 0) + (rec.created_expense or 0)
    await db.execute(_delete(BankImportFile).where(BankImportFile.id == file_id))
    await db.commit()
    return {"deleted": True, "file_name": rec.file_name, "was_ghost": created == 0 and (rec.transaction_count or 0) > 0}



@router.post("/parse")
async def parse_izvod(
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Разобрать файл извода (.xls). Возвращает список транзакций."""
    all_transactions = []
    skipped_files = []
    parsed_files = []
    
    for file in files:
        if not file.filename or not file.filename.lower().endswith((".xls", ".xlsx")):
            skipped_files.append({"file_name": file.filename or "unknown", "reason": "Нужен файл .xls или .xlsx"})
            continue
            
        content = await file.read()
        file_hash = hashlib.sha256(content).hexdigest()
        
        r = await db.execute(select(BankImportFile).where(BankImportFile.file_hash == file_hash))
        existing = r.scalar_one_or_none()
        if existing:
            skipped_files.append({"file_name": file.filename, "reason": "Уже импортирован", "hash": file_hash})
            continue
            
        try:
            transactions = parse_izvod_xls(content)
            for t in transactions:
                t["file_hash"] = file_hash
            all_transactions.extend(transactions)
            parsed_files.append({
                "file_hash": file_hash,
                "file_name": file.filename,
                "file_size": len(content),
                "transaction_count": len(transactions)
            })
        except Exception as e:
            skipped_files.append({"file_name": file.filename, "reason": f"Ошибка чтения: {e}"})
            
    return {
        "transactions": all_transactions,
        "parsed_files": parsed_files,
        "skipped_files": skipped_files,
        "recent_files": await _recent_files(db, 10),
    }


@router.post("/apply")
async def apply_import(
    body: ApplyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """
    Создать BankTransaction из выбранных строк.
    """
    if body.files:
        hashes = [f.file_hash for f in body.files]
        r_files = await db.execute(select(BankImportFile).where(BankImportFile.file_hash.in_(hashes)))
        existing_files = r_files.scalars().all()
        if existing_files:
            names = ", ".join(f.file_name for f in existing_files)
            raise HTTPException(409, f"Файлы уже были импортированы: {names}")

    file_stats = {f.file_hash: {"created_income": 0, "created_expense": 0, "errors_count": 0} for f in body.files}
    created_transactions = 0
    skipped_duplicates = 0
    errors = []
    transactions = body.transactions

    for i, item in enumerate(transactions):
        tx = item.tx
        
        ref = tx.get("reference") or ""
        date_str = tx.get("date")
        amount = tx.get("amount") or 0
        direction = "in" if tx.get("type") == "income" else "out"
        description = (tx.get("description") or "")[:500]
        payer = (tx.get("payer_beneficiary") or "")[:200]
        raw_json = tx.get("raw_json")

        if not date_str or float(amount) <= 0:
            errors.append(f"Строка {i + 1}: неверные дата или сумма")
            if item.file_hash and item.file_hash in file_stats:
                file_stats[item.file_hash]["errors_count"] += 1
            continue

        try:
            d = date.fromisoformat(date_str)
        except ValueError:
            errors.append(f"Строка {i + 1}: неверный формат даты")
            if item.file_hash and item.file_hash in file_stats:
                file_stats[item.file_hash]["errors_count"] += 1
            continue

        is_duplicate = False
        if ref:
            r = await db.execute(select(BankTransaction).where(BankTransaction.bank_reference == ref))
            if r.scalar_one_or_none():
                is_duplicate = True
        else:
            # Дедупликация по дате, сумме, направлению и назначению
            r = await db.execute(select(BankTransaction).where(
                BankTransaction.date == d,
                BankTransaction.amount == float(amount),
                BankTransaction.direction == direction,
                BankTransaction.purpose == description
            ))
            if r.scalar_one_or_none():
                is_duplicate = True

        if is_duplicate:
            skipped_duplicates += 1
            continue

        transaction = BankTransaction(
            date=d,
            amount=float(amount),
            direction=direction,
            counterparty_name=payer or None,
            purpose=description or None,
            bank_reference=ref or None,
            raw_json=raw_json,
            status="unmatched"
        )
        db.add(transaction)
        created_transactions += 1
        if item.file_hash and item.file_hash in file_stats:
            if direction == "in":
                file_stats[item.file_hash]["created_income"] += 1
            else:
                file_stats[item.file_hash]["created_expense"] += 1

    await db.flush()

    for f in body.files:
        stats = file_stats[f.file_hash]
        file_entry = BankImportFile(
            file_name=f.file_name,
            file_hash=f.file_hash,
            file_size=f.file_size,
            transaction_count=f.transaction_count,
            created_income=stats["created_income"],
            created_expense=stats["created_expense"],
            errors_count=stats["errors_count"],
            imported_by=current_user.id,
        )
        db.add(file_entry)

    await db.commit()

    return {
        "created_transactions": created_transactions,
        "skipped_duplicates": skipped_duplicates,
        "errors": errors,
        "recent_files": await _recent_files(db, 10),
    }
