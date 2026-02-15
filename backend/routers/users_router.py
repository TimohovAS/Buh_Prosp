"""Роутер управления пользователями (только для администратора)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import User, UserRole
from backend.schemas import UserCreate, UserUpdate, UserResponse
from backend.auth import get_password_hash, require_admin

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserResponse])
async def list_users(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Список пользователей."""
    q = select(User).order_by(User.username)
    if not include_inactive:
        q = q.where(User.is_active == True)
    result = await db.execute(q)
    return [UserResponse.model_validate(u) for u in result.scalars().all()]


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Получить пользователя."""
    r = await db.execute(select(User).where(User.id == user_id))
    user = r.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    return UserResponse.model_validate(user)


@router.post("", response_model=UserResponse)
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Создать пользователя."""
    r = await db.execute(select(User).where(User.username == data.username))
    if r.scalar_one_or_none():
        raise HTTPException(400, "Пользователь с таким логином уже существует")
    try:
        role = UserRole(data.role).value
    except ValueError:
        raise HTTPException(400, "Недопустимая роль")
    user = User(
        username=data.username,
        password_hash=get_password_hash(data.password),
        full_name=data.full_name,
        role=role,
        default_language=data.default_language or "sr",
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return UserResponse.model_validate(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Обновить пользователя."""
    r = await db.execute(select(User).where(User.id == user_id))
    user = r.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    d = data.model_dump(exclude_unset=True)
    if "password" in d:
        pwd = d.pop("password")
        if pwd:
            user.password_hash = get_password_hash(pwd)
    if "role" in d:
        try:
            d["role"] = UserRole(d["role"]).value
        except ValueError:
            raise HTTPException(400, "Недопустимая роль")
    for k, v in d.items():
        setattr(user, k, v)
    await db.flush()
    await db.refresh(user)
    return UserResponse.model_validate(user)


@router.delete("/{user_id}")
async def deactivate_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Деактивировать пользователя (не удалять)."""
    if user_id == current_user.id:
        raise HTTPException(400, "Нельзя деактивировать себя")
    r = await db.execute(select(User).where(User.id == user_id))
    user = r.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    user.is_active = False
    await db.flush()
    return {"ok": True}
