"""Work diaries and construction diary reports."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.auth import get_current_user_required, require_edit_access
from backend.database import get_db
from backend.models import Project, User, WorkDiaryEntry, WorkDiaryMaterial, WorkDiaryProjectMeta, Worker
from backend.schemas import (
    WorkDiaryEntryCreate,
    WorkDiaryEntryResponse,
    WorkDiaryEntryUpdate,
    WorkDiaryMaterialCreate,
    WorkDiaryMaterialResponse,
    WorkDiaryProjectMetaBase,
    WorkDiaryProjectMetaResponse,
    WorkDiarySummaryResponse,
)

router = APIRouter(prefix="/work-diaries", tags=["work-diaries"])

REGULAR_DAY_HOURS = Decimal("8")


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


def _calculate_hours(start_time: str | None, end_time: str | None, explicit_hours: float | None) -> Decimal:
    start_hours = _time_to_hours(start_time)
    end_hours = _time_to_hours(end_time)
    if start_hours is not None and end_hours is not None:
        hours = end_hours - start_hours
        if hours <= 0:
            raise HTTPException(400, "End time must be after start time")
        return hours.quantize(Decimal("0.01"))
    if explicit_hours is None:
        raise HTTPException(400, "Provide hours or both start_time and end_time")
    return _dec(explicit_hours).quantize(Decimal("0.01"))


def _default_hourly_rate(worker: Worker | None) -> Decimal:
    if not worker:
        return Decimal("0")
    day_rate = _dec(worker.regular_day_rate)
    return (day_rate / REGULAR_DAY_HOURS).quantize(Decimal("0.01")) if day_rate > 0 else Decimal("0")


async def _get_project(db: AsyncSession, project_id: int) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    return project


async def _get_worker(db: AsyncSession, worker_id: int | None) -> Worker | None:
    if worker_id is None:
        return None
    result = await db.execute(select(Worker).where(Worker.id == worker_id))
    worker = result.scalar_one_or_none()
    if not worker:
        raise HTTPException(404, "Worker not found")
    return worker


async def _get_entry(db: AsyncSession, entry_id: int) -> WorkDiaryEntry:
    result = await db.execute(
        select(WorkDiaryEntry)
        .options(
            selectinload(WorkDiaryEntry.project),
            selectinload(WorkDiaryEntry.worker),
            selectinload(WorkDiaryEntry.materials),
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
    hours: Decimal,
    hourly_rate: Decimal,
    overtime_multiplier: Decimal,
) -> None:
    regular_hours = min(hours, REGULAR_DAY_HOURS)
    overtime_hours = max(hours - REGULAR_DAY_HOURS, Decimal("0"))
    entry.hours = hours
    entry.regular_hours = regular_hours
    entry.overtime_hours = overtime_hours
    entry.hourly_rate_snapshot = hourly_rate
    entry.overtime_multiplier = overtime_multiplier


def _replace_materials(entry: WorkDiaryEntry, materials: list[WorkDiaryMaterialCreate]) -> None:
    entry.materials = [
        WorkDiaryMaterial(
            line_no=index + 1,
            description=item.description.strip(),
            quantity=item.quantity,
            amount=_dec(item.amount),
        )
        for index, item in enumerate(materials)
        if item.description.strip()
    ]


def _entry_amounts(entry: WorkDiaryEntry, meta: WorkDiaryProjectMeta | None = None) -> dict[str, Decimal]:
    labor = _dec(entry.regular_hours) * _dec(entry.hourly_rate_snapshot)
    labor += _dec(entry.overtime_hours) * _dec(entry.hourly_rate_snapshot) * _dec(entry.overtime_multiplier)
    allowances = _dec(entry.lodging_amount)
    if entry.per_diem:
        allowances += _dec(entry.per_diem_amount)
    if entry.food_allowance:
        allowances += _dec(entry.food_amount)
    materials = sum((_dec(material.amount) for material in entry.materials), Decimal("0"))
    billing_rate = _dec(getattr(meta, "billing_hourly_rate", 0))
    billable = _dec(entry.hours) * billing_rate + materials
    return {
        "labor_amount": labor,
        "payout_amount": labor + (_dec(entry.per_diem_amount) if entry.per_diem else Decimal("0")),
        "allowance_amount": allowances,
        "material_amount": materials,
        "total_cost_amount": labor + allowances + materials,
        "billable_amount": billable,
    }


def _serialize_material(material: WorkDiaryMaterial) -> WorkDiaryMaterialResponse:
    return WorkDiaryMaterialResponse(
        id=material.id,
        line_no=material.line_no,
        description=material.description,
        quantity=material.quantity,
        amount=_float(material.amount),
    )


async def _meta_by_project_ids(db: AsyncSession, project_ids: set[int]) -> dict[int, WorkDiaryProjectMeta]:
    if not project_ids:
        return {}
    result = await db.execute(select(WorkDiaryProjectMeta).where(WorkDiaryProjectMeta.project_id.in_(project_ids)))
    return {meta.project_id: meta for meta in result.scalars().all()}


def _serialize_entry(entry: WorkDiaryEntry, meta: WorkDiaryProjectMeta | None = None) -> WorkDiaryEntryResponse:
    amounts = _entry_amounts(entry, meta)
    return WorkDiaryEntryResponse(
        id=entry.id,
        date=entry.date,
        project_id=entry.project_id,
        project_name=getattr(getattr(entry, "project", None), "name", None),
        worker_id=entry.worker_id,
        worker_name=getattr(getattr(entry, "worker", None), "name", None),
        description=entry.description,
        start_time=entry.start_time,
        end_time=entry.end_time,
        hours=_float(entry.hours),
        regular_hours=_float(entry.regular_hours),
        overtime_hours=_float(entry.overtime_hours),
        hourly_rate_snapshot=_float(entry.hourly_rate_snapshot),
        overtime_multiplier=_float(entry.overtime_multiplier),
        labor_amount=_float(amounts["labor_amount"]),
        payout_amount=_float(amounts["payout_amount"]),
        allowance_amount=_float(amounts["allowance_amount"]),
        material_amount=_float(amounts["material_amount"]),
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
        selectinload(WorkDiaryEntry.worker),
        selectinload(WorkDiaryEntry.materials),
    )
    if project_id is not None:
        query = query.where(WorkDiaryEntry.project_id == project_id)
    if worker_id is not None:
        query = query.where(WorkDiaryEntry.worker_id == worker_id)
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
    worker = await _get_worker(db, data.worker_id)
    hours = _calculate_hours(data.start_time, data.end_time, data.hours)
    hourly_rate = _dec(data.hourly_rate_snapshot) if data.hourly_rate_snapshot is not None else _default_hourly_rate(worker)
    entry = WorkDiaryEntry(
        date=data.date,
        project_id=data.project_id,
        worker_id=data.worker_id,
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
    _apply_calculated_fields(
        entry,
        hours=hours,
        hourly_rate=hourly_rate,
        overtime_multiplier=_dec(data.overtime_multiplier),
    )
    _replace_materials(entry, data.materials)
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
    worker = await _get_worker(db, dump.get("worker_id", entry.worker_id))

    for key in (
        "date",
        "project_id",
        "worker_id",
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

    hours = _calculate_hours(entry.start_time, entry.end_time, dump.get("hours", _float(entry.hours)))
    if "hourly_rate_snapshot" in dump and dump["hourly_rate_snapshot"] is not None:
        hourly_rate = _dec(dump["hourly_rate_snapshot"])
    elif entry.hourly_rate_snapshot is not None:
        hourly_rate = _dec(entry.hourly_rate_snapshot)
    else:
        hourly_rate = _default_hourly_rate(worker)
    overtime_multiplier = _dec(dump.get("overtime_multiplier", entry.overtime_multiplier))
    _apply_calculated_fields(entry, hours=hours, hourly_rate=hourly_rate, overtime_multiplier=overtime_multiplier)
    if data.materials is not None:
        _replace_materials(entry, data.materials)

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
    workers = {entry.worker_id for entry in entries if entry.worker_id is not None}
    return WorkDiarySummaryResponse(
        entries_count=len(entries),
        days_count=len(dates),
        workers_count=len(workers),
        hours=sum(entry.hours for entry in entries),
        regular_hours=sum(entry.regular_hours for entry in entries),
        overtime_hours=sum(entry.overtime_hours for entry in entries),
        labor_amount=sum(entry.labor_amount for entry in entries),
        allowance_amount=sum(entry.allowance_amount for entry in entries),
        material_amount=sum(entry.material_amount for entry in entries),
        total_cost_amount=sum(entry.total_cost_amount for entry in entries),
        billable_amount=sum(entry.billable_amount for entry in entries),
    )
