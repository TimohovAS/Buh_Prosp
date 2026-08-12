"""Clients router."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.bank_account_utils import normalize_serbian_bank_account
from backend.database import get_db
from backend.models import Client, ClientBankAccount, User
from backend.schemas import ClientCreate, ClientUpdate, ClientResponse, ClientBrief
from backend.auth import get_current_user_required, require_edit_access

router = APIRouter(prefix="/clients", tags=["clients"])


async def _sync_bank_accounts(
    db: AsyncSession,
    client: Client,
    values: list[str],
    *,
    source: str = "manual",
) -> None:
    normalized_accounts: list[str] = []
    for value in values:
        normalized = normalize_serbian_bank_account(value)
        if not normalized:
            raise ValueError(f"Invalid Serbian bank account: {value}")
        if normalized not in normalized_accounts:
            normalized_accounts.append(normalized)

    if normalized_accounts:
        owner_result = await db.execute(
            select(ClientBankAccount).where(ClientBankAccount.account_number.in_(normalized_accounts))
        )
        for record in owner_result.scalars().all():
            if int(record.client_id) != int(client.id):
                raise ValueError(f"Bank account {record.account_number} belongs to another client")

    existing_result = await db.execute(select(ClientBankAccount).where(ClientBankAccount.client_id == client.id))
    existing = {record.account_number: record for record in existing_result.scalars().all()}
    requested = set(normalized_accounts)
    for account_number, record in existing.items():
        if account_number not in requested:
            await db.delete(record)
    for account_number in normalized_accounts:
        if account_number not in existing:
            db.add(
                ClientBankAccount(
                    client_id=client.id,
                    account_number=account_number,
                    source=source,
                )
            )
    await db.flush()


async def _load_client(db: AsyncSession, client_id: int) -> Client | None:
    result = await db.execute(
        select(Client).options(selectinload(Client.bank_account_records)).where(Client.id == client_id)
    )
    return result.scalar_one_or_none()


@router.get("", response_model=list[ClientResponse])
async def list_clients(
    search: str = Query("", description="Client search"),
    archived: bool = Query(False, description="Include archived"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    q = select(Client).options(selectinload(Client.bank_account_records))
    if not archived:
        q = q.where(Client.is_archived == False)
    if search:
        search_conditions = [
            Client.name.ilike(f"%{search}%"),
            Client.pib.ilike(f"%{search}%"),
            Client.maticni_broj.ilike(f"%{search}%"),
            Client.bank_account_records.any(ClientBankAccount.account_number.ilike(f"%{search}%")),
        ]
        account_digits = "".join(char for char in search if char.isdigit())
        if len(account_digits) >= 3:
            search_conditions.append(
                Client.bank_account_records.any(ClientBankAccount.account_number.ilike(f"%{account_digits}%"))
            )
        q = q.where(or_(*search_conditions))
    q = q.order_by(Client.name)
    result = await db.execute(q)
    return [ClientResponse.model_validate(client) for client in result.scalars().all()]


@router.get("/brief", response_model=list[ClientBrief])
async def list_clients_brief(
    search: str = Query(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    q = select(Client).where(Client.is_archived == False)
    if search:
        q = q.where(
            or_(
                Client.name.ilike(f"%{search}%"),
                Client.pib.ilike(f"%{search}%"),
                Client.maticni_broj.ilike(f"%{search}%"),
            )
        )
    q = q.order_by(Client.name).limit(50)
    result = await db.execute(q)
    return [ClientBrief(id=client.id, name=client.name) for client in result.scalars().all()]


@router.post("", response_model=ClientResponse)
async def create_client(
    data: ClientCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    payload = data.model_dump(exclude={"bank_accounts"})
    client = Client(**payload)
    db.add(client)
    try:
        await db.flush()
        await _sync_bank_accounts(db, client, data.bank_accounts)
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(400, str(exc)) from exc
    loaded_client = await _load_client(db, client.id)
    return ClientResponse.model_validate(loaded_client)


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    client = await _load_client(db, client_id)
    if not client:
        raise HTTPException(404, "Client not found")
    return ClientResponse.model_validate(client)


@router.patch("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: int,
    data: ClientUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    client = await _load_client(db, client_id)
    if not client:
        raise HTTPException(404, "Client not found")
    payload = data.model_dump(exclude_unset=True)
    bank_accounts = payload.pop("bank_accounts", None)
    for key, value in payload.items():
        setattr(client, key, value)
    try:
        if bank_accounts is not None:
            await _sync_bank_accounts(db, client, bank_accounts)
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(400, str(exc)) from exc
    loaded_client = await _load_client(db, client.id)
    return ClientResponse.model_validate(loaded_client)


@router.delete("/{client_id}")
async def delete_client(
    client_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(404, "Client not found")
    client.is_archived = True
    await db.commit()
    return {"ok": True}
