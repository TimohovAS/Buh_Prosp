"""Главный модуль приложения ProspEl."""
import asyncio
from contextlib import asynccontextmanager
from contextlib import suppress
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.database import init_db
from backend.backup_service import backup_scheduler_loop
from backend.models import User
from backend.auth import get_password_hash
from backend.routers.auth_router import router as auth_router
from backend.routers.income_router import router as income_router
from backend.routers.clients_router import router as clients_router
from backend.routers.obligations_router import router as obligations_router
from backend.routers.dashboard_router import router as dashboard_router
from backend.routers.enterprise_router import router as enterprise_router
from backend.routers.reports_router import router as reports_router
from backend.routers.finance_router import router as finance_router
from backend.routers.contracts_router import router as contracts_router
from backend.routers.users_router import router as users_router
from backend.routers.expenses_router import router as expenses_router
from backend.routers.planned_expenses_router import router as planned_expenses_router
from backend.routers.bank_import_router import router as bank_import_router
from backend.routers.bank_transactions_router import router as bank_transactions_router
from backend.routers.projects_router import router as projects_router
from backend.routers.categories_router import router as categories_router
from backend.routers.cash_router import router as cash_router
from backend.routers.service_router import router as service_router
from backend.routers.efaktura_router import router as efaktura_router

settings = get_settings()


async def _bootstrap_users_and_payments() -> None:
    """Подготовить dev-bootstrap и базовые справочники при старте."""
    from backend.database import AsyncSessionLocal
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).limit(1))
        has_any_user = result.scalar_one_or_none() is not None

        if not has_any_user and settings.is_dev:
            admin = User(
                username="admin",
                password_hash=get_password_hash("admin"),
                full_name="Администратор",
                role="admin",
                default_language="sr",
            )
            db.add(admin)
            await db.commit()
        elif not has_any_user and settings.is_prod:
            print("[startup] No users found. Admin auto-bootstrap is disabled in prod.")

        from backend.payments_service import ensure_payment_types
        await ensure_payment_types(db)
        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Инициализация при запуске."""
    await init_db()
    backup_task = None
    await _bootstrap_users_and_payments()
    backup_task = asyncio.create_task(backup_scheduler_loop())
    try:
        yield
    finally:
        if backup_task is not None:
            backup_task.cancel()
            with suppress(asyncio.CancelledError):
                await backup_task


app = FastAPI(
    title=settings.app_name,
    description="Бухгалтерская программа для ИП-паушальщика (Сербия)",
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api")
app.include_router(income_router, prefix="/api")
app.include_router(clients_router, prefix="/api")

app.include_router(contracts_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(expenses_router, prefix="/api")
app.include_router(planned_expenses_router, prefix="/api")
app.include_router(bank_import_router, prefix="/api")
app.include_router(bank_transactions_router, prefix="/api")
app.include_router(projects_router, prefix="/api")
app.include_router(categories_router, prefix="/api")
app.include_router(cash_router, prefix="/api")
app.include_router(service_router, prefix="/api")
app.include_router(efaktura_router, prefix="/api")
app.include_router(obligations_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(enterprise_router, prefix="/api")
app.include_router(reports_router, prefix="/api")
app.include_router(finance_router, prefix="/api")


@app.get("/")
def root():
    return {"app": settings.app_name, "version": settings.app_version, "env": settings.app_env}


@app.get("/api/prospel")
def prospel_check():
    """Проверка: если видите это — backend ProspEl работает."""
    return {"app": settings.app_name, "status": "ok", "version": settings.app_version, "env": settings.app_env}
