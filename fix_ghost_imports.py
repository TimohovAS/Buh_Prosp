"""
Quick fix: list all BankImportFile records and optionally delete ones where
created_income + created_expense == 0 (these are ghost imports with no actual transactions).
"""
import asyncio
from sqlalchemy import select, delete, text
from backend.database import AsyncSessionLocal
from backend.models import BankImportFile


async def main():
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(BankImportFile).order_by(BankImportFile.id)
        )
        all_files = r.scalars().all()
        print(f"Всего файлов в базе: {len(all_files)}\n")
        print(f"{'ID':>4}  {'Создано':>7}  {'Заявлено':>8}  Файл")
        print("-" * 80)
        
        ghost_ids = []
        for f in all_files:
            created = (f.created_income or 0) + (f.created_expense or 0)
            is_ghost = created == 0 and (f.transaction_count or 0) > 0
            marker = " <<< GHOST" if is_ghost else ""
            print(f"{f.id:>4}  {created:>7}  {f.transaction_count or 0:>8}  {f.file_name}{marker}")
            if is_ghost:
                ghost_ids.append(f.id)
        
        print()
        if not ghost_ids:
            print("Призрачных записей не найдено.")
            return
        
        print(f"Найдено {len(ghost_ids)} призрачных записей (IDs: {ghost_ids})")
        print("Удаляем их, чтобы дать возможность повторно импортировать...")
        await db.execute(
            delete(BankImportFile).where(BankImportFile.id.in_(ghost_ids))
        )
        await db.commit()
        print("Готово! Теперь можно снова импортировать эти файлы.")


if __name__ == "__main__":
    asyncio.run(main())
