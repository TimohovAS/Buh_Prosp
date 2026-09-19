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


async def test_payout_type_can_be_changed_later_without_touching_the_money(attach_client, db_session):
    worker = Worker(name="Andrei Timokhov")
    db_session.add(worker)
    await db_session.flush()
    entry, expense = await make_cash_expense(db_session, description="Andrei Timokhov Struja")
    attached = (
        await attach_client.post(
            "/api/workers/payouts/attach",
            json={"cash_entry_id": entry.id, "worker_id": worker.id},
        )
    ).json()["payout"]

    response = await attach_client.patch(
        f"/api/workers/payouts/{attached['id']}/link",
        json={
            "worker_id": worker.id,
            "payout_type": "monthly",
            "period_start": "2026-02-01",
            "period_end": "2026-02-28",
        },
    )

    assert response.status_code == 200
    assert response.json()["payout"]["payout_type"] == "monthly"

    payout = (await db_session.execute(select(WorkerPayout))).scalar_one()
    assert payout.payout_type == "monthly"
    assert payout.period_start == date(2026, 2, 1)
    assert payout.period_end == date(2026, 2, 28)
    assert Decimal(payout.cash_paid_amount) == Decimal("15000.00")
    # Ни описание операции, ни расход правка типа трогать не должна.
    assert payout.description == "Andrei Timokhov Struja"
    assert entry.description == "Andrei Timokhov Struja"
    assert expense.description == "Andrei Timokhov Struja"
    assert Decimal(expense.amount) == Decimal("15000.00")


async def test_payout_link_update_can_move_the_record_to_another_worker(attach_client, db_session):
    worker = Worker(name="Andrei Timokhov")
    other = Worker(name="Denis Čistjakov")
    db_session.add_all([worker, other])
    await db_session.flush()
    entry, _ = await make_cash_expense(db_session)
    attached = (
        await attach_client.post(
            "/api/workers/payouts/attach",
            json={"cash_entry_id": entry.id, "worker_id": worker.id},
        )
    ).json()["payout"]

    response = await attach_client.patch(
        f"/api/workers/payouts/{attached['id']}/link",
        json={"worker_id": other.id, "payout_type": "weekly"},
    )

    assert response.status_code == 200
    payout = (await db_session.execute(select(WorkerPayout))).scalar_one()
    assert payout.worker_id == other.id


async def test_payout_link_update_rejects_bad_type_and_period(attach_client, db_session):
    worker = Worker(name="Andrei Timokhov")
    db_session.add(worker)
    await db_session.flush()
    entry, _ = await make_cash_expense(db_session)
    attached = (
        await attach_client.post(
            "/api/workers/payouts/attach",
            json={"cash_entry_id": entry.id, "worker_id": worker.id},
        )
    ).json()["payout"]

    bad_type = await attach_client.patch(
        f"/api/workers/payouts/{attached['id']}/link",
        json={"worker_id": worker.id, "payout_type": "bonus"},
    )
    bad_period = await attach_client.patch(
        f"/api/workers/payouts/{attached['id']}/link",
        json={
            "worker_id": worker.id,
            "payout_type": "regular",
            "period_start": "2026-02-28",
            "period_end": "2026-02-01",
        },
    )

    assert bad_type.status_code == 400
    assert bad_period.status_code == 400
    payout = (await db_session.execute(select(WorkerPayout))).scalar_one()
    assert payout.payout_type == "regular"


async def test_payout_link_update_returns_404_for_unknown_payout(attach_client, db_session):
    worker = Worker(name="Andrei Timokhov")
    db_session.add(worker)
    await db_session.flush()

    response = await attach_client.patch(
        "/api/workers/payouts/999/link",
        json={"worker_id": worker.id, "payout_type": "regular"},
    )

    assert response.status_code == 404
