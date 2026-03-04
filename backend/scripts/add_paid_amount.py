"""Migration: add paid_amount column to income table (SQLite-compatible)."""
import asyncio
from sqlalchemy import text
from backend.database import engine


async def run():
    async with engine.begin() as conn:
        # Check if column already exists (SQLite PRAGMA)
        result = await conn.execute(text("PRAGMA table_info(income)"))
        columns = [row[1] for row in result.fetchall()]

        if "paid_amount" not in columns:
            await conn.execute(text(
                "ALTER TABLE income ADD COLUMN paid_amount FLOAT DEFAULT 0.0"
            ))
            print("Column paid_amount added.")
        else:
            print("Column paid_amount already exists, skipping ALTER.")

        # Initialize: fully paid records get paid_amount = amount_rsd
        await conn.execute(text(
            "UPDATE income SET paid_amount = amount_rsd WHERE status = 'paid' AND (paid_amount IS NULL OR paid_amount = 0)"
        ))
        # Everything else stays at 0
        await conn.execute(text(
            "UPDATE income SET paid_amount = 0.0 WHERE paid_amount IS NULL"
        ))
        print("Migration completed successfully.")


if __name__ == "__main__":
    asyncio.run(run())
