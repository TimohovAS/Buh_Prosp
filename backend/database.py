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
        await conn.run_sync(_ensure_income_due_date_column)
        await conn.run_sync(_ensure_enterprise_backup_columns)


def _ensure_income_due_date_column(sync_conn):
    """
    Лёгкая миграция для существующих SQLite БД:
    добавляет income.due_date (Valuta), если колонка отсутствует.
    """
    if sync_conn.dialect.name != "sqlite":
        return
    rows = sync_conn.exec_driver_sql("PRAGMA table_info('income')").fetchall()
    columns = {str(r[1]).lower() for r in rows}
    if "due_date" not in columns:
        sync_conn.exec_driver_sql("ALTER TABLE income ADD COLUMN due_date DATE")


def _ensure_enterprise_backup_columns(sync_conn):
    if sync_conn.dialect.name != "sqlite":
        return
    rows = sync_conn.exec_driver_sql("PRAGMA table_info('enterprise')").fetchall()
    columns = {str(r[1]).lower() for r in rows}
    required = {
        "backup_dir": "ALTER TABLE enterprise ADD COLUMN backup_dir VARCHAR(500)",
        "backup_auto_enabled": "ALTER TABLE enterprise ADD COLUMN backup_auto_enabled BOOLEAN",
        "backup_auto_interval_hours": "ALTER TABLE enterprise ADD COLUMN backup_auto_interval_hours INTEGER",
        "backup_auto_retention_count": "ALTER TABLE enterprise ADD COLUMN backup_auto_retention_count INTEGER",
        "backup_manual_retention_count": "ALTER TABLE enterprise ADD COLUMN backup_manual_retention_count INTEGER",
        "backup_pre_restore_retention_count": "ALTER TABLE enterprise ADD COLUMN backup_pre_restore_retention_count INTEGER",
        "backup_scheduler_check_minutes": "ALTER TABLE enterprise ADD COLUMN backup_scheduler_check_minutes INTEGER",
    }
    for column, ddl in required.items():
        if column not in columns:
            sync_conn.exec_driver_sql(ddl)


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
