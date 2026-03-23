"""One-time repair: convert legacy incoming eFaktura expenses into IncomingInvoice records."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from backend.database import AsyncSessionLocal, get_db_path
from backend.efaktura_service import migrate_legacy_efaktura_incoming_records


async def main_async() -> None:
    db_path = get_db_path()
    if db_path:
        print(f"[repair-legacy-efaktura] Using DB: {db_path}")

    async with AsyncSessionLocal() as session:
        try:
            result = await migrate_legacy_efaktura_incoming_records(session, user_id=None)
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    print(f"[repair-legacy-efaktura] Found: {result['found_count']}")
    print(f"[repair-legacy-efaktura] Migrated: {result['migrated_count']}")
    print(f"[repair-legacy-efaktura] Skipped existing invoice: {result['skipped_existing_invoice_count']}")
    print(f"[repair-legacy-efaktura] Skipped missing expense: {result['skipped_missing_expense_count']}")
    print(f"[repair-legacy-efaktura] Skipped non-legacy expense: {result['skipped_nonlegacy_expense_count']}")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
