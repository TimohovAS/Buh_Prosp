from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user_required, require_edit_access
from backend.database import get_db
from backend.models import Contract, Expense, Project, User
from backend.schemas import BulkAssignProject, ExpenseCreate, ExpenseResponse, ExpenseReverseRequest, ExpenseUpdate
from backend.services import create_expense_reversal

router = APIRouter(prefix="/expenses", tags=["expenses"])


async def _get_unassigned_project_id(db: AsyncSession) -> int | None:
    result = await db.execute(select(Project).where(Project.code == "INT-UNASSIGNED"))
    project = result.scalar_one_or_none()
    return project.id if project else None


async def _get_project_or_404(db: AsyncSession, project_id: int) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    if project.status == "archived":
        raise HTTPException(400, "Cannot use archived project")
    return project


async def _get_contract_or_404(db: AsyncSession, contract_id: int) -> Contract:
    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(404, "Contract not found")
    return contract


async def _resolve_expense_links(
    db: AsyncSession,
    project_id: int | None,
    contract_id: int | None,
) -> tuple[int | None, int | None]:
    resolved_project_id = project_id or await _get_unassigned_project_id(db)
    resolved_contract_id = contract_id

    if resolved_contract_id is not None:
        contract = await _get_contract_or_404(db, resolved_contract_id)
        if contract.project_id is None:
            raise HTTPException(400, "Contract must be linked to a project before using it in expenses")
        resolved_project_id = contract.project_id

    if resolved_project_id is not None:
        await _get_project_or_404(db, resolved_project_id)

    return resolved_project_id, resolved_contract_id


async def _clear_contract_if_project_mismatch(db: AsyncSession, expense: Expense, project_id: int | None) -> None:
    if not expense.contract_id or project_id is None:
        return
    contract = await _get_contract_or_404(db, expense.contract_id)
    if contract.project_id != project_id:
        expense.contract_id = None


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
    query = select(Expense).order_by(Expense.date.desc(), Expense.id.desc())
    if year:
        query = query.where(Expense.date >= date(year, 1, 1), Expense.date <= date(year, 12, 31))
    if month and year:
        import calendar

        last_day = calendar.monthrange(year, month)[1]
        query = query.where(Expense.date >= date(year, month, 1), Expense.date <= date(year, month, last_day))
    if category:
        query = query.where(Expense.category == category)
    if category_id:
        query = query.where(Expense.category_id == category_id)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()
    return [ExpenseResponse.model_validate(item) for item in items]


@router.post("", response_model=ExpenseResponse)
async def create_expense(
    data: ExpenseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    project_id, contract_id = await _resolve_expense_links(db, data.project_id, data.contract_id)
    expense = Expense(
        date=data.date,
        description=data.description,
        amount=data.amount,
        currency=data.currency,
        category=data.category,
        category_id=data.category_id,
        contract_id=contract_id,
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
    if not data.ids:
        return {"updated": 0}

    project_id = data.project_id
    if project_id is None:
        project_id = await _get_unassigned_project_id(db)
    if project_id is not None:
        await _get_project_or_404(db, project_id)

    result = await db.execute(select(Expense).where(Expense.id.in_(data.ids)))
    items = result.scalars().all()
    for item in items:
        item.project_id = project_id
        await _clear_contract_if_project_mismatch(db, item, project_id)

    await db.commit()
    return {"updated": len(items)}


@router.get("/totals/summary")
async def get_expense_totals(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    today = date.today()
    selected_year = year or today.year
    selected_month = month or today.month

    result_year = await db.execute(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.date >= date(selected_year, 1, 1),
            Expense.date <= date(selected_year, 12, 31),
        )
    )
    year_total = float(result_year.scalar() or 0)

    import calendar

    last_day = calendar.monthrange(selected_year, selected_month)[1]
    result_month = await db.execute(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.date >= date(selected_year, selected_month, 1),
            Expense.date <= date(selected_year, selected_month, last_day),
        )
    )
    month_total = float(result_month.scalar() or 0)

    return {"year_expenses": year_total, "month_expenses": month_total}


@router.get("/{expense_id}", response_model=ExpenseResponse)
async def get_expense(
    expense_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    result = await db.execute(select(Expense).where(Expense.id == expense_id))
    expense = result.scalar_one_or_none()
    if not expense:
        raise HTTPException(404, "Expense not found")
    return ExpenseResponse.model_validate(expense)


@router.patch("/{expense_id}/reverse", response_model=ExpenseResponse)
async def reverse_expense(
    expense_id: int,
    data: ExpenseReverseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    result = await db.execute(select(Expense).where(Expense.id == expense_id))
    expense = result.scalar_one_or_none()
    if not expense:
        raise HTTPException(404, "Expense not found")
    if getattr(expense, "status", "paid") == "reversed":
        raise HTTPException(400, "Expense is already reversed")
    if getattr(expense, "reversed_expense_id", None):
        raise HTTPException(400, "Expense is already reversed")

    reversal = await create_expense_reversal(
        db,
        expense,
        reverse_date=data.date if data.date else None,
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
    result = await db.execute(select(Expense).where(Expense.id == expense_id))
    expense = result.scalar_one_or_none()
    if not expense:
        raise HTTPException(404, "Expense not found")

    dump = data.model_dump(exclude_unset=True)
    desired_project_id = dump.get("project_id", expense.project_id)
    desired_contract_id = dump.get("contract_id", expense.contract_id)

    if not desired_project_id:
        desired_project_id = await _get_unassigned_project_id(db)

    if desired_contract_id is None and expense.contract_id and "project_id" in dump:
        contract = await _get_contract_or_404(db, expense.contract_id)
        if contract.project_id != desired_project_id:
            desired_contract_id = None

    desired_project_id, desired_contract_id = await _resolve_expense_links(db, desired_project_id, desired_contract_id)
    dump["project_id"] = desired_project_id
    dump["contract_id"] = desired_contract_id

    for key, value in dump.items():
        setattr(expense, key, value)

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
    result = await db.execute(select(Expense).where(Expense.id == expense_id))
    expense = result.scalar_one_or_none()
    if not expense:
        raise HTTPException(404, "Expense not found")
    if getattr(expense, "status", "paid") == "reversed" or getattr(expense, "reversed_expense_id", None):
        raise HTTPException(400, "Expense is already reversed")

    reversal = await create_expense_reversal(
        db,
        expense,
        source=getattr(expense, "source", None) or "manual",
        created_by=current_user.id,
    )
    await db.commit()
    return {"ok": True, "reversal_id": reversal.id}
