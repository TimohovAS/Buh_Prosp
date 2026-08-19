"""Роутер аутентификации."""

from datetime import datetime, timezone

from jose import JWTError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import User
from backend.schemas import UserResponse, Token
from backend.auth import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    verify_password,
    get_current_user_required,
)
from backend.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


class MeUpdate(BaseModel):
    default_language: str | None = None


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        default_language=user.default_language or "sr",
        is_active=user.is_active,
        created_at=user.created_at,
    )


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        max_age=settings.refresh_token_idle_expire_minutes * 60,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="lax",
        path="/api/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="lax",
        path="/api/auth",
    )


def _expired_session_response() -> JSONResponse:
    response = JSONResponse(status_code=401, content={"detail": "Сессия истекла"})
    _clear_refresh_cookie(response)
    return response


@router.post("/login")
async def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Вход в систему."""
    result = await db.execute(select(User).where(User.username == form_data.username, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    token = create_access_token(data={"sub": user.username})
    refresh_token = create_refresh_token(data={"sub": user.username})
    _set_refresh_cookie(response, refresh_token)
    return Token(
        access_token=token,
        user=_user_response(user),
    )


@router.post("/refresh", response_model=Token)
async def refresh_session(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """Тихо обновить access-токен и продлить сессию в пределах 12 часов."""
    refresh_token = request.cookies.get(settings.refresh_cookie_name)
    if not refresh_token:
        return _expired_session_response()

    try:
        payload = decode_refresh_token(refresh_token)
        username = payload["sub"]
        absolute_expires_at = datetime.fromtimestamp(payload["session_expires_at"], tz=timezone.utc)
    except (JWTError, KeyError, TypeError, ValueError):
        return _expired_session_response()

    result = await db.execute(select(User).where(User.username == username, User.is_active == True))
    user = result.scalar_one_or_none()
    if user is None:
        return _expired_session_response()

    try:
        rotated_refresh_token = create_refresh_token(
            data={"sub": user.username},
            absolute_expires_at=absolute_expires_at,
        )
    except JWTError:
        return _expired_session_response()

    _set_refresh_cookie(response, rotated_refresh_token)
    return Token(access_token=create_access_token({"sub": user.username}), user=_user_response(user))


@router.post("/logout", status_code=204)
async def logout(response: Response):
    """Завершить браузерную refresh-сессию."""
    _clear_refresh_cookie(response)


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
    await db.commit()
    await db.refresh(current_user)
    return _user_response(current_user)
