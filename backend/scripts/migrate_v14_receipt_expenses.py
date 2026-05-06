import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from backend.database import AsyncSessionLocal
from backend.models import PurchaseReceipt
from backend.receipt_service import ReceiptImportError, create_expense_from_receipt


async def run() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PurchaseReceipt.id)
            .where(PurchaseReceipt.expense_id.is_(None))
            .order_by(PurchaseReceipt.receipt_datetime.asc(), PurchaseReceipt.id.asc())
        )
        receipt_ids = list(result.scalars().all())
        if not receipt_ids:
            print("[v14] No purchase receipts without expenses found.")
            return

        created = 0
        skipped: list[tuple[int, str]] = []
        for receipt_id in receipt_ids:
            try:
                await create_expense_from_receipt(db, receipt_id)
                created += 1
            except ReceiptImportError as exc:
                skipped.append((receipt_id, str(exc)))

        await db.commit()

    print(f"[v14] Created expenses for receipts: {created}")
    if skipped:
        print(f"[v14] Skipped receipts: {len(skipped)}")
        for receipt_id, reason in skipped:
            print(f"[v14]   #{receipt_id}: {reason}")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
