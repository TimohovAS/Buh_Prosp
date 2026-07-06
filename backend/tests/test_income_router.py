from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.routers.income_router import bulk_assign_project_income
from backend.schemas import BulkAssignProject

pytestmark = pytest.mark.filterwarnings("ignore:datetime.datetime.utcnow\\(\\) is deprecated:DeprecationWarning")


async def test_bulk_assign_project_income_rejects_regular_archived_project(
    db_session,
    make_income,
    make_project,
):
    archived_project = await make_project(db_session, code="ARCH-INCOME", status="archived")
    income = await make_income(db_session, invoice_number="INV-BULK-1")

    with pytest.raises(HTTPException) as exc_info:
        await bulk_assign_project_income(
            BulkAssignProject(ids=[income.id], project_id=archived_project.id),
            db_session,
            SimpleNamespace(id=1),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Cannot use archived project"


async def test_bulk_assign_project_income_allows_archived_unassigned_project(
    db_session,
    make_income,
    make_project,
):
    unassigned_project = await make_project(
        db_session,
        code="INT-UNASSIGNED",
        name="Unassigned",
        status="archived",
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
