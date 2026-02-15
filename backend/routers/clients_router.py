"""Роутер справочника клиентов."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import Client, User
from backend.schemas import ClientCreate, ClientUpdate, ClientResponse, ClientBrief
from backend.auth import get_current_user_required, require_edit_access

router = APIRouter(prefix="/clients", tags=["clients"])


@router.get("", response_model=list[ClientResponse])
async def list_clients(
    search: str = Query("", description="Поиск по имени"),
    archived: bool = Query(False, description="Включая архивных"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Список клиентов."""
    q = select(Client)
    if not archived:
        q = q.where(Client.is_archived == False)
    if search:
        q = q.where(Client.name.ilike(f"%{search}%"))
    q = q.order_by(Client.name)
    result = await db.execute(q)
    return [ClientResponse.model_validate(c) for c in result.scalars().all()]


@router.get("/brief", response_model=list[ClientBrief])
async def list_clients_brief(
    search: str = Query(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Краткий список для выпадающих списков."""
    q = select(Client).where(Client.is_archived == False)
    if search:
        q = q.where(Client.name.ilike(f"%{search}%"))
    q = q.order_by(Client.name).limit(50)
    result = await db.execute(q)
    return [ClientBrief(id=c.id, name=c.name) for c in result.scalars().all()]


@router.post("", response_model=ClientResponse)
async def create_client(
    data: ClientCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Добавить клиента."""
    client = Client(**data.model_dump())
    db.add(client)
    await db.flush()
    await db.refresh(client)
    return ClientResponse.model_validate(client)


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Получить клиента."""
    r = await db.execute(select(Client).where(Client.id == client_id))
    client = r.scalar_one_or_none()
    if not client:
        raise HTTPException(404, "Клиент не найден")
    return ClientResponse.model_validate(client)


@router.patch("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: int,
    data: ClientUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Обновить клиента."""
    r = await db.execute(select(Client).where(Client.id == client_id))
    client = r.scalar_one_or_none()
    if not client:
        raise HTTPException(404, "Клиент не найден")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(client, k, v)
    await db.flush()
    await db.refresh(client)
    return ClientResponse.model_validate(client)


@router.delete("/{client_id}")
async def delete_client(
    client_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Архивировать клиента (мягкое удаление)."""
    r = await db.execute(select(Client).where(Client.id == client_id))
    client = r.scalar_one_or_none()
    if not client:
        raise HTTPException(404, "Клиент не найден")
    client.is_archived = True
    await db.flush()
    return {"ok": True}
