from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from backend.expense_service import (
    NotFoundError,
    build_expense_item_models,
    clear_contract_if_project_mismatch,
    expense_amount_from_items,
    expense_description_from_items,
    normalize_expense_items,
    resolve_expense_links,
)
from backend.models import Contract, Expense, Project
from backend.tests.conftest import TEST_NOW

NOW = TEST_NOW


def test_normalize_expense_items_computes_total_from_quantity_and_unit_price():
    items = normalize_expense_items(
        [
            {
                "name": "Service",
                "quantity": Decimal("2"),
                "unit_price": Decimal("125.50"),
                "total_amount": Decimal("999.00"),
                "note": "  scheduled  ",
            }
        ]
    )

    assert items == [
        {
            "name": "Service",
            "quantity": Decimal("2"),
            "unit_price": Decimal("125.50"),
            "total_amount": Decimal("251.00"),
            "note": "scheduled",
        }
    ]
    assert expense_amount_from_items(items, Decimal("1.00")) == Decimal("251.00")
    assert expense_description_from_items(items, None) == "Service"

    models = build_expense_item_models(items)
    assert models[0].line_no == 1
    assert models[0].name == "Service"
    assert models[0].total_amount == Decimal("251.00")


def test_expense_item_helpers_use_fallbacks_without_items():
    assert normalize_expense_items([{}]) == []
    assert expense_amount_from_items([], Decimal("45.00")) == Decimal("45.00")
    assert expense_description_from_items([], " Manual description ") == "Manual description"


def test_normalize_expense_items_rejects_payload_without_name():
    with pytest.raises(ValueError, match="Expense item name is required"):
        normalize_expense_items([{"quantity": Decimal("1"), "unit_price": Decimal("10")}])


async def test_resolve_expense_links_rejects_archived_project(db_session):
    project = Project(code="ARCH-EXP", name="Archived", status="archived", created_at=NOW, updated_at=NOW)
    db_session.add(project)
    await db_session.flush()

    with pytest.raises(ValueError, match="Cannot use archived project"):
        await resolve_expense_links(db_session, project.id, None)


async def test_resolve_expense_links_reports_missing_project_as_not_found(db_session):
    with pytest.raises(NotFoundError, match="Project not found"):
        await resolve_expense_links(db_session, 999, None)


async def test_resolve_expense_links_reports_missing_contract_as_not_found(db_session):
    with pytest.raises(NotFoundError, match="Contract not found"):
        await resolve_expense_links(db_session, None, 999)


@pytest.mark.filterwarnings("ignore:datetime.datetime.utcnow\\(\\) is deprecated:DeprecationWarning")
async def test_resolve_expense_links_assigns_project_to_unassigned_contract(db_session):
    project = Project(code="ACT-EXP", name="Active", status="active", created_at=NOW, updated_at=NOW)
    contract = Contract(
        number="C-001",
        date=date(2026, 7, 6),
        client_id=1,
        project_id=None,
        created_at=NOW,
        updated_at=NOW,
    )
    db_session.add_all([project, contract])
    await db_session.flush()

    project_id, contract_id = await resolve_expense_links(db_session, project.id, contract.id)

    assert project_id == project.id
    assert contract_id == contract.id
    assert contract.project_id == project.id

    result = await db_session.execute(select(Contract.id).where(Contract.project_id == project.id))
    assert result.scalar_one() == contract.id


async def test_clear_contract_if_project_mismatch_removes_stale_contract(db_session):
    first_project = Project(code="PRJ-001", name="First", status="active", created_at=NOW, updated_at=NOW)
    second_project = Project(code="PRJ-002", name="Second", status="active", created_at=NOW, updated_at=NOW)
    db_session.add_all([first_project, second_project])
    await db_session.flush()

    contract = Contract(
        number="C-001",
        date=date(2026, 7, 6),
        client_id=1,
        project_id=first_project.id,
        created_at=NOW,
        updated_at=NOW,
    )
    expense = Expense(
        date=date(2026, 7, 6),
        description="Expense",
        amount=Decimal("100.00"),
        project_id=second_project.id,
        contract_id=contract.id,
        created_at=NOW,
    )
    db_session.add_all([contract, expense])
    await db_session.flush()

    await clear_contract_if_project_mismatch(db_session, expense, second_project.id)

    assert expense.contract_id is None
