"""Подключение к базе данных и сессии."""
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
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Инициализация таблиц БД (создание по моделям)."""
    import backend.models  # noqa: F401 — регистрируем модели в Base.metadata
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


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
        db_path.unlink()
    await init_db()
