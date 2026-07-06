from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.database import Base
from backend.incoming_invoice_service import create_incoming_invoice, update_incoming_invoice
from backend.models import IncomingInvoice, Project

NOW = datetime(2026, 7, 6, 8, 0, 0)


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session

    await engine.dispose()


async def test_create_incoming_invoice_rejects_archived_project(db_session):
    project = Project(code="ARCH-001", name="Archived", status="archived", created_at=NOW, updated_at=NOW)
    db_session.add(project)
    await db_session.flush()

    with pytest.raises(ValueError, match="Cannot use archived project"):
        await create_incoming_invoice(
            db_session,
            invoice_number="IN-001",
            invoice_date=date(2026, 7, 6),
            client_id=None,
            counterparty_name="Supplier",
            project_id=project.id,
            amount=Decimal("100.00"),
        )


async def test_update_incoming_invoice_rejects_archived_project(db_session):
    active_project = Project(code="ACT-001", name="Active", status="active", created_at=NOW, updated_at=NOW)
    archived_project = Project(code="ARCH-001", name="Archived", status="archived", created_at=NOW, updated_at=NOW)
    db_session.add_all([active_project, archived_project])
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

    with pytest.raises(ValueError, match="Cannot use archived project"):
        await update_incoming_invoice(db_session, invoice, project_id=archived_project.id)

    assert invoice.project_id == active_project.id
