from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Request, Response
from jose import JWTError, jwt

from backend import auth
from backend.models import User
from backend.routers.auth_router import _clear_refresh_cookie, _set_refresh_cookie, refresh_session


def _claims(token: str) -> dict:
    return jwt.get_unverified_claims(token)


def test_access_token_is_short_lived_and_typed(monkeypatch):
    monkeypatch.setattr(auth.settings, "access_token_expire_minutes", 15)
    before = datetime.now(timezone.utc)

    token = auth.create_access_token({"sub": "admin"})
    claims = _claims(token)

    assert claims["type"] == "access"
    assert claims["sub"] == "admin"
    expires_at = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)
    assert before + timedelta(minutes=14, seconds=55) <= expires_at
    assert expires_at <= before + timedelta(minutes=15, seconds=5)


def test_refresh_token_has_four_hour_idle_and_twelve_hour_absolute_limits(monkeypatch):
    monkeypatch.setattr(auth.settings, "refresh_token_idle_expire_minutes", 4 * 60)
    monkeypatch.setattr(auth.settings, "refresh_token_absolute_expire_minutes", 12 * 60)
    now = datetime.now(timezone.utc).replace(microsecond=0)

    token = auth.create_refresh_token({"sub": "admin"}, now=now)
    claims = auth.decode_refresh_token(token)

    assert claims["type"] == "refresh"
    assert datetime.fromtimestamp(claims["exp"], tz=timezone.utc) == now + timedelta(hours=4)
    assert datetime.fromtimestamp(claims["session_expires_at"], tz=timezone.utc) == now + timedelta(hours=12)


def test_refresh_rotation_preserves_absolute_session_limit(monkeypatch):
    monkeypatch.setattr(auth.settings, "refresh_token_idle_expire_minutes", 4 * 60)
    monkeypatch.setattr(auth.settings, "refresh_token_absolute_expire_minutes", 12 * 60)
    started_at = datetime.now(timezone.utc).replace(microsecond=0)
    absolute_expiry = started_at + timedelta(hours=12)

    rotated = auth.create_refresh_token(
        {"sub": "admin"},
        absolute_expires_at=absolute_expiry,
        now=started_at + timedelta(hours=10),
    )
    claims = _claims(rotated)

    assert datetime.fromtimestamp(claims["exp"], tz=timezone.utc) == absolute_expiry
    assert datetime.fromtimestamp(claims["session_expires_at"], tz=timezone.utc) == absolute_expiry


def test_access_token_cannot_be_used_as_refresh_token():
    with pytest.raises(JWTError):
        auth.decode_refresh_token(auth.create_access_token({"sub": "admin"}))


def test_refresh_token_cannot_be_rotated_after_absolute_expiry():
    now = datetime.now(timezone.utc)

    with pytest.raises(JWTError):
        auth.create_refresh_token(
            {"sub": "admin"},
            absolute_expires_at=now - timedelta(seconds=1),
            now=now,
        )


def test_refresh_cookie_is_http_only_and_can_be_cleared():
    response = Response()
    _set_refresh_cookie(response, "refresh-token")

    cookie_header = response.headers["set-cookie"]
    assert f"{auth.settings.refresh_cookie_name}=refresh-token" in cookie_header
    assert "HttpOnly" in cookie_header
    assert "Max-Age=14400" in cookie_header
    assert "Path=/api/auth" in cookie_header
    assert "SameSite=lax" in cookie_header

    clear_response = Response()
    _clear_refresh_cookie(clear_response)
    clear_cookie_header = clear_response.headers["set-cookie"]
    assert f'{auth.settings.refresh_cookie_name}=""' in clear_cookie_header
    assert "Max-Age=0" in clear_cookie_header


@pytest.mark.asyncio
async def test_refresh_endpoint_rotates_cookie_and_returns_new_access_token(db_session):
    user = User(
        username="session-user",
        password_hash=auth.get_password_hash("password"),
        full_name="Session User",
        role="admin",
        default_language="sr",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    refresh_token = auth.create_refresh_token({"sub": user.username})
    cookie = f"{auth.settings.refresh_cookie_name}={refresh_token}".encode("ascii")
    request = Request({"type": "http", "headers": [(b"cookie", cookie)]})
    response = Response()

    result = await refresh_session(request=request, response=response, db=db_session)

    assert result.access_token
    assert result.user.username == user.username
    assert "HttpOnly" in response.headers["set-cookie"]
    assert response.headers["set-cookie"] != cookie.decode("ascii")
