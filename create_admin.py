"""Создание или сброс пароля администратора."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select
from backend.database import AsyncSessionLocal, init_db
from backend.models import User
from backend.auth import get_password_hash


async def main():
    await init_db()
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(User).where(User.username == "admin"))
        user = r.scalar_one_or_none()
        password = "admin"
        if user:
            user.password_hash = get_password_hash(password)
            print("Пароль admin сброшен на: admin")
        else:
            user = User(
                username="admin",
                password_hash=get_password_hash(password),
                full_name="Администратор",
                role="admin",
                default_language="sr",
            )
            db.add(user)
            print("Создан пользователь admin с паролем: admin")
        await db.commit()
    print("Готово.")


if __name__ == "__main__":
    asyncio.run(main())
