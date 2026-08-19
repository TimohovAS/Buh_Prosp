"""Аутентификация и авторизация."""

from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.config import get_settings
from backend.database import get_db
from backend.models import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)
settings = get_settings()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8") if isinstance(hashed_password, str) else hashed_password,
    )


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def create_refresh_token(
    data: dict,
    *,
    absolute_expires_at: Optional[datetime] = None,
    now: Optional[datetime] = None,
) -> str:
    """Создать refresh-токен с лимитом простоя и абсолютным сроком сессии."""
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)

    absolute_expiry = absolute_expires_at or (
        current_time + timedelta(minutes=settings.refresh_token_absolute_expire_minutes)
    )
    if absolute_expiry.tzinfo is None:
        absolute_expiry = absolute_expiry.replace(tzinfo=timezone.utc)

    idle_expiry = current_time + timedelta(minutes=settings.refresh_token_idle_expire_minutes)
    expiry = min(idle_expiry, absolute_expiry)
    if expiry <= current_time:
        raise JWTError("Refresh session has expired")

    to_encode = data.copy()
    to_encode.update(
        {
            "exp": expiry,
            "type": "refresh",
            "session_expires_at": int(absolute_expiry.timestamp()),
        }
    )
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_refresh_token(token: str) -> dict:
    """Проверить подпись, сроки и назначение refresh-токена."""
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    if payload.get("type") != "refresh":
        raise JWTError("Invalid token type")
    if not payload.get("sub") or not payload.get("session_expires_at"):
        raise JWTError("Invalid refresh token claims")
    return payload


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """Получить текущего пользователя по токену."""
    if not token:
        return None
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Недействительные учётные данные",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        if payload.get("type") == "refresh":
            raise credentials_exception
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.username == username, User.is_active == True))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user


async def get_current_user_required(current_user: Optional[User] = Depends(get_current_user)) -> User:
    """Требует авторизации."""
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется авторизация")
    return current_user


def require_role(*allowed_roles: UserRole):
    """Проверка роли пользователя."""

    async def role_checker(current_user: User = Depends(get_current_user_required)) -> User:
        user_role = UserRole(current_user.role)
        if user_role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
        return current_user

    return role_checker


def require_admin(current_user: User = Depends(get_current_user_required)) -> User:
    if UserRole(current_user.role) != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Требуются права администратора")
    return current_user


def require_edit_access(current_user: User = Depends(get_current_user_required)) -> User:
    """Право на редактирование: admin, accountant, cashier."""
    if UserRole(current_user.role) not in (UserRole.ADMIN, UserRole.ACCOUNTANT, UserRole.CASHIER):
        raise HTTPException(status_code=403, detail="Недостаточно прав для редактирования")
    return current_user
