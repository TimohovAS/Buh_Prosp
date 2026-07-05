import asyncio
import os
import sys

# Add root directory to path so 'backend' module is recognized
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.database import engine
from sqlalchemy import text


async def main():
    async with engine.begin() as conn:
        print("Starting migration to drop project.contract_id...")

        # Check if the column exists
        rows = await conn.run_sync(
            lambda sync_conn: sync_conn.exec_driver_sql("PRAGMA table_info('projects')").fetchall()
        )
        columns = {str(r[1]).lower() for r in rows}

        if "contract_id" in columns:
            print("Dropping contract_id from projects table...")
            try:
                await conn.execute(text("ALTER TABLE projects DROP COLUMN contract_id"))
                print("Column dropped successfully.")
            except Exception as e:
                print(f"Failed to drop column natively (maybe old SQLite version): {e}")
                print("Skipping column drop. The column will exist but be ignored by models.py")
        else:
            print("Column contract_id does not exist in projects. Nothing to do.")

        print("Migration complete.")


if __name__ == "__main__":
    asyncio.run(main())
