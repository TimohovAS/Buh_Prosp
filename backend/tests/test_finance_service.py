from datetime import datetime
from decimal import Decimal

from backend.finance_service import get_finance_by_project, get_project_movements
from backend.models import PurchaseReceipt
from backend.tests.conftest import TEST_DATE


async def test_planned_receipt_expense_is_visible_in_accrual_project_finance(
    db_session,
    make_expense,
    make_project,
):
    project = await make_project(db_session, code="PR-RECEIPT")
    receipt_expense = await make_expense(
        db_session,
        amount=Decimal("1487.08"),
        status="planned",
        project_id=project.id,
        source="receipt",
        description="Receipt purchase",
    )
    ordinary_planned_expense = await make_expense(
        db_session,
        amount=Decimal("500.00"),
        status="planned",
        project_id=project.id,
        source="manual",
        description="Future expense",
    )
    receipt = PurchaseReceipt(
        verification_url="https://example.test/receipt",
        qr_hash="planned-receipt-project-finance",
        receipt_datetime=datetime.combine(TEST_DATE, datetime.min.time()),
        total_amount=Decimal("1487.08"),
        status="waiting_bank",
        project_id=project.id,
        expense_id=receipt_expense.id,
    )
    db_session.add(receipt)
    await db_session.flush()

    movements = await get_project_movements(
        db_session,
        project.id,
        TEST_DATE,
        TEST_DATE,
        mode="accrual",
    )
    movement_ids = {item["source_id"] for item in movements["items"]}

    assert receipt_expense.id in movement_ids
    assert ordinary_planned_expense.id not in movement_ids
    receipt_movement = next(item for item in movements["items"] if item["source_id"] == receipt_expense.id)
    assert receipt_movement["receipt_id"] == receipt.id
    assert receipt_movement["amount"] == Decimal("1487.08")

    accrual = await get_finance_by_project(
        db_session,
        TEST_DATE,
        TEST_DATE,
        mode="accrual",
    )
    accrual_row = next(item for item in accrual["by_project"] if item["project_id"] == project.id)
    assert accrual_row["expenses"] == Decimal("1487.08")

    cash = await get_finance_by_project(
        db_session,
        TEST_DATE,
        TEST_DATE,
        mode="cash",
    )
    cash_row = next(item for item in cash["by_project"] if item["project_id"] == project.id)
    assert cash_row["expenses"] == Decimal("0.00")
