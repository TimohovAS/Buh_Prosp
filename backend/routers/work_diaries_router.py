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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.auth import get_current_user_required, require_edit_access
from backend.database import get_db
from backend.expense_service import CASH_TRANSFER_SOURCE, visible_expense_condition
from backend.models import (
    Contract,
    Enterprise,
    Expense,
    ExpenseItem,
    Income,
    IncomeItem,
    Project,
    PurchaseReceipt,
    PurchaseReceiptItem,
    User,
    WorkDiaryEntry,
    WorkDiaryInvoiceAllocation,
    WorkDiaryMaterial,
    WorkDiaryProjectMeta,
    Worker,
)
from backend.schemas import (
    WORK_DIARY_MATERIAL_UNITS,
    WorkDiaryEntryCreate,
    WorkDiaryEntryResponse,
    WorkDiaryEntryUpdate,
    WorkDiaryExpenseItemOption,
    WorkDiaryExpenseOptionResponse,
    WorkDiaryInvoiceCreate,
    WorkDiaryInvoiceCreateResponse,
    WorkDiaryInvoiceLinkResponse,
    WorkDiaryMaterialCreate,
    WorkDiaryMaterialResponse,
    WorkDiaryProjectCostsResponse,
    WorkDiaryProjectMetaBase,
    WorkDiaryProjectMetaResponse,
    WorkDiarySummaryResponse,
)
from backend.income_service import has_invoice_duplicate, invoice_year_from_number, to_number_year_format
from backend.services import allocate_next_invoice_number

router = APIRouter(prefix="/work-diaries", tags=["work-diaries"])

REGULAR_DAY_HOURS = Decimal("8")
# Закон о раде РС, чл. 108: надбавка за сверхурочные — минимум +26%
DEFAULT_OVERTIME_MULTIPLIER = Decimal("1.26")
EXPENSE_OPTIONS_LIMIT = 300
INVOICE_ALLOCATE_DETAIL = "Could not allocate a unique invoice number for this year."


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


def _billing_hourly_rate(worker: Worker | None) -> Decimal:
    return _dec(worker.billing_hourly_rate) if worker else Decimal("0")


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
            selectinload(WorkDiaryEntry.invoice_allocations).selectinload(WorkDiaryInvoiceAllocation.income),
        )
        .execution_options(populate_existing=True)
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
    team_billing_hourly_rate: Decimal,
    overtime_multiplier: Decimal,
) -> None:
    entry.duration_hours = duration_hours
    entry.regular_duration_hours = min(duration_hours, REGULAR_DAY_HOURS)
    entry.overtime_duration_hours = max(duration_hours - REGULAR_DAY_HOURS, Decimal("0"))
    entry.team_hourly_rate_snapshot = team_hourly_rate
    entry.team_billing_hourly_rate_snapshot = team_billing_hourly_rate
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


def _entry_amounts(entry: WorkDiaryEntry) -> dict[str, Decimal]:
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
    billing_rate = _dec(entry.team_billing_hourly_rate_snapshot)
    material_billing_multiplier = _dec(entry.material_billing_multiplier)
    billable_materials = materials * material_billing_multiplier
    calculated_billable = _dec(entry.duration_hours) * billing_rate + billable_materials
    billable = (
        calculated_billable
        if entry.billable_amount_override is None
        else _dec(entry.billable_amount_override)
    )
    return {
        "labor_amount": labor,
        "payout_amount": labor + allowances,
        "allowance_amount": allowances,
        "material_amount": materials,
        "billable_material_amount": billable_materials,
        "stock_material_amount": stock_materials,
        "linked_material_amount": linked_materials,
        "total_cost_amount": labor + allowances + materials,
        "calculated_billable_amount": calculated_billable,
        "billable_amount": billable,
    }


def _active_invoice_allocations(entry: WorkDiaryEntry) -> list[WorkDiaryInvoiceAllocation]:
    return [
        allocation
        for allocation in entry.invoice_allocations
        if allocation.income is not None and allocation.income.status != "cancelled"
    ]


def _entry_billing(entry: WorkDiaryEntry, billable_amount: Decimal) -> dict:
    active_allocations = _active_invoice_allocations(entry)
    invoiced_amount = sum((_dec(allocation.amount) for allocation in active_allocations), Decimal("0"))
    remaining_amount = max(billable_amount - invoiced_amount, Decimal("0"))
    if invoiced_amount <= 0:
        billing_status = "not_invoiced"
    elif remaining_amount > 0:
        billing_status = "partially_invoiced"
    else:
        billing_status = "invoiced"
    links = [
        WorkDiaryInvoiceLinkResponse(
            income_id=allocation.income_id,
            invoice_number=allocation.income.invoice_number,
            invoice_status=allocation.income.status,
            amount=_float(allocation.amount),
        )
        for allocation in entry.invoice_allocations
        if allocation.income is not None
    ]
    return {
        "invoiced_amount": invoiced_amount,
        "remaining_billable_amount": remaining_amount,
        "billing_status": billing_status,
        "invoice_links": links,
    }


def _ensure_entry_not_invoiced(entry: WorkDiaryEntry) -> None:
    if _active_invoice_allocations(entry):
        raise HTTPException(
            409,
            "Work diary entry is linked to an active invoice. Cancel the invoice before changing the entry.",
        )


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


def _serialize_entry(entry: WorkDiaryEntry) -> WorkDiaryEntryResponse:
    amounts = _entry_amounts(entry)
    billing = _entry_billing(entry, amounts["billable_amount"])
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
        team_billing_hourly_rate_snapshot=_float(entry.team_billing_hourly_rate_snapshot),
        material_billing_multiplier=_float(entry.material_billing_multiplier),
        billable_amount_override=(
            _float(entry.billable_amount_override) if entry.billable_amount_override is not None else None
        ),
        overtime_multiplier=_float(entry.overtime_multiplier),
        labor_amount=_float(amounts["labor_amount"]),
        payout_amount=_float(amounts["payout_amount"]),
        allowance_amount=_float(amounts["allowance_amount"]),
        material_amount=_float(amounts["material_amount"]),
        billable_material_amount=_float(amounts["billable_material_amount"]),
        stock_material_amount=_float(amounts["stock_material_amount"]),
        linked_material_amount=_float(amounts["linked_material_amount"]),
        total_cost_amount=_float(amounts["total_cost_amount"]),
        calculated_billable_amount=_float(amounts["calculated_billable_amount"]),
        billable_amount=_float(amounts["billable_amount"]),
        invoiced_amount=_float(billing["invoiced_amount"]),
        remaining_billable_amount=_float(billing["remaining_billable_amount"]),
        billing_status=billing["billing_status"],
        invoice_links=billing["invoice_links"],
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
        selectinload(WorkDiaryEntry.invoice_allocations).selectinload(WorkDiaryInvoiceAllocation.income),
    ).execution_options(populate_existing=True)
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
    return [_serialize_entry(entry) for entry in entries]


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
    team_billing_hourly_rate = sum((_billing_hourly_rate(worker) for worker in workers), Decimal("0"))
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
        material_billing_multiplier=_dec(data.material_billing_multiplier),
        billable_amount_override=(
            _dec(data.billable_amount_override) if data.billable_amount_override is not None else None
        ),
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
        team_billing_hourly_rate=team_billing_hourly_rate,
        overtime_multiplier=overtime_multiplier,
    )
    _replace_materials(entry, data.materials, material_expenses)
    db.add(entry)
    await db.commit()
    entry = await _get_entry(db, entry.id)
    return _serialize_entry(entry)


@router.patch("/entries/{entry_id}", response_model=WorkDiaryEntryResponse)
async def update_entry(
    entry_id: int,
    data: WorkDiaryEntryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    entry = await _get_entry(db, entry_id)
    _ensure_entry_not_invoiced(entry)
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
    if "material_billing_multiplier" in dump and dump["material_billing_multiplier"] is not None:
        entry.material_billing_multiplier = _dec(dump["material_billing_multiplier"])
    if "billable_amount_override" in dump:
        entry.billable_amount_override = (
            _dec(dump["billable_amount_override"])
            if dump["billable_amount_override"] is not None
            else None
        )

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
    team_billing_hourly_rate = sum((_billing_hourly_rate(worker) for worker in workers), Decimal("0"))
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
        team_billing_hourly_rate=team_billing_hourly_rate,
        overtime_multiplier=overtime_multiplier,
    )
    if data.materials is not None:
        _replace_materials(entry, data.materials, material_expenses)

    await db.commit()
    entry = await _get_entry(db, entry.id)
    return _serialize_entry(entry)


@router.delete("/entries/{entry_id}")
async def delete_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    entry = await _get_entry(db, entry_id)
    _ensure_entry_not_invoiced(entry)
    await db.delete(entry)
    await db.commit()
    return {"ok": True}


async def _invoice_number(
    db: AsyncSession,
    issued_date: date,
    requested_number: str | None,
) -> tuple[str, int]:
    year = issued_date.year
    normalized_requested = (requested_number or "").strip()
    if normalized_requested:
        invoice_number = to_number_year_format(normalized_requested, year)
        invoice_year = invoice_year_from_number(invoice_number) or year
        if await has_invoice_duplicate(db, invoice_number, invoice_year):
            raise HTTPException(409, "Invoice number already exists for this year.")
        return invoice_number, invoice_year

    for _ in range(50):
        sequence_number = await allocate_next_invoice_number(db, year)
        invoice_number = f"{sequence_number:04d}-{year}"
        if not await has_invoice_duplicate(db, invoice_number, year):
            return invoice_number, year
    raise HTTPException(409, INVOICE_ALLOCATE_DETAIL)


@router.post("/invoices", response_model=WorkDiaryInvoiceCreateResponse)
async def create_invoice_from_entries(
    data: WorkDiaryInvoiceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    entry_ids = [line.entry_id for line in data.lines]
    result = await db.execute(
        select(WorkDiaryEntry)
        .options(
            selectinload(WorkDiaryEntry.project).selectinload(Project.client),
            selectinload(WorkDiaryEntry.workers),
            selectinload(WorkDiaryEntry.materials).selectinload(WorkDiaryMaterial.expense),
            selectinload(WorkDiaryEntry.invoice_allocations).selectinload(WorkDiaryInvoiceAllocation.income),
        )
        .execution_options(populate_existing=True)
        .where(WorkDiaryEntry.id.in_(entry_ids))
    )
    entries_by_id = {entry.id: entry for entry in result.scalars().all()}
    missing_ids = [entry_id for entry_id in entry_ids if entry_id not in entries_by_id]
    if missing_ids:
        raise HTTPException(404, f"Work diary entry not found: {missing_ids[0]}")

    entries = [entries_by_id[entry_id] for entry_id in entry_ids]
    project_ids = {entry.project_id for entry in entries}
    if len(project_ids) != 1:
        raise HTTPException(400, "All selected work diary entries must belong to the same project.")
    project = entries[0].project
    if project is None or project.client_id is None or project.client is None:
        raise HTTPException(400, "The selected project must have a client before an invoice can be created.")
    if project.is_internal:
        raise HTTPException(400, "Internal projects cannot be invoiced.")

    contract = None
    if data.contract_id is not None:
        contract_result = await db.execute(select(Contract).where(Contract.id == data.contract_id))
        contract = contract_result.scalar_one_or_none()
        if contract is None:
            raise HTTPException(404, "Contract not found")
        if contract.client_id != project.client_id:
            raise HTTPException(400, "The selected contract belongs to a different client.")
        if contract.project_id is not None and contract.project_id != project.id:
            raise HTTPException(400, "The selected contract belongs to a different project.")
        if contract.status == "cancelled":
            raise HTTPException(400, "A cancelled contract cannot be used for an invoice.")

    normalized_lines: list[tuple[WorkDiaryEntry, str, Decimal, Decimal]] = []
    for line in data.lines:
        entry = entries_by_id[line.entry_id]
        source_amount = _entry_amounts(entry)["billable_amount"].quantize(Decimal("0.01"))
        remaining_amount = _entry_billing(entry, source_amount)["remaining_billable_amount"].quantize(
            Decimal("0.01")
        )
        line_amount = _dec(line.amount).quantize(Decimal("0.01"))
        if remaining_amount <= 0:
            raise HTTPException(409, f"Work diary entry {entry.id} is already fully invoiced.")
        if line_amount > remaining_amount:
            raise HTTPException(
                409,
                f"Invoice amount for work diary entry {entry.id} exceeds the remaining billable amount.",
            )
        normalized_lines.append((entry, line.name[:500], line_amount, source_amount))

    invoice_number, invoice_year = await _invoice_number(db, data.issued_date, data.invoice_number)
    amount_rsd = sum((line[2] for line in normalized_lines), Decimal("0"))
    period_start = min(entry.date for entry in entries)
    period_end = max(entry.date for entry in entries)
    period_label = period_start.strftime("%d.%m.%Y")
    if period_end != period_start:
        period_label = f"{period_label} - {period_end.strftime('%d.%m.%Y')}"
    description = (data.description or f"Radovi po projektu {project.name}, period {period_label}").strip()[:500]
    income_type = {
        "advance": "advance",
        "intermediate": "intermediate",
        "closing": "final",
    }.get(data.contract_payment_type or "", "other")
    income = Income(
        issued_date=data.issued_date,
        due_date=data.due_date,
        invoice_number=invoice_number,
        invoice_year=invoice_year,
        client_id=project.client_id,
        client_name=project.client.name,
        contract_id=contract.id if contract is not None else None,
        contract_payment_type=data.contract_payment_type if contract is not None else None,
        description=description,
        amount_rsd=amount_rsd,
        currency="RSD",
        exchange_rate=1.0,
        is_paid=False,
        paid_amount=Decimal("0"),
        status="issued",
        project_id=project.id,
        income_type=income_type,
        note=data.note,
        created_by=current_user.id,
    )
    try:
        db.add(income)
        await db.flush()

        for line_no, (entry, line_name, line_amount, source_amount) in enumerate(normalized_lines, start=1):
            income_item = IncomeItem(
                income_id=income.id,
                line_no=line_no,
                name=line_name,
                quantity=Decimal("1"),
                unit="usl",
                unit_price=line_amount,
                total_amount=line_amount,
                tax_category="SS",
                tax_rate=Decimal("0"),
                note=f"Work diary entry #{entry.id}, {entry.date.strftime('%d.%m.%Y')}",
            )
            db.add(income_item)
            await db.flush()
            db.add(
                WorkDiaryInvoiceAllocation(
                    work_diary_entry_id=entry.id,
                    income_id=income.id,
                    income_item_id=income_item.id,
                    amount=line_amount,
                    source_amount_snapshot=source_amount,
                    created_by=current_user.id,
                )
            )

        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "The invoice could not be created because the data changed. Refresh and retry.") from exc
    return WorkDiaryInvoiceCreateResponse(
        income_id=income.id,
        invoice_number=income.invoice_number,
        amount_rsd=income.amount_rsd,
        entries_count=len(normalized_lines),
    )


def _unit_from_item_name(name: str) -> str | None:
    """Чеки ПУ пишут единицу в конце названия: «KLEMA ... /kom» — вытаскиваем её."""
    tail = name.rsplit("/", 1)
    if len(tail) != 2:
        return None
    unit = tail[1].strip().lower()
    return unit if unit in WORK_DIARY_MATERIAL_UNITS else None


async def _load_expense_item_options(
    db: AsyncSession, expense_ids: list[int]
) -> dict[int, list[WorkDiaryExpenseItemOption]]:
    """Позиции расходов: свои позиции фактуры, иначе позиции связанного кассового чека."""
    if not expense_ids:
        return {}
    items_by_expense: dict[int, list[WorkDiaryExpenseItemOption]] = {}

    expense_items_result = await db.execute(
        select(ExpenseItem)
        .where(ExpenseItem.expense_id.in_(expense_ids))
        .order_by(ExpenseItem.expense_id, ExpenseItem.line_no, ExpenseItem.id)
    )
    for item in expense_items_result.scalars().all():
        items_by_expense.setdefault(item.expense_id, []).append(
            WorkDiaryExpenseItemOption(
                name=item.name,
                quantity=_float(item.quantity) if item.quantity is not None else None,
                unit=_unit_from_item_name(item.name),
                unit_price=_float(item.unit_price) if item.unit_price is not None else None,
                total_amount=_float(item.total_amount),
            )
        )

    remaining_ids = [expense_id for expense_id in expense_ids if expense_id not in items_by_expense]
    if remaining_ids:
        receipt_items_result = await db.execute(
            select(PurchaseReceipt.expense_id, PurchaseReceiptItem)
            .join(PurchaseReceiptItem, PurchaseReceiptItem.receipt_id == PurchaseReceipt.id)
            .where(PurchaseReceipt.expense_id.in_(remaining_ids))
            .order_by(PurchaseReceiptItem.receipt_id, PurchaseReceiptItem.line_no, PurchaseReceiptItem.id)
        )
        for expense_id, item in receipt_items_result.all():
            items_by_expense.setdefault(expense_id, []).append(
                WorkDiaryExpenseItemOption(
                    name=item.name,
                    quantity=_float(item.quantity) if item.quantity is not None else None,
                    unit=_unit_from_item_name(item.name),
                    unit_price=_float(item.unit_price) if item.unit_price is not None else None,
                    total_amount=_float(item.total_amount),
                )
            )
    return items_by_expense


@router.get("/expense-options", response_model=list[WorkDiaryExpenseOptionResponse])
async def list_expense_options(
    project_id: int = Query(...),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Расходы проекта, к которым можно привязать строку материалов (с позициями чеков/фактур)."""
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
    expenses = result.scalars().all()
    items_by_expense = await _load_expense_item_options(db, [expense.id for expense in expenses])
    return [
        WorkDiaryExpenseOptionResponse(
            id=expense.id,
            date=expense.date,
            description=expense.description,
            amount=_float(expense.amount),
            source=expense.source,
            status=expense.status,
            items=items_by_expense.get(expense.id, []),
        )
        for expense in expenses
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
        billable_material_amount=sum(entry.billable_material_amount for entry in entries),
        stock_material_amount=sum(entry.stock_material_amount for entry in entries),
        linked_material_amount=sum(entry.linked_material_amount for entry in entries),
        total_cost_amount=sum(entry.total_cost_amount for entry in entries),
        billable_amount=sum(entry.billable_amount for entry in entries),
        invoiced_amount=sum(entry.invoiced_amount for entry in entries),
        remaining_billable_amount=sum(entry.remaining_billable_amount for entry in entries),
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
