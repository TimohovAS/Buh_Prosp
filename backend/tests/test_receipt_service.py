from datetime import date, datetime
from decimal import Decimal

from backend.models import PurchaseReceipt, PurchaseReceiptItem
from backend.receipt_service import get_project_receipt_purchases


async def test_project_receipt_purchases_allow_completed_project(db_session, make_project):
    project = await make_project(db_session, code="DONE-RECEIPTS", status="completed")
    receipt = PurchaseReceipt(
        verification_url="https://example.test/receipt",
        qr_hash="completed-project-receipt",
        invoice_number="REC-DONE-1",
        seller_name="Supplier",
        receipt_datetime=datetime(2026, 7, 6, 12, 0),
        total_amount=Decimal("100.00"),
        project_id=project.id,
    )
    receipt.items = [
        PurchaseReceiptItem(
            line_no=1,
            name="Material",
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
            total_amount=Decimal("100.00"),
        )
    ]
    db_session.add(receipt)
    await db_session.flush()

    result = await get_project_receipt_purchases(
        db_session,
        project_id=project.id,
        from_date=date(2026, 7, 1),
        to_date=date(2026, 7, 31),
    )

    assert result["project_id"] == project.id
    assert result["project_name"] == project.name
    assert len(result["items"]) == 1
    assert result["items"][0]["receipt_id"] == receipt.id
