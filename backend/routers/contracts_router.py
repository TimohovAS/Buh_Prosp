"""Роутер договоров (по образцу 1С Моя фирма)."""
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.models import Contract, ContractItem, Client, User
from backend.schemas import ContractCreate, ContractUpdate, ContractResponse, ContractItemCreate, ContractItemResponse
from backend.auth import get_current_user_required, require_edit_access

router = APIRouter(prefix="/contracts", tags=["contracts"])


@router.get("", response_model=list[ContractResponse])
async def list_contracts(
    client_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Список договоров."""
    q = select(Contract).options(selectinload(Contract.client), selectinload(Contract.items), selectinload(Contract.incomes))
    if client_id:
        q = q.where(Contract.client_id == client_id)
    if status:
        q = q.where(Contract.status == status)
    if year:
        q = q.where(
            Contract.date >= date(year, 1, 1),
            Contract.date <= date(year, 12, 31)
        )
    q = q.order_by(Contract.date.desc(), Contract.id.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    contracts = result.scalars().all()
    return [_contract_to_response(c) for c in contracts]


@router.get("/next-number/")
async def next_contract_number(
    year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Следующий номер договора."""
    y = year or date.today().year
    r = await db.execute(
        select(Contract).where(
            Contract.date >= date(y, 1, 1),
            Contract.date <= date(y, 12, 31)
        )
    )
    contracts = r.scalars().all()
    nums = []
    for c in contracts:
        parts = str(c.number).split("-")
        if len(parts) == 2 and parts[1].isdigit():
            nums.append(int(parts[1]))
    next_num = max(nums, default=0) + 1
    return {"number": f"{y}-{next_num:04d}"}


@router.post("/create", response_model=ContractResponse)
async def create_contract(
    data: ContractCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Создать договор."""
    r = await db.execute(select(Client).where(Client.id == data.client_id))
    client = r.scalar_one_or_none()
    if not client:
        raise HTTPException(404, "Клиент не найден")

    amount = 0
    items_data = []
    if data.items:
        for i, item in enumerate(data.items):
            amt = item.quantity * item.price
            amount += amt
            items_data.append((item, amt, i))
    else:
        amount = data.amount

    contract = Contract(
        number=data.number,
        date=data.date,
        client_id=data.client_id,
        project_id=data.project_id,
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

    for item, amt, idx in items_data:
        ci = ContractItem(
            contract_id=contract.id,
            description=item.description,
            quantity=item.quantity,
            unit=item.unit,
            price=item.price,
            amount=amt,
            sort_order=idx,
        )
        db.add(ci)

    await db.flush()
    await db.refresh(contract)
    await db.refresh(contract, ["client", "items"])
    return _contract_to_response(contract)


def _contract_to_response(c: Contract) -> ContractResponse:
    items = [ContractItemResponse.model_validate(i) for i in c.items] if c.items else []
    advance_sum = intermediate_sum = closing_sum = 0.0
    incomes = getattr(c, "incomes", []) or []
    for inc in incomes:
        amt = inc.amount_rsd * (inc.exchange_rate or 1)
        if inc.contract_payment_type == "advance":
            advance_sum += amt
        elif inc.contract_payment_type == "intermediate":
            intermediate_sum += amt
        elif inc.contract_payment_type == "closing":
            closing_sum += amt
    total_received = advance_sum + intermediate_sum + closing_sum
    return ContractResponse(
        id=c.id,
        number=c.number,
        date=c.date,
        client_id=c.client_id,
        project_id=c.project_id,
        client_name=c.client.name if c.client else None,
        contract_type=c.contract_type,
        subject=c.subject,
        amount=c.amount,
        currency=c.currency,
        validity_start=c.validity_start,
        validity_end=c.validity_end,
        status=c.status,
        note=c.note,
        created_at=c.created_at,
        items=items,
        advance_sum=advance_sum,
        intermediate_sum=intermediate_sum,
        closing_sum=closing_sum,
        total_received=total_received,
    )


@router.get("/{contract_id}", response_model=ContractResponse)
async def get_contract(
    contract_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Получить договор."""
    r = await db.execute(
        select(Contract).options(selectinload(Contract.client), selectinload(Contract.items), selectinload(Contract.incomes))
        .where(Contract.id == contract_id)
    )
    contract = r.scalar_one_or_none()
    if not contract:
        raise HTTPException(404, "Договор не найден")
    return _contract_to_response(contract)


@router.patch("/{contract_id}", response_model=ContractResponse)
async def update_contract(
    contract_id: int,
    data: ContractUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Обновить договор."""
    r = await db.execute(
        select(Contract).options(selectinload(Contract.client), selectinload(Contract.items), selectinload(Contract.incomes))
        .where(Contract.id == contract_id)
    )
    contract = r.scalar_one_or_none()
    if not contract:
        raise HTTPException(404, "Договор не найден")
    data_dict = data.model_dump(exclude_unset=True)
    items_data = data_dict.pop("items", None)
    for k, v in data_dict.items():
        setattr(contract, k, v)
    if items_data is not None:
        for ci in list(contract.items):
            await db.delete(ci)
        await db.flush()
        amount = 0
        for i, item in enumerate(items_data):
            item_obj = ContractItemCreate(**item)
            amt = item_obj.quantity * item_obj.price
            amount += amt
            ci = ContractItem(
                contract_id=contract.id,
                description=item_obj.description,
                quantity=item_obj.quantity,
                unit=item_obj.unit,
                price=item_obj.price,
                amount=amt,
                sort_order=i,
            )
            db.add(ci)
        contract.amount = amount
    await db.flush()
    await db.refresh(contract)
    await db.refresh(contract, ["client", "items"])
    return _contract_to_response(contract)


@router.delete("/{contract_id}")
async def delete_contract(
    contract_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Удалить договор."""
    r = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = r.scalar_one_or_none()
    if not contract:
        raise HTTPException(404, "Договор не найден")
    await db.delete(contract)
    return {"ok": True}
