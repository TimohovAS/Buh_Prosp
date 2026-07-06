from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.database import Base
from backend.models import BankTransaction, Expense, Income, Project

TEST_NOW = datetime(2026, 7, 6, 9, 0, 0)
TEST_DATE = date(2026, 7, 6)


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def make_project():
    async def _make_project(db, *, code="PR-1", name="Project", status="active", is_internal=False):
        project = Project(
            code=code,
            name=name,
            status=status,
            is_internal=is_internal,
            created_at=TEST_NOW,
            updated_at=TEST_NOW,
        )
        db.add(project)
        await db.flush()
        return project

    return _make_project


@pytest.fixture
def make_unassigned_project(make_project):
    async def _make_unassigned_project(db):
        return await make_project(db, code="INT-UNASSIGNED", name="Unassigned", is_internal=True)

    return _make_unassigned_project


@pytest.fixture
def make_income():
    async def _make_income(
        db,
        *,
        amount=Decimal("100.00"),
        status="issued",
        paid_amount=Decimal("0.00"),
        issued_date=TEST_DATE,
        invoice_number="INV-001",
        client_name="Client",
        project_id=None,
    ):
        income = Income(
            issued_date=issued_date,
            invoice_number=invoice_number,
            invoice_year=issued_date.year,
            client_name=client_name,
            amount_rsd=Decimal(str(amount)),
            currency="RSD",
            exchange_rate=1.0,
            is_paid=status == "paid",
            paid_amount=Decimal(str(paid_amount)),
            status=status,
            project_id=project_id,
            created_at=TEST_NOW,
            updated_at=TEST_NOW,
        )
        db.add(income)
        await db.flush()
        return income

    return _make_income


@pytest.fixture
def make_expense():
    async def _make_expense(
        db,
        *,
        amount=Decimal("100.00"),
        status="planned",
        expense_date=TEST_DATE,
        description="Expense",
        project_id=None,
        contract_id=None,
        source="manual",
    ):
        expense = Expense(
            date=expense_date,
            description=description,
            amount=Decimal(str(amount)),
            currency="RSD",
            status=status,
            paid_date=expense_date if status == "paid" else None,
            project_id=project_id,
            contract_id=contract_id,
            source=source,
            is_tax_related=False,
            created_at=TEST_NOW,
        )
        db.add(expense)
        await db.flush()
        return expense

    return _make_expense


@pytest.fixture
def make_bank_tx():
    async def _make_bank_tx(
        db,
        *,
        amount=Decimal("100.00"),
        direction="in",
        status="unmatched",
        tx_date=TEST_DATE,
        counterparty_name="Counterparty",
        purpose="Payment",
        bank_reference="REF-001",
        project_id=None,
    ):
        tx = BankTransaction(
            date=tx_date,
            amount=Decimal(str(amount)),
            direction=direction,
            currency="RSD",
            counterparty_name=counterparty_name,
            purpose=purpose,
            bank_reference=bank_reference,
            status=status,
            project_id=project_id,
            created_at=TEST_NOW,
        )
        db.add(tx)
        await db.flush()
        return tx

    return _make_bank_tx
