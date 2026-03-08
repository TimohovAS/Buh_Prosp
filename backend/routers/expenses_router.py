"""Р РѕСѓС‚РµСЂ СЂР°СЃС…РѕРґРѕРІ."""
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import Expense, User, Project
from backend.schemas import ExpenseCreate, ExpenseUpdate, ExpenseResponse, ExpenseReverseRequest, BulkAssignProject
from backend.auth import get_current_user_required, require_edit_access
from backend.services import create_expense_reversal

router = APIRouter(prefix="/expenses", tags=["expenses"])

async def _get_unassigned_project_id(db: AsyncSession) -> int | None:
    r = await db.execute(select(Project).where(Project.code == "INT-UNASSIGNED"))
    p = r.scalar_one_or_none()
    return p.id if p else None


@router.get("", response_model=list[ExpenseResponse])
async def list_expenses(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    category_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """РЎРїРёСЃРѕРє СЂР°СЃС…РѕРґРѕРІ СЃ С„РёР»СЊС‚СЂР°С†РёРµР№."""
    q = select(Expense).order_by(Expense.date.desc(), Expense.id.desc())
    if year:
        q = q.where(Expense.date >= date(year, 1, 1), Expense.date <= date(year, 12, 31))
    if month and year:
        import calendar
        last = calendar.monthrange(year, month)[1]
        q = q.where(Expense.date >= date(year, month, 1), Expense.date <= date(year, month, last))
    if category:
        q = q.where(Expense.category == category)
    if category_id:
        q = q.where(Expense.category_id == category_id)
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    items = result.scalars().all()
    return [ExpenseResponse.model_validate(i) for i in items]


@router.post("", response_model=ExpenseResponse)
async def create_expense(
    data: ExpenseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Р”РѕР±Р°РІРёС‚СЊ СЂР°СЃС…РѕРґ."""
    project_id = data.project_id
    if not project_id:
        project_id = await _get_unassigned_project_id(db)
    expense = Expense(
        date=data.date,
        description=data.description,
        amount=data.amount,
        currency=data.currency,
        category=data.category,
        category_id=data.category_id,
        note=data.note,
        paid_date=data.paid_date or data.date,
        project_id=project_id,
        source="manual",
        created_by=current_user.id,
    )
    db.add(expense)
    await db.commit()
    await db.refresh(expense)
    return ExpenseResponse.model_validate(expense)


@router.post("/bulk-assign-project")
async def bulk_assign_project_expenses(
    data: BulkAssignProject,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """РњР°СЃСЃРѕРІРѕРµ РЅР°Р·РЅР°С‡РµРЅРёРµ РїСЂРѕРµРєС‚Р° СЂР°СЃС…РѕРґР°Рј. project_id=null в†’ INT-UNASSIGNED."""
    if not data.ids:
        return {"updated": 0}
    pid = data.project_id
    if pid is None:
        pid = await _get_unassigned_project_id(db)
    if pid is not None:
        r = await db.execute(select(Project).where(Project.id == pid))
        proj = r.scalar_one_or_none()
        if not proj:
            raise HTTPException(404, "РџСЂРѕРµРєС‚ РЅРµ РЅР°Р№РґРµРЅ")
        if proj.status == "archived":
            raise HTTPException(400, "РќРµР»СЊР·СЏ РЅР°Р·РЅР°С‡РёС‚СЊ Р°СЂС…РёРІРёСЂРѕРІР°РЅРЅС‹Р№ РїСЂРѕРµРєС‚")
    r = await db.execute(select(Expense).where(Expense.id.in_(data.ids)))
    items = r.scalars().all()
    for item in items:
        item.project_id = pid
    await db.commit()
    return {"updated": len(items)}


@router.get("/totals/summary")
async def get_expense_totals(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """РЎСѓРјРјС‹ СЂР°СЃС…РѕРґРѕРІ Р·Р° РіРѕРґ Рё РјРµСЃСЏС†."""
    today = date.today()
    y = year or today.year
    m = month or today.month

    r_year = await db.execute(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.date >= date(y, 1, 1),
            Expense.date <= date(y, 12, 31),
        )
    )
    year_total = float(r_year.scalar() or 0)

    import calendar
    last_day = calendar.monthrange(y, m)[1]
    r_month = await db.execute(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.date >= date(y, m, 1),
            Expense.date <= date(y, m, last_day),
        )
    )
    month_total = float(r_month.scalar() or 0)

    return {"year_expenses": year_total, "month_expenses": month_total}


@router.get("/{expense_id}", response_model=ExpenseResponse)
async def get_expense(
    expense_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """РџРѕР»СѓС‡РёС‚СЊ СЂР°СЃС…РѕРґ."""
    r = await db.execute(select(Expense).where(Expense.id == expense_id))
    expense = r.scalar_one_or_none()
    if not expense:
        raise HTTPException(404, "Р Р°СЃС…РѕРґ РЅРµ РЅР°Р№РґРµРЅ")
    return ExpenseResponse.model_validate(expense)


@router.patch("/{expense_id}/reverse", response_model=ExpenseResponse)
async def reverse_expense(
    expense_id: int,
    data: ExpenseReverseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """РЎС‚РѕСЂРЅРѕ СЂР°СЃС…РѕРґР°. РЎРѕР·РґР°С‘С‚СЃСЏ Р·Р°РїРёСЃСЊ СЃ amount=-original, РѕСЂРёРіРёРЅР°Р» РѕСЃС‚Р°С‘С‚СЃСЏ paid."""
    r = await db.execute(select(Expense).where(Expense.id == expense_id))
    expense = r.scalar_one_or_none()
    if not expense:
        raise HTTPException(404, "Р Р°СЃС…РѕРґ РЅРµ РЅР°Р№РґРµРЅ")
    if getattr(expense, "status", "paid") == "reversed":
        raise HTTPException(400, "Р Р°СЃС…РѕРґ СѓР¶Рµ СЃС‚РѕСЂРЅРёСЂРѕРІР°РЅ")
    if getattr(expense, "reversed_expense_id", None):
        raise HTTPException(400, "Р Р°СЃС…РѕРґ СѓР¶Рµ СЃС‚РѕСЂРЅРёСЂРѕРІР°РЅ")
    reverse_date = data.date if data.date else None
    reversal = await create_expense_reversal(
        db, expense,
        reverse_date=reverse_date,
        comment=data.comment,
        source="manual",
        created_by=current_user.id,
    )
    await db.commit()
    return ExpenseResponse.model_validate(reversal)


@router.patch("/{expense_id}", response_model=ExpenseResponse)
async def update_expense(
    expense_id: int,
    data: ExpenseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """РћР±РЅРѕРІРёС‚СЊ СЂР°СЃС…РѕРґ."""
    r = await db.execute(select(Expense).where(Expense.id == expense_id))
    expense = r.scalar_one_or_none()
    if not expense:
        raise HTTPException(404, "Р Р°СЃС…РѕРґ РЅРµ РЅР°Р№РґРµРЅ")
    dump = data.model_dump(exclude_unset=True)
    if "project_id" in dump and not dump["project_id"]:
        dump["project_id"] = await _get_unassigned_project_id(db)
    for k, v in dump.items():
        setattr(expense, k, v)
    await db.flush()
    await db.commit()
    await db.refresh(expense)
    return ExpenseResponse.model_validate(expense)


@router.delete("/{expense_id}")
async def delete_expense(
    expense_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """РЎС‚РѕСЂРЅРѕ СЂР°СЃС…РѕРґР° РІРјРµСЃС‚Рѕ СѓРґР°Р»РµРЅРёСЏ (РЅРёРєРѕРіРґР° РЅРµ СѓРґР°Р»СЏРµРј С„РёР·РёС‡РµСЃРєРё)."""
    r = await db.execute(select(Expense).where(Expense.id == expense_id))
    expense = r.scalar_one_or_none()
    if not expense:
        raise HTTPException(404, "Р Р°СЃС…РѕРґ РЅРµ РЅР°Р№РґРµРЅ")
    if getattr(expense, "status", "paid") == "reversed" or getattr(expense, "reversed_expense_id", None):
        raise HTTPException(400, "Р Р°СЃС…РѕРґ СѓР¶Рµ СЃС‚РѕСЂРЅРёСЂРѕРІР°РЅ")
    source = getattr(expense, "source", None) or "manual"
    reversal = await create_expense_reversal(
        db, expense,
        source=source,
        created_by=current_user.id,
    )
    await db.commit()
    return {"ok": True, "reversal_id": reversal.id}
