"""Work diaries and construction diary reports.

Роль модуля — аналитика работ: труд считается по ставкам из дневника, а деньги за
материалы живут в модуле Расходы. Строка материалов либо привязана к расходу проекта
(source="expense", в затраты объекта повторно не входит), либо взята со склада
(source="stock", стоимость — оценка, прибавляется к затратам объекта).

Труд начисляется по режиму оплаты работника за дату (по часам, полный день, день
командировки) — см. backend.work_diary_costing. Сумма заказчику от режима не зависит:
часы на объекте × цена бригады + материалы × коэффициент + услуги.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, update
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
    WorkDiaryEntryWorker,
    WorkDiaryInvoiceAllocation,
    WorkDiaryMaterial,
    WorkDiaryProjectMeta,
    WorkDiaryWorkerDay,
    Worker,
)
from backend.schemas import (
    WORK_DIARY_MATERIAL_UNITS,
    WorkDiaryCostPayout,
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
    WorkDiaryPayoutReconciliation,
    WorkDiaryPayoutReconciliationUpdate,
    WorkDiaryProposalExportRequest,
    WorkDiaryProjectCostsResponse,
    WorkDiaryProjectMetaBase,
    WorkDiaryProjectMetaResponse,
    WorkDiarySummaryResponse,
    WorkDiaryWorkerDayOtherEntry,
    WorkDiaryWorkerDayState,
    WorkDiaryWorkerPayResponse,
)
from backend.income_service import has_invoice_duplicate, invoice_year_from_number, to_number_year_format
from backend.services import allocate_next_invoice_number
from backend.work_diary_costing import (
    DayContext,
    EntryCost,
    PayoutCost,
    WorkerAccrual,
    apply_worker_day_inputs,
    delete_orphan_worker_days,
    entry_cost,
    load_day_context,
    project_payouts,
    set_payout_reconciliation,
    worker_hourly_rate,
)
from backend.work_diary_export import build_work_diary_proposal_xlsx, proposal_filename

router = APIRouter(prefix="/work-diaries", tags=["work-diaries"])

REGULAR_DAY_HOURS = Decimal("8")
# Закон о раде РС, чл. 108: надбавка за сверхурочные — минимум +26%
DEFAULT_OVERTIME_MULTIPLIER = Decimal("1.26")
DEFAULT_MATERIAL_BILLING_MULTIPLIER = Decimal("1.2")
EXPENSE_OPTIONS_LIMIT = 300
INVOICE_ALLOCATE_DETAIL = "Could not allocate a unique invoice number for this year."
MATERIAL_AMOUNT_TOLERANCE = Decimal("0.005")
MATERIAL_QUANTITY_TOLERANCE = Decimal("0.0005")


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
    return worker_hourly_rate(worker)


def _billing_hourly_rate(worker: Worker | None) -> Decimal:
    return _dec(worker.billing_hourly_rate) if worker else Decimal("0")


async def _default_overtime_multiplier(db: AsyncSession) -> Decimal:
    result = await db.execute(select(Enterprise.work_diary_overtime_multiplier).limit(1))
    value = result.scalar_one_or_none()
    return _dec(value) if value else DEFAULT_OVERTIME_MULTIPLIER


async def _default_material_billing_multiplier(db: AsyncSession) -> Decimal:
    result = await db.execute(select(Enterprise.work_diary_material_billing_multiplier).limit(1))
    value = result.scalar_one_or_none()
    return _dec(value) if value else DEFAULT_MATERIAL_BILLING_MULTIPLIER


async def _get_project(db: AsyncSession, project_id: int) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    return project


async def _get_active_project(db: AsyncSession, project_id: int) -> Project:
    project = await _get_project(db, project_id)
    if project.status != "active":
        raise HTTPException(400, "Cannot use completed project")
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


def _validate_worker_days(worker_days, workers: list[Worker]) -> None:
    worker_ids = {worker.id for worker in workers}
    unknown = [item.worker_id for item in worker_days or [] if item.worker_id not in worker_ids]
    if unknown:
        raise HTTPException(400, f"Worker {unknown[0]} is not assigned to this work diary entry")


async def _store_hourly_rate_snapshots(
    db: AsyncSession,
    entry_id: int,
    workers: list[Worker],
    *,
    only_missing: bool = False,
) -> None:
    """Запомнить себестоимость часа каждого работника записи на момент сохранения."""
    for worker in workers:
        statement = (
            update(WorkDiaryEntryWorker)
            .where(WorkDiaryEntryWorker.entry_id == entry_id, WorkDiaryEntryWorker.worker_id == worker.id)
            .values(hourly_rate_snapshot=worker_hourly_rate(worker))
        )
        if only_missing:
            statement = statement.where(WorkDiaryEntryWorker.hourly_rate_snapshot.is_(None))
        await db.execute(statement)


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


@dataclass
class _MaterialExpenseContext:
    expenses_by_id: dict[int, Expense]
    resolved_amounts: list[Decimal]
    resolved_quantities: list[Decimal | None]
    unit_prices: list[Decimal | None]


@dataclass
class _MaterialSourceAllocation:
    quantity: Decimal = Decimal("0")
    amount: Decimal = Decimal("0")


@dataclass
class _MaterialSourceItem:
    expense_id: int
    quantity: Decimal | None
    unit_price: Decimal | None
    total_amount: Decimal


async def _allocated_material_amounts(
    db: AsyncSession,
    expense_ids: set[int] | list[int],
    *,
    exclude_entry_id: int | None = None,
) -> dict[int, Decimal]:
    if not expense_ids:
        return {}
    query = (
        select(WorkDiaryMaterial.expense_id, func.coalesce(func.sum(WorkDiaryMaterial.amount), 0))
        .where(
            WorkDiaryMaterial.source == "expense",
            WorkDiaryMaterial.expense_id.in_(expense_ids),
        )
        .group_by(WorkDiaryMaterial.expense_id)
    )
    if exclude_entry_id is not None:
        query = query.where(WorkDiaryMaterial.entry_id != exclude_entry_id)
    result = await db.execute(query)
    return {expense_id: _dec(amount) for expense_id, amount in result.all()}


async def _allocated_source_item_totals(
    db: AsyncSession,
    expense_ids: set[int] | list[int],
    *,
    exclude_entry_id: int | None = None,
) -> dict[tuple[str, int], _MaterialSourceAllocation]:
    if not expense_ids:
        return {}
    query = select(
        WorkDiaryMaterial.source_item_type,
        WorkDiaryMaterial.source_item_id,
        WorkDiaryMaterial.quantity,
        WorkDiaryMaterial.unit_price_snapshot,
        WorkDiaryMaterial.amount,
    ).where(
        WorkDiaryMaterial.source == "expense",
        WorkDiaryMaterial.expense_id.in_(expense_ids),
        WorkDiaryMaterial.source_item_type.is_not(None),
        WorkDiaryMaterial.source_item_id.is_not(None),
    )
    if exclude_entry_id is not None:
        query = query.where(WorkDiaryMaterial.entry_id != exclude_entry_id)
    result = await db.execute(query)
    allocations: dict[tuple[str, int], _MaterialSourceAllocation] = {}
    for item_type, item_id, quantity, unit_price, amount in result.all():
        key = (item_type, item_id)
        allocation = allocations.setdefault(key, _MaterialSourceAllocation())
        allocated_amount = _dec(amount)
        allocated_quantity = _dec(quantity) if quantity is not None else Decimal("0")
        snapshot_price = _dec(unit_price)
        if quantity is None and snapshot_price > 0 and allocated_amount > 0:
            allocated_quantity = allocated_amount / snapshot_price
        allocation.quantity += allocated_quantity
        allocation.amount += allocated_amount
    return allocations


def _priced_line_amount(item: WorkDiaryMaterialCreate) -> Decimal:
    if item.quantity is None or item.unit_price_snapshot is None:
        return _dec(item.amount)
    return (_dec(item.quantity) * _dec(item.unit_price_snapshot)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _source_item_balance(
    quantity: Decimal | None,
    total_amount: Decimal,
    allocation: _MaterialSourceAllocation,
) -> tuple[Decimal, Decimal | None, Decimal, bool]:
    used_quantity = max(allocation.quantity, Decimal("0"))
    remaining_quantity = max(quantity - used_quantity, Decimal("0")) if quantity is not None and quantity > 0 else None
    used_amount = min(max(allocation.amount, Decimal("0")), total_amount)
    remaining_amount = max(total_amount - used_amount, Decimal("0"))
    is_used = (
        remaining_quantity <= MATERIAL_QUANTITY_TOLERANCE
        if remaining_quantity is not None
        else remaining_amount <= MATERIAL_AMOUNT_TOLERANCE
    )
    return used_quantity, remaining_quantity, remaining_amount, is_used


async def _load_material_expenses(
    db: AsyncSession,
    project_id: int,
    materials: list[WorkDiaryMaterialCreate],
    *,
    entry_id: int | None = None,
) -> _MaterialExpenseContext:
    expense_ids = {item.expense_id for item in materials if item.source == "expense" and item.expense_id}
    if not expense_ids:
        return _MaterialExpenseContext(
            expenses_by_id={},
            resolved_amounts=[_priced_line_amount(item) for item in materials],
            resolved_quantities=[_dec(item.quantity) if item.quantity is not None else None for item in materials],
            unit_prices=[
                _dec(item.unit_price_snapshot) if item.unit_price_snapshot is not None else None for item in materials
            ],
        )
    result = await db.execute(select(Expense).where(Expense.id.in_(expense_ids)).with_for_update())
    expenses_by_id = {expense.id: expense for expense in result.scalars().all()}
    for expense_id in expense_ids:
        expense = expenses_by_id.get(expense_id)
        if not expense:
            raise HTTPException(404, f"Expense not found: {expense_id}")
        if expense.project_id != project_id:
            raise HTTPException(400, "Linked expense belongs to a different project")
        if expense.status == "reversed" or expense.reversal_of_id or expense.reversed_expense_id:
            raise HTTPException(400, "Linked expense is reversed")

    expense_link_modes: dict[int, set[str]] = {}
    whole_expense_counts: dict[int, int] = {}
    for item in materials:
        if item.source != "expense" or not item.expense_id:
            continue
        mode = "position" if item.source_item_type and item.source_item_id else "whole"
        expense_link_modes.setdefault(item.expense_id, set()).add(mode)
        if mode == "whole":
            whole_expense_counts[item.expense_id] = whole_expense_counts.get(item.expense_id, 0) + 1
    if any(len(modes) > 1 for modes in expense_link_modes.values()):
        raise HTTPException(409, "Expense positions cannot be combined with the whole expense.")
    if any(count > 1 for count in whole_expense_counts.values()):
        raise HTTPException(409, "The whole expense cannot be used more than once in a work diary entry.")

    requested_item_keys = [
        (item.source_item_type, item.source_item_id)
        for item in materials
        if item.source == "expense" and item.source_item_type and item.source_item_id
    ]
    item_keys = set(requested_item_keys)
    if len(item_keys) != len(requested_item_keys):
        raise HTTPException(409, "A material position cannot be used more than once in a work diary entry.")
    allocated_source_items = await _allocated_source_item_totals(
        db,
        expense_ids,
        exclude_entry_id=entry_id,
    )

    source_items: dict[tuple[str, int], _MaterialSourceItem] = {}
    expense_item_ids = [item_id for item_type, item_id in item_keys if item_type == "expense_item"]
    if expense_item_ids:
        item_result = await db.execute(select(ExpenseItem).where(ExpenseItem.id.in_(expense_item_ids)))
        for item in item_result.scalars().all():
            source_items[("expense_item", item.id)] = _MaterialSourceItem(
                expense_id=item.expense_id,
                quantity=_dec(item.quantity) if item.quantity is not None else None,
                unit_price=_dec(item.unit_price) if item.unit_price is not None else None,
                total_amount=_dec(item.total_amount),
            )
    receipt_item_ids = [item_id for item_type, item_id in item_keys if item_type == "receipt_item"]
    if receipt_item_ids:
        item_result = await db.execute(
            select(PurchaseReceiptItem, PurchaseReceipt.expense_id)
            .join(PurchaseReceipt, PurchaseReceipt.id == PurchaseReceiptItem.receipt_id)
            .where(PurchaseReceiptItem.id.in_(receipt_item_ids))
        )
        for item, expense_id in item_result.all():
            if expense_id is not None:
                source_items[("receipt_item", item.id)] = _MaterialSourceItem(
                    expense_id=expense_id,
                    quantity=_dec(item.quantity) if item.quantity is not None else None,
                    unit_price=_dec(item.unit_price) if item.unit_price is not None else None,
                    total_amount=_dec(item.total_amount),
                )

    allocated_by_expense = await _allocated_material_amounts(
        db,
        expense_ids,
        exclude_entry_id=entry_id,
    )
    available_by_expense = {
        expense_id: max(
            _dec(expense.amount) - allocated_by_expense.get(expense_id, Decimal("0")),
            Decimal("0"),
        )
        for expense_id, expense in expenses_by_id.items()
    }
    requested_by_expense: dict[int, Decimal] = {}
    resolved_amounts: list[Decimal] = []
    resolved_quantities: list[Decimal | None] = []
    unit_prices: list[Decimal | None] = []
    for item in materials:
        if item.source != "expense" or not item.expense_id:
            resolved_amounts.append(_priced_line_amount(item))
            resolved_quantities.append(_dec(item.quantity) if item.quantity is not None else None)
            unit_prices.append(_dec(item.unit_price_snapshot) if item.unit_price_snapshot is not None else None)
            continue
        key = (item.source_item_type, item.source_item_id) if item.source_item_type and item.source_item_id else None
        source_item = source_items.get(key) if key else None
        if key is not None and source_item is None:
            raise HTTPException(404, "Linked source item not found")
        if source_item is not None and source_item.expense_id != item.expense_id:
            raise HTTPException(400, "Linked source item belongs to a different expense")
        amount = _dec(item.amount)
        quantity = _dec(item.quantity) if item.quantity is not None else None
        unit_price = _dec(item.unit_price_snapshot) if item.unit_price_snapshot is not None else None
        if source_item is not None and key is not None:
            allocation = allocated_source_items.get(key, _MaterialSourceAllocation())
            _, remaining_quantity, remaining_item_amount, is_used = _source_item_balance(
                source_item.quantity,
                source_item.total_amount,
                allocation,
            )
            if is_used:
                raise HTTPException(409, "A material position has no remaining quantity.")
            effective_unit_price = source_item.unit_price
            if (
                (effective_unit_price is None or effective_unit_price <= 0)
                and source_item.quantity is not None
                and source_item.quantity > 0
            ):
                effective_unit_price = source_item.total_amount / source_item.quantity
            if remaining_quantity is not None:
                if quantity is None:
                    if amount > 0 and effective_unit_price is not None and effective_unit_price > 0:
                        quantity = (amount / effective_unit_price).quantize(Decimal("0.001"))
                    else:
                        quantity = remaining_quantity
                if quantity > remaining_quantity + MATERIAL_QUANTITY_TOLERANCE:
                    raise HTTPException(
                        409,
                        (
                            f"Material position has only {remaining_quantity:.3f} units available, "
                            f"but {quantity:.3f} units were requested."
                        ),
                    )
                if quantity >= remaining_quantity - MATERIAL_QUANTITY_TOLERANCE:
                    amount = remaining_item_amount
                elif effective_unit_price is not None and effective_unit_price > 0:
                    amount = (quantity * effective_unit_price).quantize(Decimal("0.01"))
            elif amount <= 0:
                amount = remaining_item_amount
            if amount > remaining_item_amount + MATERIAL_AMOUNT_TOLERANCE:
                raise HTTPException(
                    409,
                    (
                        f"Material position has only {remaining_item_amount:.2f} RSD available, "
                        f"but {amount:.2f} RSD was requested."
                    ),
                )
            unit_price = effective_unit_price
        if amount <= 0 and source_item is None:
            amount = available_by_expense[item.expense_id]
        resolved_amounts.append(amount)
        resolved_quantities.append(quantity)
        unit_prices.append(unit_price)
        requested_by_expense[item.expense_id] = requested_by_expense.get(item.expense_id, Decimal("0")) + amount

    for expense_id, requested_amount in requested_by_expense.items():
        available_amount = available_by_expense[expense_id]
        if requested_amount > available_amount + Decimal("0.005"):
            raise HTTPException(
                409,
                (
                    f"Expense {expense_id} has only {available_amount:.2f} RSD available, "
                    f"but {requested_amount:.2f} RSD was requested."
                ),
            )
    return _MaterialExpenseContext(
        expenses_by_id=expenses_by_id,
        resolved_amounts=resolved_amounts,
        resolved_quantities=resolved_quantities,
        unit_prices=unit_prices,
    )


def _validate_existing_material_links(entry: WorkDiaryEntry, project_id: int) -> None:
    for material in entry.materials:
        expense = material.expense
        if expense is not None and expense.project_id != project_id:
            raise HTTPException(400, "Linked expense belongs to a different project")


def _replace_materials(
    entry: WorkDiaryEntry,
    materials: list[WorkDiaryMaterialCreate],
    context: _MaterialExpenseContext,
) -> None:
    rows: list[WorkDiaryMaterial] = []
    for index, item in enumerate(materials):
        expense = context.expenses_by_id.get(item.expense_id) if item.source == "expense" else None
        description = item.description.strip() or (expense.description if expense else "")
        if not description:
            continue
        rows.append(
            WorkDiaryMaterial(
                line_no=len(rows) + 1,
                description=description,
                quantity=context.resolved_quantities[index],
                unit=item.unit,
                source=item.source,
                expense_id=expense.id if expense else None,
                source_item_type=item.source_item_type if expense else None,
                source_item_id=item.source_item_id if expense else None,
                unit_price_snapshot=context.unit_prices[index],
                amount=context.resolved_amounts[index],
            )
        )
    entry.materials = rows


def _entry_billing_amounts(entry: WorkDiaryEntry) -> dict[str, Decimal]:
    """Материалы и сумма заказчику. От режима оплаты работников не зависят."""
    stock_materials = Decimal("0")
    linked_materials = Decimal("0")
    services = Decimal("0")
    for material in entry.materials:
        if material.source == "service":
            services += _dec(material.amount)
        elif material.source == "expense":
            linked_materials += _dec(material.amount)
        else:
            stock_materials += _dec(material.amount)
    materials = stock_materials + linked_materials
    billing_rate = _dec(entry.team_billing_hourly_rate_snapshot)
    material_billing_multiplier = _dec(entry.material_billing_multiplier)
    billable_materials = materials * material_billing_multiplier
    calculated_billable = _dec(entry.duration_hours) * billing_rate + billable_materials + services
    billable = calculated_billable if entry.billable_amount_override is None else _dec(entry.billable_amount_override)
    return {
        "material_amount": materials,
        "billable_material_amount": billable_materials,
        "billable_service_amount": services,
        "stock_material_amount": stock_materials,
        "linked_material_amount": linked_materials,
        "calculated_billable_amount": calculated_billable,
        "billable_amount": billable,
    }


def _entry_amounts(entry: WorkDiaryEntry, cost: EntryCost) -> dict[str, Decimal]:
    amounts = _entry_billing_amounts(entry)
    labor = cost.labor
    allowances = cost.allowances
    total_cost = labor + allowances + amounts["material_amount"]
    amounts.update(
        {
            "labor_amount": labor,
            "hourly_labor_amount": cost.hourly_labor,
            "day_labor_amount": cost.day_labor,
            "payout_amount": labor + allowances,
            "allowance_amount": allowances,
            "total_cost_amount": total_cost,
            "margin_amount": amounts["billable_amount"] - total_cost,
        }
    )
    return amounts


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
        source_item_type=material.source_item_type,
        source_item_id=material.source_item_id,
        unit_price_snapshot=(
            _float(material.unit_price_snapshot) if material.unit_price_snapshot is not None else None
        ),
        expense_date=getattr(expense, "date", None),
        expense_description=getattr(expense, "description", None),
        amount=_float(material.amount),
    )


def _serialize_worker_pay(cost: EntryCost) -> list[WorkDiaryWorkerPayResponse]:
    return [
        WorkDiaryWorkerPayResponse(
            worker_id=share.worker_id,
            worker_name=share.worker_name,
            pay_mode=share.pay_mode,
            hourly_rate_snapshot=_float(share.hourly_rate),
            day_rate=_float(share.day_rate),
            day_rate_manual=share.day_rate_manual,
            rate_missing=share.rate_missing,
            trip_pricing_mode=share.trip_pricing_mode,
            per_diem_amount=_float(share.per_diem),
            food_amount=_float(share.food),
            lodging_amount=_float(share.lodging),
            day_hours=_float(share.day_hours),
            day_entries_count=share.day_entries,
            share=_float(share.share),
            labor_amount=_float(share.labor),
            allowance_amount=_float(share.allowances),
        )
        for share in cost.workers
    ]


def _serialize_entry(entry: WorkDiaryEntry, context: DayContext) -> WorkDiaryEntryResponse:
    cost = entry_cost(entry, context)
    amounts = _entry_amounts(entry, cost)
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
        hourly_labor_amount=_float(amounts["hourly_labor_amount"]),
        day_labor_amount=_float(amounts["day_labor_amount"]),
        payout_amount=_float(amounts["payout_amount"]),
        allowance_amount=_float(amounts["allowance_amount"]),
        material_amount=_float(amounts["material_amount"]),
        billable_material_amount=_float(amounts["billable_material_amount"]),
        billable_service_amount=_float(amounts["billable_service_amount"]),
        stock_material_amount=_float(amounts["stock_material_amount"]),
        linked_material_amount=_float(amounts["linked_material_amount"]),
        total_cost_amount=_float(amounts["total_cost_amount"]),
        calculated_billable_amount=_float(amounts["calculated_billable_amount"]),
        billable_amount=_float(amounts["billable_amount"]),
        margin_amount=_float(amounts["margin_amount"]),
        invoiced_amount=_float(billing["invoiced_amount"]),
        remaining_billable_amount=_float(billing["remaining_billable_amount"]),
        billing_status=billing["billing_status"],
        invoice_links=billing["invoice_links"],
        per_diem=bool(entry.per_diem),
        per_diem_amount=_float(entry.per_diem_amount),
        lodging_amount=_float(entry.lodging_amount),
        food_allowance=bool(entry.food_allowance),
        food_amount=_float(entry.food_amount),
        is_trip=bool(entry.is_trip),
        travel_hours=_float(entry.travel_hours) if entry.travel_hours is not None else None,
        travel_km=_float(entry.travel_km) if entry.travel_km is not None else None,
        worker_pay=_serialize_worker_pay(cost),
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


async def _load_entries(
    db: AsyncSession,
    *,
    project_id: int | None = None,
    worker_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[WorkDiaryEntry]:
    query = (
        select(WorkDiaryEntry)
        .options(
            selectinload(WorkDiaryEntry.project),
            selectinload(WorkDiaryEntry.workers),
            selectinload(WorkDiaryEntry.materials).selectinload(WorkDiaryMaterial.expense),
            selectinload(WorkDiaryEntry.invoice_allocations).selectinload(WorkDiaryInvoiceAllocation.income),
        )
        .execution_options(populate_existing=True)
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
    return list(result.scalars().all())


async def _serialize_entries(db: AsyncSession, entries: list[WorkDiaryEntry]) -> list[WorkDiaryEntryResponse]:
    context = await load_day_context(db, entries)
    return [_serialize_entry(entry, context) for entry in entries]


async def _serialize_one(db: AsyncSession, entry_id: int) -> WorkDiaryEntryResponse:
    entry = await _get_entry(db, entry_id)
    return (await _serialize_entries(db, [entry]))[0]


@router.get("/entries", response_model=list[WorkDiaryEntryResponse])
async def list_entries(
    project_id: int | None = Query(None),
    worker_id: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    entries = await _load_entries(
        db,
        project_id=project_id,
        worker_id=worker_id,
        date_from=date_from,
        date_to=date_to,
    )
    return await _serialize_entries(db, entries)


@router.post("/export-proposal.xlsx")
async def export_proposal_xlsx(
    data: WorkDiaryProposalExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    query = (
        select(WorkDiaryEntry)
        .options(
            selectinload(WorkDiaryEntry.project).selectinload(Project.client),
            selectinload(WorkDiaryEntry.project).selectinload(Project.work_diary_meta),
            selectinload(WorkDiaryEntry.workers),
            selectinload(WorkDiaryEntry.materials),
        )
        .where(WorkDiaryEntry.id.in_(data.entry_ids))
    )
    result = await db.execute(query)
    entries = list(result.scalars().unique().all())
    entries_by_id = {entry.id: entry for entry in entries}
    missing_ids = [entry_id for entry_id in data.entry_ids if entry_id not in entries_by_id]
    if missing_ids:
        raise HTTPException(404, f"Work diary entry not found: {missing_ids[0]}")

    project_ids = {entry.project_id for entry in entries}
    if len(project_ids) != 1:
        raise HTTPException(400, "Selected work diary entries must belong to one project")

    entries.sort(key=lambda entry: (entry.date, entry.id))
    project = entries[0].project

    enterprise_result = await db.execute(select(Enterprise).order_by(Enterprise.id).limit(1))
    enterprise = enterprise_result.scalar_one_or_none() or Enterprise(name="")

    output = build_work_diary_proposal_xlsx(
        enterprise=enterprise,
        project=project,
        entries=entries,
        prepared_by=current_user.full_name or current_user.username,
        document_date=date.today(),
    )
    filename = proposal_filename(project, entries)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/entries", response_model=WorkDiaryEntryResponse)
async def create_entry(
    data: WorkDiaryEntryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    await _get_active_project(db, data.project_id)
    workers = await _get_workers(db, data.worker_ids)
    _validate_worker_days(data.worker_days, workers)
    material_context = await _load_material_expenses(db, data.project_id, data.materials)
    duration_hours = _calculate_duration_hours(data.start_time, data.end_time, data.duration_hours)
    team_hourly_rate = (
        _dec(data.team_hourly_rate_snapshot)
        if data.team_hourly_rate_snapshot is not None
        else sum((_default_hourly_rate(worker) for worker in workers), Decimal("0"))
    )
    team_billing_hourly_rate = (
        _dec(data.team_billing_hourly_rate_snapshot)
        if data.team_billing_hourly_rate_snapshot is not None
        else sum((_billing_hourly_rate(worker) for worker in workers), Decimal("0"))
    )
    overtime_multiplier = (
        _dec(data.overtime_multiplier)
        if data.overtime_multiplier is not None
        else await _default_overtime_multiplier(db)
    )
    material_billing_multiplier = (
        _dec(data.material_billing_multiplier)
        if data.material_billing_multiplier is not None
        else await _default_material_billing_multiplier(db)
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
        material_billing_multiplier=material_billing_multiplier,
        billable_amount_override=(
            _dec(data.billable_amount_override) if data.billable_amount_override is not None else None
        ),
        is_trip=data.is_trip,
        travel_hours=_dec(data.travel_hours) if data.travel_hours is not None else None,
        travel_km=_dec(data.travel_km) if data.travel_km is not None else None,
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
    _replace_materials(entry, data.materials, material_context)
    db.add(entry)
    await db.flush()
    await _store_hourly_rate_snapshots(db, entry.id, workers)
    if data.worker_days:
        await apply_worker_day_inputs(db, day=entry.date, workers=workers, inputs=data.worker_days)
    await db.commit()
    return await _serialize_one(db, entry.id)


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
    # Начисления за прежнюю дату и прежним работникам могут остаться без записей.
    previous_days = {(worker.id, entry.date) for worker in entry.workers}
    next_project_id = dump.get("project_id", entry.project_id)
    if next_project_id == entry.project_id:
        await _get_project(db, next_project_id)
    else:
        await _get_active_project(db, next_project_id)
    if data.materials is not None:
        material_context = await _load_material_expenses(
            db,
            next_project_id,
            data.materials,
            entry_id=entry.id,
        )
    else:
        material_context = None
        _validate_existing_material_links(entry, next_project_id)
    workers_changed = "worker_ids" in dump
    workers = await _get_workers(db, dump["worker_ids"] or []) if workers_changed else _entry_workers(entry)
    _validate_worker_days(data.worker_days, workers)
    if workers_changed:
        entry.workers = workers

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
    if dump.get("is_trip") is not None:
        entry.is_trip = dump["is_trip"]
    for key in ("travel_hours", "travel_km"):
        if key in dump:
            setattr(entry, key, _dec(dump[key]) if dump[key] is not None else None)
    if "material_billing_multiplier" in dump and dump["material_billing_multiplier"] is not None:
        entry.material_billing_multiplier = _dec(dump["material_billing_multiplier"])
    if "billable_amount_override" in dump:
        entry.billable_amount_override = (
            _dec(dump["billable_amount_override"]) if dump["billable_amount_override"] is not None else None
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
    if "team_billing_hourly_rate_snapshot" in dump:
        if dump["team_billing_hourly_rate_snapshot"] is None:
            team_billing_hourly_rate = sum((_billing_hourly_rate(worker) for worker in workers), Decimal("0"))
        else:
            team_billing_hourly_rate = _dec(dump["team_billing_hourly_rate_snapshot"])
    elif workers_changed:
        team_billing_hourly_rate = sum((_billing_hourly_rate(worker) for worker in workers), Decimal("0"))
    else:
        team_billing_hourly_rate = _dec(entry.team_billing_hourly_rate_snapshot)
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
        _replace_materials(entry, data.materials, material_context)

    await db.flush()
    # Ставки работников перечитываются вместе со ставкой бригады: при смене состава
    # или возврате к авто-ставке. Иначе остаются снимки на момент записи.
    refresh_rates = workers_changed or (
        "team_hourly_rate_snapshot" in dump and dump["team_hourly_rate_snapshot"] is None
    )
    await _store_hourly_rate_snapshots(db, entry.id, workers, only_missing=not refresh_rates)
    if data.worker_days:
        await apply_worker_day_inputs(db, day=entry.date, workers=workers, inputs=data.worker_days)
    await db.flush()
    await delete_orphan_worker_days(db, previous_days)
    await db.commit()
    return await _serialize_one(db, entry.id)


@router.delete("/entries/{entry_id}")
async def delete_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    entry = await _get_entry(db, entry_id)
    _ensure_entry_not_invoiced(entry)
    days = {(worker.id, entry.date) for worker in entry.workers}
    await db.delete(entry)
    await db.flush()
    # Дневная ставка работника переходит к оставшимся записям этого дня, а если их
    # нет — начисление за день удаляется вместе с последней записью.
    await delete_orphan_worker_days(db, days)
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
        source_amount = _entry_billing_amounts(entry)["billable_amount"].quantize(Decimal("0.01"))
        remaining_amount = _entry_billing(entry, source_amount)["remaining_billable_amount"].quantize(Decimal("0.01"))
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
        raise HTTPException(
            409, "The invoice could not be created because the data changed. Refresh and retry."
        ) from exc
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


def _expense_item_option(
    *,
    source_item_type: str,
    source_item_id: int,
    name: str,
    quantity,
    unit_price,
    total_amount,
    allocation: _MaterialSourceAllocation,
) -> WorkDiaryExpenseItemOption:
    source_quantity = _dec(quantity) if quantity is not None else None
    source_total_amount = _dec(total_amount)
    used_quantity, remaining_quantity, remaining_amount, is_used = _source_item_balance(
        source_quantity,
        source_total_amount,
        allocation,
    )
    return WorkDiaryExpenseItemOption(
        source_item_type=source_item_type,
        source_item_id=source_item_id,
        name=name,
        quantity=_float(quantity) if quantity is not None else None,
        unit=_unit_from_item_name(name),
        unit_price=_float(unit_price) if unit_price is not None else None,
        total_amount=_float(source_total_amount),
        used_quantity=_float(used_quantity),
        remaining_quantity=_float(remaining_quantity) if remaining_quantity is not None else None,
        used_amount=_float(min(max(allocation.amount, Decimal("0")), source_total_amount)),
        remaining_amount=_float(remaining_amount),
        is_used=is_used,
    )


async def _load_expense_item_options(
    db: AsyncSession,
    expense_ids: list[int],
    allocated_source_items: dict[tuple[str, int], _MaterialSourceAllocation],
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
        key = ("expense_item", item.id)
        items_by_expense.setdefault(item.expense_id, []).append(
            _expense_item_option(
                source_item_type=key[0],
                source_item_id=item.id,
                name=item.name,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_amount=item.total_amount,
                allocation=allocated_source_items.get(key, _MaterialSourceAllocation()),
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
            key = ("receipt_item", item.id)
            items_by_expense.setdefault(expense_id, []).append(
                _expense_item_option(
                    source_item_type=key[0],
                    source_item_id=item.id,
                    name=item.name,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    total_amount=item.total_amount,
                    allocation=allocated_source_items.get(key, _MaterialSourceAllocation()),
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
    entry_id: int | None = Query(None),
):
    """Расходы проекта, к которым можно привязать строку материалов (с позициями чеков/фактур)."""
    if not isinstance(entry_id, int):
        entry_id = None
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
    expense_ids = [expense.id for expense in expenses]
    allocated_source_items = await _allocated_source_item_totals(
        db,
        expense_ids,
        exclude_entry_id=entry_id,
    )
    items_by_expense = await _load_expense_item_options(db, expense_ids, allocated_source_items)
    allocated_by_expense = await _allocated_material_amounts(
        db,
        expense_ids,
        exclude_entry_id=entry_id,
    )
    return [
        WorkDiaryExpenseOptionResponse(
            id=expense.id,
            date=expense.date,
            description=expense.description,
            amount=_float(expense.amount),
            source=expense.source,
            status=expense.status,
            used_amount=_float(allocated_by_expense.get(expense.id)),
            remaining_amount=_float(
                max(
                    _dec(expense.amount) - allocated_by_expense.get(expense.id, Decimal("0")),
                    Decimal("0"),
                )
            ),
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
        day_labor_amount=sum(entry.day_labor_amount for entry in entries),
        payout_amount=sum(entry.payout_amount for entry in entries),
        allowance_amount=sum(entry.allowance_amount for entry in entries),
        material_amount=sum(entry.material_amount for entry in entries),
        billable_material_amount=sum(entry.billable_material_amount for entry in entries),
        billable_service_amount=sum(entry.billable_service_amount for entry in entries),
        stock_material_amount=sum(entry.stock_material_amount for entry in entries),
        linked_material_amount=sum(entry.linked_material_amount for entry in entries),
        total_cost_amount=sum(entry.total_cost_amount for entry in entries),
        billable_amount=sum(entry.billable_amount for entry in entries),
        invoiced_amount=sum(entry.invoiced_amount for entry in entries),
        remaining_billable_amount=sum(entry.remaining_billable_amount for entry in entries),
    )


def _serialize_cost_payout(item: PayoutCost) -> WorkDiaryCostPayout:
    payout = item.payout
    return WorkDiaryCostPayout(
        payout_id=payout.id,
        worker_id=payout.worker_id,
        worker_name=item.worker_name,
        payout_type=payout.payout_type,
        date=payout.date,
        period_start=payout.period_start,
        period_end=payout.period_end,
        amount=_float(item.amount),
        project_id=payout.project_id,
        project_name=item.project_name,
        diary_reconciled=item.reconciled,
        can_reconcile=bool(payout.period_start and payout.period_end),
        period_accrued_amount=_float(item.period_accrued) if item.period_accrued is not None else None,
        excess_amount=_float(item.excess),
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

    Начисления дневника (труд, командировочные) и материалы со склада — оценка.
    expenses_amount — все расходы проекта из модуля Расходы (включая материалы,
    привязанные к записям дневника, и выплаты работникам). Выплаты, явно
    сопоставленные с начислениями дневника, в итог повторно не входят — кроме части,
    выплаченной сверх начислений. Несопоставленные выплаты входят в итог отдельной
    строкой, чтобы их было видно.
    """
    project = await _get_project(db, project_id)
    entries = await _load_entries(db, project_id=project_id, date_from=date_from, date_to=date_to)
    context = await load_day_context(db, entries)
    costs = [(entry, entry_cost(entry, context)) for entry in entries]
    amounts = [_entry_amounts(entry, cost) for entry, cost in costs]
    project_accruals = [
        WorkerAccrual(
            worker_id=share.worker_id,
            day=entry.date,
            entry_id=entry.id,
            project_id=entry.project_id,
            amount=share.accrued,
        )
        for entry, cost in costs
        for share in cost.workers
    ]

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
    expenses_amount = _dec(result.scalar_one())
    payouts = await project_payouts(
        db,
        project_id=project_id,
        date_from=date_from,
        date_to=date_to,
        project_accruals=project_accruals,
    )

    def total(key: str) -> Decimal:
        return sum((item[key] for item in amounts), Decimal("0"))

    labor_amount = total("labor_amount")
    allowance_amount = total("allowance_amount")
    stock_material_amount = total("stock_material_amount")
    billable_amount = total("billable_amount")
    other_expenses_amount = expenses_amount - payouts.total
    total_cost_amount = (
        labor_amount
        + allowance_amount
        + stock_material_amount
        + other_expenses_amount
        + payouts.unmatched
        + payouts.excess
    )
    return WorkDiaryProjectCostsResponse(
        project_id=project.id,
        project_name=project.name,
        date_from=date_from,
        date_to=date_to,
        entries_count=len(entries),
        person_hours=_float(sum((_dec(entry.duration_hours) * len(entry.workers) for entry in entries), Decimal("0"))),
        expenses_amount=_float(expenses_amount),
        labor_amount=_float(labor_amount),
        hourly_labor_amount=_float(total("hourly_labor_amount")),
        day_labor_amount=_float(total("day_labor_amount")),
        allowance_amount=_float(allowance_amount),
        stock_material_amount=_float(stock_material_amount),
        linked_material_amount=_float(total("linked_material_amount")),
        other_expenses_amount=_float(other_expenses_amount),
        unmatched_payout_amount=_float(payouts.unmatched),
        matched_payout_amount=_float(payouts.matched),
        payout_excess_amount=_float(payouts.excess),
        total_cost_amount=_float(total_cost_amount),
        billable_amount=_float(billable_amount),
        margin_amount=_float(billable_amount - total_cost_amount),
        payouts=[_serialize_cost_payout(item) for item in payouts.payouts],
        reconciliations=[
            WorkDiaryPayoutReconciliation(
                worker_id=group.worker_id,
                worker_name=group.worker_name,
                period_start=group.period_start,
                period_end=group.period_end,
                accrued_amount=_float(group.accrued),
                accrued_in_project_amount=_float(group.accrued_in_project),
                paid_amount=_float(group.paid),
                balance_amount=_float(group.accrued - group.paid),
                payouts=[_serialize_cost_payout(item) for item in group.payouts],
            )
            for group in payouts.groups
        ],
    )


@router.put("/payouts/{payout_id}/reconciliation")
async def update_payout_reconciliation(
    payout_id: int,
    data: WorkDiaryPayoutReconciliationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Явно связать выплату работнику с начислениями дневника за её период или снять связь.

    Связь идёт по работнику и периоду выплаты, а не по совпадению суммы или даты:
    выплаты работника с одним периодом (аванс и окончательный расчёт) сверяются
    вместе, пересекающиеся разные периоды не допускаются.
    """
    payout = await set_payout_reconciliation(db, payout_id, data.reconciled)
    await db.commit()
    return {"ok": True, "payout_id": payout.id, "diary_reconciled": bool(payout.diary_reconciled)}


@router.get("/worker-days", response_model=list[WorkDiaryWorkerDayState])
async def get_worker_days(
    day: date = Query(..., alias="date"),
    worker_ids: str = Query(""),
    entry_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Режимы оплаты работников за дату и их другие записи в этот день.

    Форма записи показывает отсюда, как дневная ставка делится между записями.
    """
    try:
        ids = [int(value) for value in str(worker_ids or "").split(",") if value.strip()]
    except ValueError as exc:
        raise HTTPException(400, "worker_ids must be a comma-separated list of integers") from exc
    if not isinstance(entry_id, int):
        entry_id = None
    workers = await _get_workers(db, ids)
    if not workers:
        return []
    worker_ids_set = [worker.id for worker in workers]
    result = await db.execute(
        select(WorkDiaryWorkerDay).where(
            WorkDiaryWorkerDay.date == day,
            WorkDiaryWorkerDay.worker_id.in_(worker_ids_set),
        )
    )
    worker_days = {row.worker_id: row for row in result.scalars().all()}
    other_query = (
        select(
            WorkDiaryEntryWorker.worker_id,
            WorkDiaryEntry.id,
            WorkDiaryEntry.project_id,
            Project.name,
            WorkDiaryEntry.duration_hours,
        )
        .join(WorkDiaryEntry, WorkDiaryEntry.id == WorkDiaryEntryWorker.entry_id)
        .outerjoin(Project, Project.id == WorkDiaryEntry.project_id)
        .where(WorkDiaryEntry.date == day, WorkDiaryEntryWorker.worker_id.in_(worker_ids_set))
        .order_by(WorkDiaryEntry.id)
    )
    if entry_id is not None:
        other_query = other_query.where(WorkDiaryEntry.id != entry_id)
    others: dict[int, list[WorkDiaryWorkerDayOtherEntry]] = {}
    for worker_id, other_id, other_project_id, project_name, duration_hours in (await db.execute(other_query)).all():
        others.setdefault(worker_id, []).append(
            WorkDiaryWorkerDayOtherEntry(
                id=other_id,
                project_id=other_project_id,
                project_name=project_name,
                duration_hours=_float(duration_hours),
            )
        )
    states = []
    for worker in workers:
        row = worker_days.get(worker.id)
        other_entries = others.get(worker.id, [])
        states.append(
            WorkDiaryWorkerDayState(
                worker_id=worker.id,
                worker_name=worker.name,
                exists=row is not None,
                pay_mode=row.pay_mode if row is not None else "hourly",
                day_rate=_float(row.day_rate) if row is not None else 0,
                day_rate_manual=bool(row.day_rate_manual) if row is not None else False,
                trip_pricing_mode=row.trip_pricing_mode if row is not None else None,
                per_diem_amount=_float(row.per_diem_amount) if row is not None else 0,
                food_amount=_float(row.food_amount) if row is not None else 0,
                lodging_amount=_float(row.lodging_amount) if row is not None else 0,
                other_entries=other_entries,
                other_hours=sum(item.duration_hours for item in other_entries),
            )
        )
    return states
