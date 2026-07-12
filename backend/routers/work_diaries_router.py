"""Work diaries and construction diary reports.

Роль модуля — аналитика работ: труд считается по ставкам из дневника, а деньги за
материалы живут в модуле Расходы. Строка материалов либо привязана к расходу проекта
(source="expense", в затраты объекта повторно не входит), либо взята со склада
(source="stock", стоимость — оценка, прибавляется к затратам объекта).
"""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.auth import get_current_user_required, require_edit_access
from backend.database import get_db
from backend.expense_service import CASH_TRANSFER_SOURCE, visible_expense_condition
from backend.models import (
    Enterprise,
    Expense,
    Project,
    User,
    WorkDiaryEntry,
    WorkDiaryMaterial,
    WorkDiaryProjectMeta,
    Worker,
)
from backend.schemas import (
    WorkDiaryEntryCreate,
    WorkDiaryEntryResponse,
    WorkDiaryEntryUpdate,
    WorkDiaryExpenseOptionResponse,
    WorkDiaryMaterialCreate,
    WorkDiaryMaterialResponse,
    WorkDiaryProjectCostsResponse,
    WorkDiaryProjectMetaBase,
    WorkDiaryProjectMetaResponse,
    WorkDiarySummaryResponse,
)

router = APIRouter(prefix="/work-diaries", tags=["work-diaries"])

REGULAR_DAY_HOURS = Decimal("8")
# Закон о раде РС, чл. 108: надбавка за сверхурочные — минимум +26%
DEFAULT_OVERTIME_MULTIPLIER = Decimal("1.26")
EXPENSE_OPTIONS_LIMIT = 300


def _dec(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value))


def _float(value) -> float:
    return float(_dec(value))


def _time_to_hours(value: str | None) -> Decimal | None:
    if not value:
        return None
    parts = value.split(":")
    if len(parts) != 2:
        raise HTTPException(400, "Time must be in HH:MM format")
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
    except ValueError as exc:
        raise HTTPException(400, "Time must be in HH:MM format") from exc
    if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
        raise HTTPException(400, "Time must be in HH:MM format")
    return Decimal(hours) + (Decimal(minutes) / Decimal(60))


def _calculate_duration_hours(
    start_time: str | None,
    end_time: str | None,
    explicit_duration_hours: float | None,
) -> Decimal:
    start_hours = _time_to_hours(start_time)
    end_hours = _time_to_hours(end_time)
    if (start_hours is None) != (end_hours is None):
        raise HTTPException(400, "Provide both start_time and end_time")
    if start_hours is not None and end_hours is not None:
        duration_hours = end_hours - start_hours
        if duration_hours <= 0:
            raise HTTPException(400, "End time must be after start time")
        return duration_hours.quantize(Decimal("0.01"))
    if explicit_duration_hours is None:
        raise HTTPException(400, "Provide duration_hours or both start_time and end_time")
    duration_hours = _dec(explicit_duration_hours).quantize(Decimal("0.01"))
    if duration_hours <= 0:
        raise HTTPException(400, "duration_hours must be greater than zero")
    return duration_hours


def _default_hourly_rate(worker: Worker | None) -> Decimal:
    if not worker:
        return Decimal("0")
    day_rate = _dec(worker.regular_day_rate)
    return (day_rate / REGULAR_DAY_HOURS).quantize(Decimal("0.01")) if day_rate > 0 else Decimal("0")


async def _default_overtime_multiplier(db: AsyncSession) -> Decimal:
    result = await db.execute(select(Enterprise.work_diary_overtime_multiplier).limit(1))
    value = result.scalar_one_or_none()
    return _dec(value) if value else DEFAULT_OVERTIME_MULTIPLIER


async def _get_project(db: AsyncSession, project_id: int) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    return project


async def _get_workers(db: AsyncSession, worker_ids: list[int]) -> list[Worker]:
    normalized_ids = list(dict.fromkeys(worker_ids))
    if not normalized_ids:
        return []
    result = await db.execute(select(Worker).where(Worker.id.in_(normalized_ids)))
    workers_by_id = {worker.id: worker for worker in result.scalars().all()}
    missing_ids = [worker_id for worker_id in normalized_ids if worker_id not in workers_by_id]
    if missing_ids:
        raise HTTPException(404, f"Worker not found: {missing_ids[0]}")
    return [workers_by_id[worker_id] for worker_id in normalized_ids]


def _entry_workers(entry: WorkDiaryEntry) -> list[Worker]:
    return sorted(entry.workers, key=lambda worker: (worker.name or "").casefold())


async def _get_entry(db: AsyncSession, entry_id: int) -> WorkDiaryEntry:
    result = await db.execute(
        select(WorkDiaryEntry)
        .options(
            selectinload(WorkDiaryEntry.project),
            selectinload(WorkDiaryEntry.workers),
            selectinload(WorkDiaryEntry.materials).selectinload(WorkDiaryMaterial.expense),
        )
        .where(WorkDiaryEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Work diary entry not found")
    return entry


def _apply_calculated_fields(
    entry: WorkDiaryEntry,
    *,
    duration_hours: Decimal,
    team_hourly_rate: Decimal,
    overtime_multiplier: Decimal,
) -> None:
    entry.duration_hours = duration_hours
    entry.regular_duration_hours = min(duration_hours, REGULAR_DAY_HOURS)
    entry.overtime_duration_hours = max(duration_hours - REGULAR_DAY_HOURS, Decimal("0"))
    entry.team_hourly_rate_snapshot = team_hourly_rate
    entry.overtime_multiplier = overtime_multiplier


async def _load_material_expenses(
    db: AsyncSession,
    project_id: int,
    materials: list[WorkDiaryMaterialCreate],
) -> dict[int, Expense]:
    expense_ids = {item.expense_id for item in materials if item.source == "expense" and item.expense_id}
    if not expense_ids:
        return {}
    result = await db.execute(select(Expense).where(Expense.id.in_(expense_ids)))
    expenses_by_id = {expense.id: expense for expense in result.scalars().all()}
    for expense_id in expense_ids:
        expense = expenses_by_id.get(expense_id)
        if not expense:
            raise HTTPException(404, f"Expense not found: {expense_id}")
        if expense.project_id != project_id:
            raise HTTPException(400, "Linked expense belongs to a different project")
        if expense.status == "reversed" or expense.reversal_of_id or expense.reversed_expense_id:
            raise HTTPException(400, "Linked expense is reversed")
    return expenses_by_id


def _validate_existing_material_links(entry: WorkDiaryEntry, project_id: int) -> None:
    for material in entry.materials:
        expense = material.expense
        if expense is not None and expense.project_id != project_id:
            raise HTTPException(400, "Linked expense belongs to a different project")


def _replace_materials(
    entry: WorkDiaryEntry,
    materials: list[WorkDiaryMaterialCreate],
    expenses_by_id: dict[int, Expense],
) -> None:
    rows: list[WorkDiaryMaterial] = []
    for item in materials:
        expense = expenses_by_id.get(item.expense_id) if item.source == "expense" else None
        description = item.description.strip() or (expense.description if expense else "")
        if not description:
            continue
        amount = _dec(item.amount)
        if expense is not None and amount <= 0:
            amount = _dec(expense.amount)
        rows.append(
            WorkDiaryMaterial(
                line_no=len(rows) + 1,
                description=description,
                quantity=item.quantity,
                unit=item.unit,
                source=item.source,
                expense_id=expense.id if expense else None,
                amount=amount,
            )
        )
    entry.materials = rows


def _entry_amounts(entry: WorkDiaryEntry, meta: WorkDiaryProjectMeta | None = None) -> dict[str, Decimal]:
    worker_count = len(entry.workers)
    rate = _dec(entry.team_hourly_rate_snapshot)
    labor = _dec(entry.regular_duration_hours) * rate
    labor += _dec(entry.overtime_duration_hours) * rate * _dec(entry.overtime_multiplier)
    # Дневница и питание — на человека, проживание — на всю бригаду
    allowances = _dec(entry.lodging_amount)
    if entry.per_diem:
        allowances += _dec(entry.per_diem_amount) * worker_count
    if entry.food_allowance:
        allowances += _dec(entry.food_amount) * worker_count
    stock_materials = Decimal("0")
    linked_materials = Decimal("0")
    for material in entry.materials:
        if material.source == "expense":
            linked_materials += _dec(material.amount)
        else:
            stock_materials += _dec(material.amount)
    materials = stock_materials + linked_materials
    billing_rate = _dec(getattr(meta, "billing_hourly_rate", 0))
    person_hours = _dec(entry.duration_hours) * worker_count
    billable = person_hours * billing_rate + materials
    return {
        "labor_amount": labor,
        "payout_amount": labor + allowances,
        "allowance_amount": allowances,
        "material_amount": materials,
        "stock_material_amount": stock_materials,
        "linked_material_amount": linked_materials,
        "total_cost_amount": labor + allowances + materials,
        "billable_amount": billable,
    }


def _serialize_material(material: WorkDiaryMaterial) -> WorkDiaryMaterialResponse:
    expense = material.expense
    return WorkDiaryMaterialResponse(
        id=material.id,
        line_no=material.line_no,
        description=material.description,
        quantity=_float(material.quantity) if material.quantity is not None else None,
        unit=material.unit,
        source=material.source,
        expense_id=material.expense_id,
        expense_date=getattr(expense, "date", None),
        expense_description=getattr(expense, "description", None),
        amount=_float(material.amount),
    )


async def _meta_by_project_ids(db: AsyncSession, project_ids: set[int]) -> dict[int, WorkDiaryProjectMeta]:
    if not project_ids:
        return {}
    result = await db.execute(select(WorkDiaryProjectMeta).where(WorkDiaryProjectMeta.project_id.in_(project_ids)))
    return {meta.project_id: meta for meta in result.scalars().all()}


def _serialize_entry(entry: WorkDiaryEntry, meta: WorkDiaryProjectMeta | None = None) -> WorkDiaryEntryResponse:
    amounts = _entry_amounts(entry, meta)
    workers = _entry_workers(entry)
    worker_count = len(workers)
    return WorkDiaryEntryResponse(
        id=entry.id,
        date=entry.date,
        project_id=entry.project_id,
        project_name=getattr(getattr(entry, "project", None), "name", None),
        worker_ids=[worker.id for worker in workers],
        worker_names=[worker.name for worker in workers],
        description=entry.description,
        start_time=entry.start_time,
        end_time=entry.end_time,
        duration_hours=_float(entry.duration_hours),
        person_hours=_float(_dec(entry.duration_hours) * worker_count),
        regular_person_hours=_float(_dec(entry.regular_duration_hours) * worker_count),
        overtime_person_hours=_float(_dec(entry.overtime_duration_hours) * worker_count),
        team_hourly_rate_snapshot=_float(entry.team_hourly_rate_snapshot),
        overtime_multiplier=_float(entry.overtime_multiplier),
        labor_amount=_float(amounts["labor_amount"]),
        payout_amount=_float(amounts["payout_amount"]),
        allowance_amount=_float(amounts["allowance_amount"]),
        material_amount=_float(amounts["material_amount"]),
        stock_material_amount=_float(amounts["stock_material_amount"]),
        linked_material_amount=_float(amounts["linked_material_amount"]),
        total_cost_amount=_float(amounts["total_cost_amount"]),
        billable_amount=_float(amounts["billable_amount"]),
        per_diem=bool(entry.per_diem),
        per_diem_amount=_float(entry.per_diem_amount),
        lodging_amount=_float(entry.lodging_amount),
        food_allowance=bool(entry.food_allowance),
        food_amount=_float(entry.food_amount),
        weather=entry.weather,
        temperature=entry.temperature,
        note=entry.note,
        materials=[_serialize_material(material) for material in entry.materials],
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


def _serialize_meta(project: Project, meta: WorkDiaryProjectMeta | None) -> WorkDiaryProjectMetaResponse:
    if meta:
        return WorkDiaryProjectMetaResponse(
            id=meta.id,
            project_id=project.id,
            project_name=project.name,
            investor=meta.investor,
            permit_number=meta.permit_number,
            contractor=meta.contractor,
            place=meta.place,
            supervision=meta.supervision,
            object_name=meta.object_name,
            sector=meta.sector,
            responsible_person=meta.responsible_person,
            billing_hourly_rate=_float(meta.billing_hourly_rate),
        )
    return WorkDiaryProjectMetaResponse(project_id=project.id, project_name=project.name)


@router.get("/entries", response_model=list[WorkDiaryEntryResponse])
async def list_entries(
    project_id: int | None = Query(None),
    worker_id: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    query = select(WorkDiaryEntry).options(
        selectinload(WorkDiaryEntry.project),
        selectinload(WorkDiaryEntry.workers),
        selectinload(WorkDiaryEntry.materials).selectinload(WorkDiaryMaterial.expense),
    )
    if project_id is not None:
        query = query.where(WorkDiaryEntry.project_id == project_id)
    if worker_id is not None:
        query = query.where(WorkDiaryEntry.workers.any(Worker.id == worker_id))
    if date_from is not None:
        query = query.where(WorkDiaryEntry.date >= date_from)
    if date_to is not None:
        query = query.where(WorkDiaryEntry.date <= date_to)
    query = query.order_by(WorkDiaryEntry.date.desc(), WorkDiaryEntry.id.desc())
    result = await db.execute(query)
    entries = result.scalars().all()
    metas = await _meta_by_project_ids(db, {entry.project_id for entry in entries})
    return [_serialize_entry(entry, metas.get(entry.project_id)) for entry in entries]


@router.post("/entries", response_model=WorkDiaryEntryResponse)
async def create_entry(
    data: WorkDiaryEntryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    await _get_project(db, data.project_id)
    workers = await _get_workers(db, data.worker_ids)
    material_expenses = await _load_material_expenses(db, data.project_id, data.materials)
    duration_hours = _calculate_duration_hours(data.start_time, data.end_time, data.duration_hours)
    team_hourly_rate = (
        _dec(data.team_hourly_rate_snapshot)
        if data.team_hourly_rate_snapshot is not None
        else sum((_default_hourly_rate(worker) for worker in workers), Decimal("0"))
    )
    overtime_multiplier = (
        _dec(data.overtime_multiplier)
        if data.overtime_multiplier is not None
        else await _default_overtime_multiplier(db)
    )
    entry = WorkDiaryEntry(
        date=data.date,
        project_id=data.project_id,
        description=data.description.strip(),
        start_time=data.start_time,
        end_time=data.end_time,
        per_diem=data.per_diem,
        per_diem_amount=_dec(data.per_diem_amount),
        lodging_amount=_dec(data.lodging_amount),
        food_allowance=data.food_allowance,
        food_amount=_dec(data.food_amount),
        weather=data.weather,
        temperature=data.temperature,
        note=data.note,
        created_by=current_user.id,
    )
    entry.workers = workers
    _apply_calculated_fields(
        entry,
        duration_hours=duration_hours,
        team_hourly_rate=team_hourly_rate,
        overtime_multiplier=overtime_multiplier,
    )
    _replace_materials(entry, data.materials, material_expenses)
    db.add(entry)
    await db.commit()
    entry = await _get_entry(db, entry.id)
    metas = await _meta_by_project_ids(db, {entry.project_id})
    return _serialize_entry(entry, metas.get(entry.project_id))


@router.patch("/entries/{entry_id}", response_model=WorkDiaryEntryResponse)
async def update_entry(
    entry_id: int,
    data: WorkDiaryEntryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    entry = await _get_entry(db, entry_id)
    dump = data.model_dump(exclude_unset=True)
    next_project_id = dump.get("project_id", entry.project_id)
    await _get_project(db, next_project_id)
    if data.materials is not None:
        material_expenses = await _load_material_expenses(db, next_project_id, data.materials)
    else:
        material_expenses = {}
        _validate_existing_material_links(entry, next_project_id)
    workers_changed = "worker_ids" in dump
    if workers_changed:
        workers = await _get_workers(db, dump["worker_ids"] or [])
        entry.workers = workers
    else:
        workers = _entry_workers(entry)

    for key in (
        "date",
        "project_id",
        "description",
        "start_time",
        "end_time",
        "per_diem",
        "lodging_amount",
        "food_allowance",
        "weather",
        "temperature",
        "note",
    ):
        if key in dump:
            setattr(entry, key, dump[key])
    if "per_diem_amount" in dump:
        entry.per_diem_amount = _dec(dump["per_diem_amount"])
    if "food_amount" in dump:
        entry.food_amount = _dec(dump["food_amount"])

    # Явная длительность без явных времен означает ручной ввод: старые времена сбрасываются,
    # иначе они бы молча перекрыли переданное значение.
    if dump.get("duration_hours") is not None and "start_time" not in dump and "end_time" not in dump:
        entry.start_time = None
        entry.end_time = None
    duration_hours = _calculate_duration_hours(
        entry.start_time,
        entry.end_time,
        dump.get("duration_hours", _float(entry.duration_hours)),
    )
    if "team_hourly_rate_snapshot" in dump:
        if dump["team_hourly_rate_snapshot"] is None:
            team_hourly_rate = sum((_default_hourly_rate(worker) for worker in workers), Decimal("0"))
        else:
            team_hourly_rate = _dec(dump["team_hourly_rate_snapshot"])
    elif workers_changed:
        team_hourly_rate = sum((_default_hourly_rate(worker) for worker in workers), Decimal("0"))
    else:
        team_hourly_rate = _dec(entry.team_hourly_rate_snapshot)
    if "overtime_multiplier" in dump:
        if dump["overtime_multiplier"] is None:
            overtime_multiplier = await _default_overtime_multiplier(db)
        else:
            overtime_multiplier = _dec(dump["overtime_multiplier"])
    else:
        overtime_multiplier = _dec(entry.overtime_multiplier)
    _apply_calculated_fields(
        entry,
        duration_hours=duration_hours,
        team_hourly_rate=team_hourly_rate,
        overtime_multiplier=overtime_multiplier,
    )
    if data.materials is not None:
        _replace_materials(entry, data.materials, material_expenses)

    await db.commit()
    entry = await _get_entry(db, entry.id)
    metas = await _meta_by_project_ids(db, {entry.project_id})
    return _serialize_entry(entry, metas.get(entry.project_id))


@router.delete("/entries/{entry_id}")
async def delete_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    entry = await _get_entry(db, entry_id)
    await db.delete(entry)
    await db.commit()
    return {"ok": True}


@router.get("/expense-options", response_model=list[WorkDiaryExpenseOptionResponse])
async def list_expense_options(
    project_id: int = Query(...),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Расходы проекта, к которым можно привязать строку материалов."""
    await _get_project(db, project_id)
    query = select(Expense).where(
        Expense.project_id == project_id,
        Expense.source != CASH_TRANSFER_SOURCE,
        visible_expense_condition(),
        Expense.reversal_of_id.is_(None),
        Expense.reversed_expense_id.is_(None),
        Expense.amount > 0,
    )
    if date_from is not None:
        query = query.where(Expense.date >= date_from)
    if date_to is not None:
        query = query.where(Expense.date <= date_to)
    query = query.order_by(Expense.date.desc(), Expense.id.desc()).limit(EXPENSE_OPTIONS_LIMIT)
    result = await db.execute(query)
    return [
        WorkDiaryExpenseOptionResponse(
            id=expense.id,
            date=expense.date,
            description=expense.description,
            amount=_float(expense.amount),
            source=expense.source,
            status=expense.status,
        )
        for expense in result.scalars().all()
    ]


@router.get("/project-meta/{project_id}", response_model=WorkDiaryProjectMetaResponse)
async def get_project_meta(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    project = await _get_project(db, project_id)
    result = await db.execute(select(WorkDiaryProjectMeta).where(WorkDiaryProjectMeta.project_id == project_id))
    return _serialize_meta(project, result.scalar_one_or_none())


@router.put("/project-meta/{project_id}", response_model=WorkDiaryProjectMetaResponse)
async def update_project_meta(
    project_id: int,
    data: WorkDiaryProjectMetaBase,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    project = await _get_project(db, project_id)
    result = await db.execute(select(WorkDiaryProjectMeta).where(WorkDiaryProjectMeta.project_id == project_id))
    meta = result.scalar_one_or_none()
    if not meta:
        meta = WorkDiaryProjectMeta(project_id=project_id)
        db.add(meta)
    for key, value in data.model_dump().items():
        setattr(meta, key, value)
    await db.commit()
    await db.refresh(meta)
    return _serialize_meta(project, meta)


@router.get("/summary", response_model=WorkDiarySummaryResponse)
async def get_summary(
    project_id: int | None = Query(None),
    worker_id: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    entries = await list_entries(project_id, worker_id, date_from, date_to, db, current_user)
    dates = {entry.date for entry in entries}
    workers = {worker_id for entry in entries for worker_id in entry.worker_ids}
    return WorkDiarySummaryResponse(
        entries_count=len(entries),
        days_count=len(dates),
        workers_count=len(workers),
        person_hours=sum(entry.person_hours for entry in entries),
        regular_person_hours=sum(entry.regular_person_hours for entry in entries),
        overtime_person_hours=sum(entry.overtime_person_hours for entry in entries),
        labor_amount=sum(entry.labor_amount for entry in entries),
        payout_amount=sum(entry.payout_amount for entry in entries),
        allowance_amount=sum(entry.allowance_amount for entry in entries),
        material_amount=sum(entry.material_amount for entry in entries),
        stock_material_amount=sum(entry.stock_material_amount for entry in entries),
        linked_material_amount=sum(entry.linked_material_amount for entry in entries),
        total_cost_amount=sum(entry.total_cost_amount for entry in entries),
        billable_amount=sum(entry.billable_amount for entry in entries),
    )


@router.get("/project-costs", response_model=WorkDiaryProjectCostsResponse)
async def get_project_costs(
    project_id: int = Query(...),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Затраты по объекту без двойного счета.

    expenses_amount — все расходы проекта из модуля Расходы (включая материалы,
    привязанные к записям дневника). Сверху добавляются только труд, надбавки и
    материалы со склада, которых в расходах нет.
    """
    project = await _get_project(db, project_id)
    entries = await list_entries(project_id, None, date_from, date_to, db, current_user)
    expense_query = select(func.coalesce(func.sum(Expense.amount), 0)).where(
        Expense.project_id == project_id,
        Expense.source != CASH_TRANSFER_SOURCE,
        visible_expense_condition(),
    )
    if date_from is not None:
        expense_query = expense_query.where(Expense.date >= date_from)
    if date_to is not None:
        expense_query = expense_query.where(Expense.date <= date_to)
    result = await db.execute(expense_query)
    expenses_amount = _float(result.scalar_one())
    labor_amount = sum(entry.labor_amount for entry in entries)
    allowance_amount = sum(entry.allowance_amount for entry in entries)
    stock_material_amount = sum(entry.stock_material_amount for entry in entries)
    linked_material_amount = sum(entry.linked_material_amount for entry in entries)
    return WorkDiaryProjectCostsResponse(
        project_id=project.id,
        project_name=project.name,
        date_from=date_from,
        date_to=date_to,
        entries_count=len(entries),
        expenses_amount=expenses_amount,
        labor_amount=labor_amount,
        allowance_amount=allowance_amount,
        stock_material_amount=stock_material_amount,
        linked_material_amount=linked_material_amount,
        total_cost_amount=expenses_amount + labor_amount + allowance_amount + stock_material_amount,
        billable_amount=sum(entry.billable_amount for entry in entries),
    )
