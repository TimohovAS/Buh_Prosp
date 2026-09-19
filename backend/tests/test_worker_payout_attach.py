from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.auth import get_current_user_required, require_edit_access
from backend.database import get_db
from backend.models import CashEntry, Expense, Worker, WorkerPayout
from backend.routers.workers_router import router


@pytest.fixture
async def attach_client(db_session):
    app = FastAPI()
    app.include_router(router, prefix="/api")

    async def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user_required] = lambda: SimpleNamespace(id=1, role="admin")
    app.dependency_overrides[require_edit_access] = lambda: SimpleNamespace(id=1, role="admin")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def make_cash_expense(
    db,
    *,
    amount="15000.00",
    entry_date=date(2026, 2, 4),
    description="Andrei Timokhov",
    project_id=None,
    entry_type="expense",
):
    expense = Expense(
        date=entry_date,
        description=description,
        amount=Decimal(amount),
        currency="RSD",
        category="Зарплата",
        source="cash",
        status="paid",
        paid_date=entry_date,
        project_id=project_id,
    )
    db.add(expense)
    await db.flush()
    entry = CashEntry(
        date=entry_date,
        direction="out",
        amount=Decimal(amount),
        currency="RSD",
        description=description,
        entry_type=entry_type,
        expense_id=expense.id,
    )
    db.add(entry)
    await db.flush()
    return entry, expense


async def test_attach_links_legacy_expense_without_touching_the_money(attach_client, db_session, make_project):
    project = await make_project(db_session, code="PR-SALARY")
    worker = Worker(name="Andrei Timokhov")
    db_session.add(worker)
    await db_session.flush()
    entry, expense = await make_cash_expense(db_session, project_id=project.id)

    response = await attach_client.post(
        "/api/workers/payouts/attach",
        json={"cash_entry_id": entry.id, "worker_id": worker.id, "payout_type": "monthly"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["payout"]["worker_id"] == worker.id
    assert payload["payout"]["payout_type"] == "monthly"
    assert payload["cash_entry"]["worker_payout_id"] == payload["payout"]["id"]

    payout = (await db_session.execute(select(WorkerPayout))).scalar_one()
    assert payout.cash_entry_id == entry.id
    assert payout.expense_id == expense.id
    assert payout.date == entry.date
    assert Decimal(payout.cash_paid_amount) == Decimal("15000.00")
    assert Decimal(payout.gross_amount) == Decimal("15000.00")
    assert Decimal(payout.remaining_amount or 0) == Decimal("0")
    assert payout.project_id == project.id
    # Деньги в кассе и расходе должны остаться нетронутыми.
    assert Decimal(entry.amount) == Decimal("15000.00")
    assert entry.description == "Andrei Timokhov"
    assert Decimal(expense.amount) == Decimal("15000.00")


async def test_attached_payout_shows_up_in_the_report(attach_client, db_session):
    worker = Worker(name="Andrei Timokhov")
    db_session.add(worker)
    await db_session.flush()
    entry, _ = await make_cash_expense(db_session)

    await attach_client.post(
        "/api/workers/payouts/attach",
        json={"cash_entry_id": entry.id, "worker_id": worker.id},
    )
    report = (await attach_client.get("/api/workers/payouts/report")).json()

    assert report["payout_count"] == 1
    assert Decimal(report["total_paid"]) == Decimal("15000.00")
    assert Decimal(report["workers"][0]["regular_paid"]) == Decimal("15000.00")


async def test_attach_is_rejected_for_already_linked_entry(attach_client, db_session):
    worker = Worker(name="Andrei Timokhov")
    db_session.add(worker)
    await db_session.flush()
    entry, _ = await make_cash_expense(db_session)
    body = {"cash_entry_id": entry.id, "worker_id": worker.id}

    assert (await attach_client.post("/api/workers/payouts/attach", json=body)).status_code == 200
    second = await attach_client.post("/api/workers/payouts/attach", json=body)

    assert second.status_code == 400
    assert len((await db_session.execute(select(WorkerPayout))).scalars().all()) == 1


async def test_attach_is_rejected_for_non_expense_entries(attach_client, db_session):
    worker = Worker(name="Andrei Timokhov")
    db_session.add(worker)
    await db_session.flush()
    entry = CashEntry(
        date=date(2026, 2, 4),
        direction="in",
        amount=Decimal("15000.00"),
        currency="RSD",
        description="Isplata gotovine",
        entry_type="withdrawal",
    )
    db_session.add(entry)
    await db_session.flush()

    response = await attach_client.post(
        "/api/workers/payouts/attach",
        json={"cash_entry_id": entry.id, "worker_id": worker.id},
    )

    assert response.status_code == 400
    assert (await db_session.execute(select(WorkerPayout))).scalars().all() == []


async def test_attach_accepts_archived_worker(attach_client, db_session):
    worker = Worker(name="Zlatko Bavanski", is_active=False)
    db_session.add(worker)
    await db_session.flush()
    entry, _ = await make_cash_expense(db_session, description="Zlatko Bavanski")

    response = await attach_client.post(
        "/api/workers/payouts/attach",
        json={"cash_entry_id": entry.id, "worker_id": worker.id},
    )

    assert response.status_code == 200


async def test_attach_rejects_unknown_payout_type(attach_client, db_session):
    worker = Worker(name="Andrei Timokhov")
    db_session.add(worker)
    await db_session.flush()
    entry, _ = await make_cash_expense(db_session)

    response = await attach_client.post(
        "/api/workers/payouts/attach",
        json={"cash_entry_id": entry.id, "worker_id": worker.id, "payout_type": "bonus"},
    )

    assert response.status_code == 400
