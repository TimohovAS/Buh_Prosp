from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.auth import get_current_user_required, require_edit_access
from backend.database import get_db
from backend.db_utils import get_project_or_404
from backend.decimal_utils import ZERO_DECIMAL, decimal_sum, to_decimal
from backend.models import Client, Contract, ContractItem, Project, User
from backend.schemas import ContractCreate, ContractItemCreate, ContractItemResponse, ContractResponse, ContractUpdate
from backend.state_machine import initialize_project_status

router = APIRouter(prefix="/contracts", tags=["contracts"])


@router.get("", response_model=list[ContractResponse])
async def list_contracts(
    client_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: Optional[int] = Query(None, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    query = select(Contract).options(
        selectinload(Contract.client),
        selectinload(Contract.items),
        selectinload(Contract.incomes),
        selectinload(Contract.expenses),
    )
    if client_id:
        query = query.where(Contract.client_id == client_id)
    if status:
        query = query.where(Contract.status == status)
    if year:
        query = query.where(Contract.date >= date(year, 1, 1), Contract.date <= date(year, 12, 31))
    query = query.order_by(Contract.date.desc(), Contract.id.desc())
    if skip:
        query = query.offset(skip)
    if limit is not None:
        query = query.limit(limit)
    result = await db.execute(query)
    return [_contract_to_response(contract) for contract in result.scalars().all()]


@router.get("/next-number/")
async def next_contract_number(
    year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    selected_year = year or date.today().year
    result = await db.execute(
        select(Contract).where(Contract.date >= date(selected_year, 1, 1), Contract.date <= date(selected_year, 12, 31))
    )
    contracts = result.scalars().all()
    numbers = []
    for contract in contracts:
        parts = str(contract.number).split("-")
        if len(parts) == 2 and parts[1].isdigit():
            numbers.append(int(parts[1]))
    next_num = max(numbers, default=0) + 1
    return {"number": f"{selected_year}-{next_num:04d}"}


@router.post("/create", response_model=ContractResponse)
async def create_contract(
    data: ContractCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    result = await db.execute(select(Client).where(Client.id == data.client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(404, "Client not found")

    amount = ZERO_DECIMAL
    items_data: list[tuple[ContractItemCreate, float, int]] = []
    if data.items:
        for index, item in enumerate(data.items):
            item_amount = to_decimal(item.quantity) * to_decimal(item.price)
            amount += item_amount
            items_data.append((item, item_amount, index))
    else:
        amount = data.amount

    project_id = data.project_id
    if project_id:
        await get_project_or_404(db, project_id)
    else:
        project_name = data.subject or f"Project: {data.number}"
        new_project = Project(
            name=project_name[:200],
            client_id=data.client_id,
            is_internal=False,
        )
        initialize_project_status(new_project, "active")
        db.add(new_project)
        await db.flush()
        project_id = new_project.id

    contract = Contract(
        number=data.number,
        date=data.date,
        client_id=data.client_id,
        project_id=project_id,
        contract_type=data.contract_type,
        subject=data.subject,
        amount=amount,
        currency=data.currency,
        validity_start=data.validity_start,
        validity_end=data.validity_end,
        status=data.status,
        note=data.note,
        created_by=current_user.id,
    )
    db.add(contract)
    await db.flush()

    for item, item_amount, index in items_data:
        db.add(
            ContractItem(
                contract_id=contract.id,
                description=item.description,
                quantity=item.quantity,
                unit=item.unit,
                price=item.price,
                amount=item_amount,
                sort_order=index,
            )
        )

    await db.commit()
    await db.refresh(contract)
    await db.refresh(contract, ["client", "items", "incomes", "expenses"])
    return _contract_to_response(contract)


def _contract_to_response(contract: Contract) -> ContractResponse:
    items = [ContractItemResponse.model_validate(item) for item in contract.items] if contract.items else []

    advance_sum = ZERO_DECIMAL
    intermediate_sum = ZERO_DECIMAL
    closing_sum = ZERO_DECIMAL
    for income in contract.__dict__.get("incomes") or []:
        amount = to_decimal(income.amount_rsd) * Decimal(str(income.exchange_rate or 1))
        if income.contract_payment_type == "advance":
            advance_sum += amount
        elif income.contract_payment_type == "intermediate":
            intermediate_sum += amount
        elif income.contract_payment_type == "closing":
            closing_sum += amount

    total_received = advance_sum + intermediate_sum + closing_sum
    total_expenses = decimal_sum(
        [expense.amount or ZERO_DECIMAL for expense in (contract.__dict__.get("expenses") or [])]
    )
    profit = total_received - total_expenses

    return ContractResponse(
        id=contract.id,
        number=contract.number,
        date=contract.date,
        client_id=contract.client_id,
        project_id=contract.project_id,
        client_name=contract.client.name if contract.client else None,
        contract_type=contract.contract_type,
        subject=contract.subject,
        amount=contract.amount,
        currency=contract.currency,
        validity_start=contract.validity_start,
        validity_end=contract.validity_end,
        status=contract.status,
        note=contract.note,
        created_at=contract.created_at,
        items=items,
        advance_sum=advance_sum,
        intermediate_sum=intermediate_sum,
        closing_sum=closing_sum,
        total_received=total_received,
        total_expenses=total_expenses,
        profit=profit,
    )


@router.get("/{contract_id}", response_model=ContractResponse)
async def get_contract(
    contract_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    result = await db.execute(
        select(Contract)
        .options(
            selectinload(Contract.client),
            selectinload(Contract.items),
            selectinload(Contract.incomes),
            selectinload(Contract.expenses),
        )
        .where(Contract.id == contract_id)
    )
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(404, "Contract not found")
    return _contract_to_response(contract)


@router.patch("/{contract_id}", response_model=ContractResponse)
async def update_contract(
    contract_id: int,
    data: ContractUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    result = await db.execute(
        select(Contract)
        .options(
            selectinload(Contract.client),
            selectinload(Contract.items),
            selectinload(Contract.incomes),
            selectinload(Contract.expenses),
        )
        .where(Contract.id == contract_id)
    )
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(404, "Contract not found")

    data_dict = data.model_dump(exclude_unset=True)
    items_data = data_dict.pop("items", None)
    if data_dict.get("project_id"):
        await get_project_or_404(db, data_dict["project_id"])

    for key, value in data_dict.items():
        setattr(contract, key, value)

    if items_data is not None:
        for item in list(contract.items):
            await db.delete(item)
        await db.flush()

        amount = ZERO_DECIMAL
        has_items = False
        for index, item in enumerate(items_data):
            item_obj = ContractItemCreate(**item)
            item_amount = to_decimal(item_obj.quantity) * to_decimal(item_obj.price)
            amount += item_amount
            has_items = True
            db.add(
                ContractItem(
                    contract_id=contract.id,
                    description=item_obj.description,
                    quantity=item_obj.quantity,
                    unit=item_obj.unit,
                    price=item_obj.price,
                    amount=item_amount,
                    sort_order=index,
                )
            )
        if has_items:
            contract.amount = amount

    if "project_id" in data_dict:
        for income in contract.incomes or []:
            income.project_id = contract.project_id
        for expense in contract.expenses or []:
            expense.project_id = contract.project_id

    await db.commit()
    await db.refresh(contract)
    await db.refresh(contract, ["client", "items", "incomes", "expenses"])
    return _contract_to_response(contract)


@router.delete("/{contract_id}")
async def delete_contract(
    contract_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(404, "Contract not found")
    await db.delete(contract)
    await db.commit()
    return {"ok": True}
