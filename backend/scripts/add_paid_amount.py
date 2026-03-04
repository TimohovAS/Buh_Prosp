"""Migration: add paid_amount column to income table."""
import asyncio
from sqlalchemy import text
from backend.database import engine


async def run():
    async with engine.begin() as conn:
        # Add paid_amount column if not exists
        await conn.execute(text("""
            ALTER TABLE income ADD COLUMN IF NOT EXISTS paid_amount FLOAT DEFAULT 0.0;
        """))
        # Set paid_amount = amount_rsd for already fully paid records (so AR stays correct)
        await conn.execute(text("""
            UPDATE income SET paid_amount = amount_rsd WHERE status = 'paid' AND paid_amount IS NULL;
        """))
        # Set paid_amount = 0 for everything else
        await conn.execute(text("""
            UPDATE income SET paid_amount = 0.0 WHERE paid_amount IS NULL;
        """))
        print("Migration completed: paid_amount column added to income table.")


if __name__ == "__main__":
    asyncio.run(run())
