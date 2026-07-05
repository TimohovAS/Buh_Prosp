"""Подключение к базе данных и сессии."""

import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from backend.config import get_settings


settings = get_settings()
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Базовый класс для моделей."""

    pass


async def get_db():
    """Dependency для получения сессии БД."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Apply Alembic migrations to the configured database."""
    await asyncio.to_thread(run_migrations)


def run_migrations() -> None:
    """Upgrade the configured database to the latest Alembic revision."""
    from alembic import command
    from alembic.config import Config

    project_root = Path(__file__).resolve().parent.parent
    alembic_config = Config(str(project_root / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(project_root / "alembic"))
    command.upgrade(alembic_config, "head")


def get_db_path() -> Path | None:
    """Путь к файлу БД для SQLite (для reset_db)."""
    url = settings.database_url
    if url.startswith("sqlite"):
        path = url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
        return Path(path).resolve()
    return None


async def reset_db():
    """Удалить БД и создать пустую. Вызвать до создания сессий."""
    db_path = get_db_path()
    if db_path and db_path.exists():
        await engine.dispose()
        db_path.unlink()
    await init_db()
