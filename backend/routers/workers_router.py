"""Workers and cash payout helpers."""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.auth import get_current_user_required, require_edit_access
from backend.database import get_db
from backend.db_utils import (
    get_contract_or_404,
    get_project_or_404,
    get_unassigned_project_id,
    resolve_category_expense_links,
)
from backend.decimal_utils import ZERO_DECIMAL, to_decimal
from backend.models import CashEntry, Expense, TransactionCategory, User, Worker, WorkerPayout
from backend.planned_expenses_service import sync_worker_payout_planned_payment
from backend.schemas import (
    CashEntryResponse,
    WorkerCreate,
    WorkerPayoutCreate,
    WorkerPayoutCreateResponse,
    WorkerPayoutResponse,
    WorkerResponse,
    WorkerUpdate,
)
from backend.state_machine import initialize_expense_status

router = APIRouter(prefix="/workers", tags=["workers"])


def _dec(value) -> Decimal:
    return to_decimal(value or ZERO_DECIMAL)


async def _get_worker_or_404(db: AsyncSession, worker_id: int) -> Worker:
    result = await db.execute(select(Worker).where(Worker.id == worker_id))
    worker = result.scalar_one_or_none()
    if not worker:
        raise HTTPException(404, "Worker not found")
    return worker


async def _get_salary_category_id(db: AsyncSession) -> int | None:
    result = await db.execute(
        select(TransactionCategory)
        .where(TransactionCategory.category_type == "expense")
        .where(
            or_(
                func.lower(TransactionCategory.name_sr).like("%zarad%"),
                func.lower(TransactionCategory.name_ru).like("%зарп%"),
            )
        )
        .order_by(TransactionCategory.id.asc())
        .limit(1)
    )
    category = result.scalar_one_or_none()
    return int(category.id) if category else None


async def _resolve_payout_links(
    db: AsyncSession,
    worker: Worker,
    data: WorkerPayoutCreate,
) -> tuple[int | None, int | None, int | None, str | None, bool]:
    category_id = data.category_id or worker.default_category_id or await _get_salary_category_id(db)
    project_id = data.project_id or worker.default_project_id
    contract_id = data.contract_id
    project_id, contract_id, is_tax_related = await resolve_category_expense_links(
        db, category_id, project_id, contract_id
    )

    if not project_id:
        project_id = await get_unassigned_project_id(db)
    if contract_id is not None:
        contract = await get_contract_or_404(db, contract_id)
        if contract.project_id is None:
            if project_id is None:
                raise HTTPException(400, "Select a project before linking this contract")
            await get_project_or_404(db, project_id)
            contract.project_id = project_id
            await db.flush()
        project_id = contract.project_id
    if project_id is not None:
        await get_project_or_404(db, project_id)

    category_name = None
    if category_id is not None:
        category_result = await db.execute(select(TransactionCategory).where(TransactionCategory.id == category_id))
        category = category_result.scalar_one_or_none()
        if not category:
            raise HTTPException(404, "Category not found")
        category_name = category.name_ru

    return project_id, contract_id, category_id, category_name, is_tax_related


def _build_payout_storage_description(worker: Worker, data: WorkerPayoutCreate) -> str:
    period = ""
    if data.period_start and data.period_end:
        period = f" {data.period_start.isoformat()}-{data.period_end.isoformat()}"
    return f"worker_payout:{data.payout_type}: {worker.name}{period}".strip()[:500]


def _inclusive_period_days(data: WorkerPayoutCreate) -> Decimal | None:
    if not data.period_start or not data.period_end or data.period_end < data.period_start:
        return None
    return Decimal((data.period_end - data.period_start).days + 1)


def _calculate_payout(worker: Worker, data: WorkerPayoutCreate) -> dict[str, Decimal]:
    payout_type = data.payout_type or "regular"
    work_days = _dec(data.work_days)
    trip_days = _dec(data.trip_days)
    period_days = _inclusive_period_days(data)
    if period_days is not None:
        if payout_type == "regular":
            work_days = period_days
        elif payout_type.startswith("trip"):
            trip_days = period_days
    regular_day_rate = _dec(data.regular_day_rate if data.regular_day_rate is not None else worker.regular_day_rate)
    weekly_rate = _dec(data.weekly_rate if data.weekly_rate is not None else worker.weekly_rate)
    monthly_rate = _dec(data.monthly_rate if data.monthly_rate is not None else worker.monthly_rate)
    trip_pricing_mode = data.trip_pricing_mode or worker.trip_pricing_mode or "allowances"
    trip_work_day_rate = _dec(
        data.trip_work_day_rate if data.trip_work_day_rate is not None else worker.trip_work_day_rate
    )
    if trip_work_day_rate <= ZERO_DECIMAL:
        trip_work_day_rate = regular_day_rate
    if trip_pricing_mode == "fixed_plus_lodging":
        trip_per_diem_rate = ZERO_DECIMAL
        trip_food_rate = ZERO_DECIMAL
    else:
        trip_per_diem_rate = _dec(
            data.trip_per_diem_rate if data.trip_per_diem_rate is not None else worker.trip_per_diem_rate
        )
        trip_food_rate = _dec(data.trip_food_rate if data.trip_food_rate is not None else worker.trip_food_rate)
    trip_advance_day_rate = _dec(
        data.trip_advance_day_rate if data.trip_advance_day_rate is not None else worker.trip_advance_day_rate
    )

    if payout_type.startswith("trip") and period_days is not None:
        lodging_nights = max(period_days - Decimal(1), ZERO_DECIMAL)
    elif data.lodging_nights is not None:
        lodging_nights = _dec(data.lodging_nights)
    else:
        lodging_nights = max(trip_days + Decimal(int(worker.lodging_nights_offset or 0)), ZERO_DECIMAL)
    lodging_night_rate = _dec(
        data.lodging_night_rate if data.lodging_night_rate is not None else worker.lodging_night_rate
    )
    lodging_amount = (
        lodging_nights * lodging_night_rate if data.lodging_night_rate is not None else _dec(data.lodging_amount)
    )
    if data.lodging_amount is None and data.lodging_night_rate is None:
        lodging_amount = lodging_nights * lodging_night_rate

    if payout_type == "monthly":
        gross_amount = monthly_rate
    elif payout_type == "weekly":
        gross_amount = weekly_rate
    elif payout_type == "regular":
        gross_amount = work_days * regular_day_rate
    else:
        gross_amount = trip_days * (trip_work_day_rate + trip_per_diem_rate + trip_food_rate) + lodging_amount

    if data.cash_paid_amount is not None:
        cash_paid_amount = _dec(data.cash_paid_amount)
    elif payout_type == "trip_advance":
        cash_paid_amount = trip_days * trip_advance_day_rate + lodging_amount
    elif payout_type == "trip_final":
        cash_paid_amount = max(gross_amount - _dec(data.advance_paid), ZERO_DECIMAL)
    else:
        cash_paid_amount = gross_amount

    remaining_amount = max(gross_amount - _dec(data.advance_paid) - cash_paid_amount, ZERO_DECIMAL)
    return {
        "work_days": work_days,
        "trip_days": trip_days,
        "lodging_nights": lodging_nights,
        "regular_day_rate": regular_day_rate,
        "weekly_rate": weekly_rate,
        "monthly_rate": monthly_rate,
        "trip_pricing_mode": trip_pricing_mode,
        "trip_work_day_rate": trip_work_day_rate,
        "trip_per_diem_rate": trip_per_diem_rate,
        "trip_food_rate": trip_food_rate,
        "trip_advance_day_rate": trip_advance_day_rate,
        "lodging_night_rate": lodging_night_rate,
        "lodging_amount": lodging_amount,
        "gross_amount": gross_amount,
        "cash_paid_amount": cash_paid_amount,
        "remaining_amount": remaining_amount,
    }


def _serialize_worker_payout(payout: WorkerPayout) -> WorkerPayoutResponse:
    return WorkerPayoutResponse(
        id=payout.id,
        worker_id=payout.worker_id,
        worker_name=getattr(getattr(payout, "worker", None), "name", None),
        cash_entry_id=payout.cash_entry_id,
        expense_id=payout.expense_id,
        payout_type=payout.payout_type,
        date=payout.date,
        period_start=payout.period_start,
        period_end=payout.period_end,
        work_days=_dec(payout.work_days),
        trip_days=_dec(payout.trip_days),
        lodging_nights=_dec(payout.lodging_nights),
        lodging_night_rate=_dec(payout.lodging_night_rate),
        lodging_amount=_dec(payout.lodging_amount),
        advance_paid=_dec(payout.advance_paid),
        gross_amount=_dec(payout.gross_amount),
        cash_paid_amount=_dec(payout.cash_paid_amount),
        remaining_amount=_dec(payout.remaining_amount),
        description=payout.description,
        note=payout.note,
        project_id=payout.project_id,
        contract_id=payout.contract_id,
        category_id=payout.category_id,
        created_at=payout.created_at,
    )


def _serialize_cash_entry(entry: CashEntry, payout: WorkerPayout | None = None) -> CashEntryResponse:
    return CashEntryResponse(
        id=entry.id,
        date=entry.date,
        direction=entry.direction,
        amount=_dec(entry.amount),
        currency=entry.currency or "RSD",
        description=entry.description,
        entry_type=entry.entry_type,
        note=entry.note,
        bank_transaction_id=entry.bank_transaction_id,
        expense_id=entry.expense_id,
        worker_payout_id=getattr(payout, "id", None),
        worker_payout_type=getattr(payout, "payout_type", None),
        worker_payout_worker_name=getattr(getattr(payout, "worker", None), "name", None),
        worker_payout_period_start=getattr(payout, "period_start", None),
        worker_payout_period_end=getattr(payout, "period_end", None),
        worker_payout_gross_amount=_dec(getattr(payout, "gross_amount", None)) if payout else None,
        worker_payout_remaining_amount=_dec(getattr(payout, "remaining_amount", None)) if payout else None,
        balance_after=ZERO_DECIMAL,
        created_at=entry.created_at,
    )


@router.get("", response_model=list[WorkerResponse])
async def list_workers(
    search: str = Query(""),
    active: bool | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    query = select(Worker)
    if active is not None:
        query = query.where(Worker.is_active == active)
    if search:
        query = query.where(or_(Worker.name.ilike(f"%{search}%"), Worker.phone.ilike(f"%{search}%")))
    result = await db.execute(query.order_by(Worker.name.asc()))
    return [WorkerResponse.model_validate(worker) for worker in result.scalars().all()]


@router.post("", response_model=WorkerResponse)
async def create_worker(
    data: WorkerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    worker = Worker(**data.model_dump())
    worker.name = worker.name.strip()
    if not worker.name:
        raise HTTPException(400, "Name is required")
    db.add(worker)
    await db.commit()
    await db.refresh(worker)
    return WorkerResponse.model_validate(worker)


@router.patch("/{worker_id}", response_model=WorkerResponse)
async def update_worker(
    worker_id: int,
    data: WorkerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    worker = await _get_worker_or_404(db, worker_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(worker, key, value)
    worker.name = (worker.name or "").strip()
    if not worker.name:
        raise HTTPException(400, "Name is required")
    await db.commit()
    await db.refresh(worker)
    return WorkerResponse.model_validate(worker)


@router.delete("/{worker_id}")
async def archive_worker(
    worker_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    worker = await _get_worker_or_404(db, worker_id)
    worker.is_active = False
    await db.commit()
    return {"ok": True}


@router.get("/payouts", response_model=list[WorkerPayoutResponse])
async def list_worker_payouts(
    worker_id: int | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    query = select(WorkerPayout).options(selectinload(WorkerPayout.worker))
    if worker_id is not None:
        query = query.where(WorkerPayout.worker_id == worker_id)
    result = await db.execute(query.order_by(WorkerPayout.date.desc(), WorkerPayout.id.desc()).limit(limit))
    return [_serialize_worker_payout(item) for item in result.scalars().all()]


@router.get("/payouts/{payout_id}", response_model=WorkerPayoutResponse)
async def get_worker_payout(
    payout_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(WorkerPayout).options(selectinload(WorkerPayout.worker)).where(WorkerPayout.id == payout_id)
    )
    payout = result.scalar_one_or_none()
    if not payout:
        raise HTTPException(404, "Worker payout not found")
    return _serialize_worker_payout(payout)


@router.post("/payouts", response_model=WorkerPayoutCreateResponse)
async def create_worker_payout(
    data: WorkerPayoutCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    worker = await _get_worker_or_404(db, data.worker_id)
    if not worker.is_active:
        raise HTTPException(400, "Worker is inactive")

    project_id, contract_id, category_id, category_name, is_tax_related = await _resolve_payout_links(db, worker, data)
    calc = _calculate_payout(worker, data)
    if calc["cash_paid_amount"] <= ZERO_DECIMAL:
        raise HTTPException(400, "Cash paid amount must be greater than zero")

    description = (data.description or _build_payout_storage_description(worker, data)).strip()[:500]
    note = data.note.strip() if data.note and data.note.strip() else None

    expense = Expense(
        date=data.date,
        description=description,
        amount=calc["cash_paid_amount"],
        currency="RSD",
        category=category_name,
        category_id=category_id,
        contract_id=contract_id,
        is_tax_related=is_tax_related,
        source="cash",
        note=note,
        project_id=project_id,
        created_by=current_user.id,
    )
    initialize_expense_status(expense, "paid", paid_date=data.date)
    db.add(expense)
    await db.flush()

    entry = CashEntry(
        date=data.date,
        direction="out",
        amount=calc["cash_paid_amount"],
        currency="RSD",
        description=description,
        entry_type="expense",
        note=note,
        expense_id=expense.id,
        created_by=current_user.id,
    )
    db.add(entry)
    await db.flush()

    payout = WorkerPayout(
        worker_id=worker.id,
        cash_entry_id=entry.id,
        expense_id=expense.id,
        payout_type=data.payout_type,
        date=data.date,
        period_start=data.period_start,
        period_end=data.period_end,
        work_days=calc["work_days"],
        trip_days=calc["trip_days"],
        lodging_nights=calc["lodging_nights"],
        regular_day_rate=calc["regular_day_rate"],
        weekly_rate=calc["weekly_rate"],
        monthly_rate=calc["monthly_rate"],
        trip_pricing_mode=calc["trip_pricing_mode"],
        trip_work_day_rate=calc["trip_work_day_rate"],
        trip_per_diem_rate=calc["trip_per_diem_rate"],
        trip_food_rate=calc["trip_food_rate"],
        trip_advance_day_rate=calc["trip_advance_day_rate"],
        lodging_night_rate=calc["lodging_night_rate"],
        lodging_amount=calc["lodging_amount"],
        advance_paid=_dec(data.advance_paid),
        gross_amount=calc["gross_amount"],
        cash_paid_amount=calc["cash_paid_amount"],
        remaining_amount=calc["remaining_amount"],
        description=description,
        note=note,
        project_id=project_id,
        contract_id=contract_id,
        category_id=category_id,
        created_by=current_user.id,
    )
    db.add(payout)
    await db.flush()
    await sync_worker_payout_planned_payment(db, payout)

    await db.commit()
    await db.refresh(payout, ["worker"])
    await db.refresh(entry)
    return WorkerPayoutCreateResponse(
        payout=_serialize_worker_payout(payout),
        cash_entry=_serialize_cash_entry(entry, payout),
    )


@router.patch("/payouts/{payout_id}", response_model=WorkerPayoutCreateResponse)
async def update_worker_payout(
    payout_id: int,
    data: WorkerPayoutCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    result = await db.execute(
        select(WorkerPayout)
        .options(
            selectinload(WorkerPayout.worker),
            selectinload(WorkerPayout.cash_entry),
            selectinload(WorkerPayout.expense),
        )
        .where(WorkerPayout.id == payout_id)
    )
    payout = result.scalar_one_or_none()
    if not payout:
        raise HTTPException(404, "Worker payout not found")

    worker = await _get_worker_or_404(db, data.worker_id)
    project_id, contract_id, category_id, category_name, is_tax_related = await _resolve_payout_links(db, worker, data)
    calc = _calculate_payout(worker, data)
    if calc["cash_paid_amount"] <= ZERO_DECIMAL:
        raise HTTPException(400, "Cash paid amount must be greater than zero")

    description = (data.description or _build_payout_storage_description(worker, data)).strip()[:500]
    note = data.note.strip() if data.note and data.note.strip() else None

    expense = payout.expense
    entry = payout.cash_entry
    if not expense or not entry:
        raise HTTPException(404, "Linked cash expense was not found")
    if entry.entry_type != "expense":
        raise HTTPException(400, "Linked cash entry is not an expense")

    expense.date = data.date
    expense.paid_date = data.date
    expense.description = description
    expense.amount = calc["cash_paid_amount"]
    expense.currency = "RSD"
    expense.category = category_name
    expense.category_id = category_id
    expense.contract_id = contract_id
    expense.is_tax_related = is_tax_related
    expense.source = "cash"
    expense.note = note
    expense.project_id = project_id

    entry.date = data.date
    entry.direction = "out"
    entry.amount = calc["cash_paid_amount"]
    entry.currency = "RSD"
    entry.description = description
    entry.entry_type = "expense"
    entry.note = note
    entry.expense_id = expense.id

    payout.worker_id = worker.id
    payout.cash_entry_id = entry.id
    payout.expense_id = expense.id
    payout.payout_type = data.payout_type
    payout.date = data.date
    payout.period_start = data.period_start
    payout.period_end = data.period_end
    payout.work_days = calc["work_days"]
    payout.trip_days = calc["trip_days"]
    payout.lodging_nights = calc["lodging_nights"]
    payout.regular_day_rate = calc["regular_day_rate"]
    payout.weekly_rate = calc["weekly_rate"]
    payout.monthly_rate = calc["monthly_rate"]
    payout.trip_pricing_mode = calc["trip_pricing_mode"]
    payout.trip_work_day_rate = calc["trip_work_day_rate"]
    payout.trip_per_diem_rate = calc["trip_per_diem_rate"]
    payout.trip_food_rate = calc["trip_food_rate"]
    payout.trip_advance_day_rate = calc["trip_advance_day_rate"]
    payout.lodging_night_rate = calc["lodging_night_rate"]
    payout.lodging_amount = calc["lodging_amount"]
    payout.advance_paid = _dec(data.advance_paid)
    payout.gross_amount = calc["gross_amount"]
    payout.cash_paid_amount = calc["cash_paid_amount"]
    payout.remaining_amount = calc["remaining_amount"]
    payout.description = description
    payout.note = note
    payout.project_id = project_id
    payout.contract_id = contract_id
    payout.category_id = category_id

    await sync_worker_payout_planned_payment(db, payout)
    await db.commit()
    await db.refresh(payout, ["worker"])
    await db.refresh(entry)
    return WorkerPayoutCreateResponse(
        payout=_serialize_worker_payout(payout),
        cash_entry=_serialize_cash_entry(entry, payout),
    )
