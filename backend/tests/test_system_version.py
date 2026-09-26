from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from backend.auth import get_current_user_required
from backend.database import get_db
from backend.main import _backend_build_info, app, settings


def test_backend_build_info_without_git(monkeypatch):
    monkeypatch.setattr("backend.main._git_output", lambda *args: None)
    assert _backend_build_info() == {"commit": None, "dirty": False}


@pytest.mark.asyncio
async def test_system_version_reports_current_database_revision(db_session, monkeypatch):
    monkeypatch.setattr("backend.main.BACKEND_BUILD_INFO", {"commit": "123456789abc", "dirty": True})
    await db_session.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
    await db_session.execute(text("INSERT INTO alembic_version (version_num) VALUES ('test_revision')"))

    async def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            unauthenticated = await client.get("/api/system/version")
            assert unauthenticated.status_code == 401

            app.dependency_overrides[get_current_user_required] = lambda: SimpleNamespace(id=1)
            response = await client.get("/api/system/version")

        assert response.status_code == 200
        data = response.json()
        assert data["backend"] == settings.app_version
        assert data["backend_build"] == {"commit": "123456789abc", "dirty": True}
        assert data["python"]
        assert data["environment"] == settings.app_env
        assert data["database"]["engine"] == "sqlite"
        assert data["database"]["version"]
        assert data["database"]["revision"] == "test_revision"
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user_required, None)
