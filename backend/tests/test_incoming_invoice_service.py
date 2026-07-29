from datetime import date
from decimal import Decimal

import pytest

from backend.incoming_invoice_service import create_incoming_invoice, update_incoming_invoice
from backend.models import Expense, IncomingInvoice, Project
from backend.tests.conftest import TEST_NOW

NOW = TEST_NOW


async def test_create_incoming_invoice_rejects_completed_project(db_session):
    project = Project(code="DONE-001", name="Completed", status="completed", created_at=NOW, updated_at=NOW)
    db_session.add(project)
    await db_session.flush()

    with pytest.raises(ValueError, match="Cannot use completed project"):
        await create_incoming_invoice(
            db_session,
            invoice_number="IN-001",
            invoice_date=date(2026, 7, 6),
            client_id=None,
            counterparty_name="Supplier",
            project_id=project.id,
            amount=Decimal("100.00"),
        )


async def test_update_incoming_invoice_rejects_completed_project(db_session):
    active_project = Project(code="ACT-001", name="Active", status="active", created_at=NOW, updated_at=NOW)
    completed_project = Project(code="DONE-001", name="Completed", status="completed", created_at=NOW, updated_at=NOW)
    db_session.add_all([active_project, completed_project])
    await db_session.flush()

    invoice = IncomingInvoice(
        invoice_number="IN-001",
        date=date(2026, 7, 6),
        counterparty_name="Supplier",
        project_id=active_project.id,
        amount=Decimal("100.00"),
        status="unpaid",
        created_at=NOW,
    )
    db_session.add(invoice)
    await db_session.flush()

    with pytest.raises(ValueError, match="Cannot use completed project"):
        await update_incoming_invoice(db_session, invoice, project_id=completed_project.id)

    assert invoice.project_id == active_project.id


async def test_update_incoming_invoice_keeps_existing_completed_project(db_session):
    project = Project(code="DONE-EDIT", name="Completed", status="active", created_at=NOW, updated_at=NOW)
    db_session.add(project)
    await db_session.flush()
    invoice = await create_incoming_invoice(
        db_session,
        invoice_number="IN-EDIT",
        invoice_date=date(2026, 7, 6),
        client_id=None,
        counterparty_name="Supplier",
        project_id=project.id,
        amount=Decimal("100.00"),
    )
    project.status = "completed"
    await db_session.flush()

    updated = await update_incoming_invoice(
        db_session,
        invoice,
        project_id=project.id,
        description="Corrected",
    )

    assert updated.project_id == project.id
    assert updated.description == "Corrected"
    expense = await db_session.get(Expense, invoice.expense_id)
    assert expense.project_id == project.id
