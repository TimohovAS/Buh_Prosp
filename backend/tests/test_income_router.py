from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.income_service import has_invoice_duplicate, invoice_identity
from backend.routers.income_router import bulk_assign_project_income, update_income
from backend.schemas import BulkAssignProject, IncomeUpdate

pytestmark = pytest.mark.filterwarnings("ignore:datetime.datetime.utcnow\\(\\) is deprecated:DeprecationWarning")


async def test_bulk_assign_project_income_rejects_regular_completed_project(
    db_session,
    make_income,
    make_project,
):
    completed_project = await make_project(db_session, code="DONE-INCOME", status="completed")
    income = await make_income(db_session, invoice_number="INV-BULK-1")

    with pytest.raises(HTTPException) as exc_info:
        await bulk_assign_project_income(
            BulkAssignProject(ids=[income.id], project_id=completed_project.id),
            db_session,
            SimpleNamespace(id=1),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Cannot use completed project"


async def test_bulk_assign_project_income_allows_completed_unassigned_project(
    db_session,
    make_income,
    make_project,
):
    unassigned_project = await make_project(
        db_session,
        code="INT-UNASSIGNED",
        name="Unassigned",
        status="completed",
        is_internal=True,
    )
    income = await make_income(db_session, invoice_number="INV-BULK-2")

    result = await bulk_assign_project_income(
        BulkAssignProject(ids=[income.id], project_id=None),
        db_session,
        SimpleNamespace(id=1),
    )

    assert result == {"updated": 1}
    assert income.project_id == unassigned_project.id


async def test_update_income_keeps_existing_completed_project(
    db_session,
    make_income,
    make_project,
):
    project = await make_project(db_session, code="DONE-EDIT-INCOME", status="completed")
    income = await make_income(
        db_session,
        invoice_number="INV-EDIT-DONE",
        project_id=project.id,
    )

    updated = await update_income(
        income.id,
        IncomeUpdate(description="Corrected", project_id=project.id),
        db_session,
        SimpleNamespace(id=1),
    )

    assert updated.project_id == project.id
    assert updated.description == "Corrected"


@pytest.mark.parametrize(
    ("stored", "entered"),
    [
        ("0012-2026-A", "2026-0012-A"),
        ("2026-0012-A2", "0012-2026-A2"),
        ("0012-2026", "2026-12"),
    ],
)
async def test_invoice_duplicate_is_found_across_number_formats(db_session, make_income, stored, entered):
    await make_income(db_session, invoice_number=stored, issued_date=date(2026, 3, 1))

    assert await has_invoice_duplicate(db_session, entered, 2026) is True


@pytest.mark.parametrize("entered", ["0013-2026-A", "0012-2026-B", "0012-2025-A"])
async def test_invoice_with_another_serial_suffix_or_year_is_not_a_duplicate(db_session, make_income, entered):
    await make_income(db_session, invoice_number="0012-2026-A", issued_date=date(2026, 3, 1))

    assert await has_invoice_duplicate(db_session, entered, 2026) is False


def test_invoice_identity_matches_suffixed_numbers_in_both_orders():
    assert invoice_identity("0012-2026-A", 2026) == invoice_identity("2026-0012-A", 2026)
    assert invoice_identity("0012-2026-A", 2026) != invoice_identity("0012-2026-B", 2026)
    # Номера без распознаваемого шаблона остаются как есть, только в верхнем регистре.
    assert invoice_identity("  racun  br 5 ", 2026) == (2026, "RACUN BR 5")
