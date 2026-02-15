"""Роутер аутентификации."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import User
from backend.schemas import UserCreate, UserResponse, Token
from backend.auth import get_password_hash, create_access_token, verify_password, require_admin, get_current_user_required
from backend.models import UserRole

router = APIRouter(prefix="/auth", tags=["auth"])


class MeUpdate(BaseModel):
    default_language: str | None = None


@router.post("/login")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """Вход в систему."""
    result = await db.execute(select(User).where(User.username == form_data.username, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    token = create_access_token(data={"sub": user.username})
    return Token(
        access_token=token,
        user=UserResponse(
            id=user.id,
            username=user.username,
            full_name=user.full_name,
            role=user.role,
            default_language=user.default_language or "sr",
            is_active=user.is_active,
            created_at=user.created_at
        )
    )


@router.patch("/me", response_model=UserResponse)
async def update_me(
    data: MeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Обновить профиль текущего пользователя (язык и т.д.)."""
    if data.default_language is not None:
        if data.default_language not in ("sr", "ru"):
            raise HTTPException(400, "Язык должен быть sr или ru")
        current_user.default_language = data.default_language
    await db.flush()
    await db.refresh(current_user)
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        full_name=current_user.full_name,
        role=current_user.role,
        default_language=current_user.default_language or "sr",
        is_active=current_user.is_active,
        created_at=current_user.created_at,
    )
