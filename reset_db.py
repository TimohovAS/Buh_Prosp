"""Пересоздание базы данных ProspEl.

Удаляет prospel.db и создаёт пустую БД. После запуска:
- создаётся admin/admin
- создаются типы обязательных платежей (tax, pio, health, unemployment)
- добавляются данные предприятия (ИП): Andrei Timokhov pr ProspEl

Запуск: python reset_db.py
Внимание: остановите бэкенд перед запуском (файл БД не должен быть открыт).
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select
from backend.auth import get_password_hash
from backend.database import reset_db, AsyncSessionLocal, get_db_path
from backend.models import User, Enterprise
from backend.payments_service import ensure_payment_types


async def main():
    db_path = get_db_path()
    if db_path and db_path.exists():
        print(f"Удаляю {db_path}...")
    else:
        print("БД не найдена, создаю пустую.")

    await reset_db()
    print("Таблицы созданы.")

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
            print("Создан пользователь admin/admin")
        else:
            print("Пользователь admin уже существует")
        await ensure_payment_types(db)
        await db.commit()
        print("Типы обязательных платежей добавлены.")

        r2 = await db.execute(select(Enterprise).limit(1))
        if r2.scalar_one_or_none() is None:
            ent = Enterprise(
                name="Andrei Timokhov pr ProspEl",
                address="Sremska 94, 26300, Vršac, Srbija",
                pib="115370068",
                maticni_broj="68313953",
                bank_name="Alta banka A.D.- Beograd",
                bank_account="190-0000000157810-14",
            )
            db.add(ent)
            await db.commit()
            print("Данные предприятия (ИП) добавлены.")
        else:
            print("Данные предприятия уже существуют.")

    print("Готово. Запустите: python run.py")


if __name__ == "__main__":
    asyncio.run(main())
