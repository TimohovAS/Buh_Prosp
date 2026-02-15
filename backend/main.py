"""Главный модуль приложения ProspEl."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db
from backend.models import User
from backend.auth import get_password_hash
from backend.routers.auth_router import router as auth_router
from backend.routers.income_router import router as income_router
from backend.routers.clients_router import router as clients_router
from backend.routers.payments_router import router as payments_router
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
from backend.routers.projects_router import router as projects_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Инициализация при запуске."""
    await init_db()
    # Создаём начального админа если нет пользователей
    from backend.database import AsyncSessionLocal
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(User).limit(1))
        if r.scalar_one_or_none() is None:
            admin = User(
                username="admin",
                password_hash=get_password_hash("admin"),
                full_name="Администратор",
                role="admin",
                default_language="sr",
            )
            db.add(admin)
            await db.commit()
        # Инициализация типов обязательных платежей
        from backend.payments_service import ensure_payment_types
        await ensure_payment_types(db)
        await db.commit()
    yield
    # cleanup if needed


app = FastAPI(
    title="ProspEl",
    description="Бухгалтерская программа для ИП-паушальщика (Сербия)",
    version="2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
app.include_router(projects_router, prefix="/api")
app.include_router(payments_router, prefix="/api")
app.include_router(obligations_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(enterprise_router, prefix="/api")
app.include_router(reports_router, prefix="/api")
app.include_router(finance_router, prefix="/api")


@app.get("/")
def root():
    return {"app": "ProspEl", "version": "2.0"}


@app.get("/api/prospel")
def prospel_check():
    """Проверка: если видите это — backend ProspEl работает."""
    return {"app": "ProspEl", "status": "ok", "version": "2.0"}
