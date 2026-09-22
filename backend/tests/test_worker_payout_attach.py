from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.auth import get_current_user_required, require_edit_access
from backend.database import get_db
from backend.expense_service import (
    PAYOUT_ORIGIN_CALCULATED,
    PAYOUT_ORIGIN_EXPENSE_LINK,
    PayoutCurrencyError,
    merge_duplicate_expenses,
    restore_worker_payout_for_expense,
    sync_worker_payout_from_expense,
    unlink_worker_payout_from_expense,
)
from backend.models import CashEntry, Expense, PlannedExpense, PlannedExpensePayment, Worker, WorkerPayout
from backend.routers.workers_router import router
from backend.services import create_expense_reversal


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


async def make_card_expense(
    db,
    *,
    amount="5260.00",
    entry_date=date(2026, 9, 18),
    description="Kartica 4025480007356295 : SALAS RUSTIK",
    status="paid",
    project_id=None,
):
    """Покупка с карты: расход есть, записи в кассе нет."""
    expense = Expense(
        date=entry_date,
        description=description,
        amount=Decimal(amount),
        currency="RSD",
        category="Зарплата",
        source="bank_import",
        status=status,
        paid_date=entry_date,
        project_id=project_id,
    )
    db.add(expense)
    await db.flush()
    return expense


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


async def test_purchase_for_a_worker_is_counted_in_the_report_without_a_cash_entry(attach_client, db_session):
    worker = Worker(name="Andrei Timokhov")
    db_session.add(worker)
    await db_session.flush()
    expense = await make_card_expense(db_session)

    response = await attach_client.post(
        "/api/workers/payouts/attach",
        json={
            "expense_id": expense.id,
            "worker_id": worker.id,
            "payout_type": "purchase",
            "period_start": "2026-09-01",
            "period_end": "2026-09-30",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["cash_entry"] is None
    assert payload["payout"]["payout_type"] == "purchase"

    payout = (await db_session.execute(select(WorkerPayout))).scalar_one()
    assert payout.expense_id == expense.id
    assert payout.cash_entry_id is None
    assert payout.date == date(2026, 9, 18)
    assert Decimal(payout.cash_paid_amount) == Decimal("5260.00")
    assert expense.description == "Kartica 4025480007356295 : SALAS RUSTIK"

    report = (await attach_client.get("/api/workers/payouts/report")).json()
    assert Decimal(report["total_paid"]) == Decimal("5260.00")
    # Доход работника, но выданный не деньгами: в обычную выплату не попадает.
    worker_row = report["workers"][0]
    assert Decimal(worker_row["purchase_paid"]) == Decimal("5260.00")
    assert Decimal(worker_row["money_paid"]) == Decimal("0")
    assert Decimal(worker_row["regular_paid"]) == Decimal("0")
    assert Decimal(worker_row["trip_paid"]) == Decimal("0")
    assert Decimal(worker_row["lodging_paid"]) == Decimal("0")


async def test_attach_by_expense_id_also_links_the_cash_entry_of_a_cash_expense(attach_client, db_session):
    worker = Worker(name="Andrei Timokhov")
    db_session.add(worker)
    await db_session.flush()
    entry, expense = await make_cash_expense(db_session)

    response = await attach_client.post(
        "/api/workers/payouts/attach",
        json={"expense_id": expense.id, "worker_id": worker.id},
    )

    assert response.status_code == 200
    assert response.json()["cash_entry"]["id"] == entry.id
    payout = (await db_session.execute(select(WorkerPayout))).scalar_one()
    assert payout.cash_entry_id == entry.id


async def test_attach_is_rejected_for_a_reversed_expense(attach_client, db_session):
    worker = Worker(name="Andrei Timokhov")
    db_session.add(worker)
    await db_session.flush()
    expense = await make_card_expense(db_session, status="reversed")

    response = await attach_client.post(
        "/api/workers/payouts/attach",
        json={
            "expense_id": expense.id,
            "worker_id": worker.id,
            "payout_type": "purchase",
            "period_start": "2026-09-01",
            "period_end": "2026-09-30",
        },
    )

    assert response.status_code == 400
    assert (await db_session.execute(select(WorkerPayout))).scalars().all() == []


async def test_attach_requires_exactly_one_target(attach_client, db_session):
    worker = Worker(name="Andrei Timokhov")
    db_session.add(worker)
    await db_session.flush()
    entry, expense = await make_cash_expense(db_session)

    both = await attach_client.post(
        "/api/workers/payouts/attach",
        json={"cash_entry_id": entry.id, "expense_id": expense.id, "worker_id": worker.id},
    )
    neither = await attach_client.post("/api/workers/payouts/attach", json={"worker_id": worker.id})

    assert both.status_code == 422
    assert neither.status_code == 422


async def test_purchase_type_can_be_changed_without_a_cash_entry(attach_client, db_session):
    worker = Worker(name="Andrei Timokhov")
    db_session.add(worker)
    await db_session.flush()
    expense = await make_card_expense(db_session)
    attached = (
        await attach_client.post(
            "/api/workers/payouts/attach",
            json={
                "expense_id": expense.id,
                "worker_id": worker.id,
                "payout_type": "purchase",
                "period_start": "2026-09-01",
                "period_end": "2026-09-30",
            },
        )
    ).json()["payout"]

    response = await attach_client.patch(
        f"/api/workers/payouts/{attached['id']}/link",
        json={"worker_id": worker.id, "payout_type": "monthly"},
    )

    assert response.status_code == 200
    assert response.json()["cash_entry"] is None
    payout = (await db_session.execute(select(WorkerPayout))).scalar_one()
    assert payout.payout_type == "monthly"
    assert Decimal(payout.cash_paid_amount) == Decimal("5260.00")


async def attach_card_expense(client, db, *, currency="RSD", amount="5260.00", status="paid"):
    worker = Worker(name="Andrei Timokhov")
    db.add(worker)
    await db.flush()
    expense = await make_card_expense(db, amount=amount, status=status)
    expense.currency = currency
    await db.flush()
    response = await client.post(
        "/api/workers/payouts/attach",
        json={
            "expense_id": expense.id,
            "worker_id": worker.id,
            "payout_type": "purchase",
            "period_start": "2026-09-01",
            "period_end": "2026-09-30",
        },
    )
    return worker, expense, response


async def test_attach_is_rejected_for_an_expense_that_was_already_reversed(attach_client, db_session):
    worker = Worker(name="Andrei Timokhov")
    db_session.add(worker)
    await db_session.flush()
    expense = await make_card_expense(db_session)
    await create_expense_reversal(db_session, expense)

    response = await attach_client.post(
        "/api/workers/payouts/attach",
        json={
            "expense_id": expense.id,
            "worker_id": worker.id,
            "payout_type": "purchase",
            "period_start": "2026-09-01",
            "period_end": "2026-09-30",
        },
    )

    assert response.status_code == 400
    assert (await db_session.execute(select(WorkerPayout))).scalars().all() == []


async def test_reversing_an_expense_takes_it_out_of_the_worker_income(attach_client, db_session):
    _, expense, response = await attach_card_expense(attach_client, db_session)
    assert response.status_code == 200

    await create_expense_reversal(db_session, expense)

    # Запись остаётся ради истории, но в доходе больше не участвует.
    payout = (await db_session.execute(select(WorkerPayout))).scalar_one()
    assert payout.cancelled_at is not None
    report = (await attach_client.get("/api/workers/payouts/report")).json()
    assert Decimal(report["total_paid"]) == Decimal("0")
    assert report["payout_count"] == 0
    assert (await attach_client.get("/api/workers/payouts")).json() == []


async def test_cancelling_a_reversal_brings_the_payout_back(attach_client, db_session):
    _, expense, _ = await attach_card_expense(attach_client, db_session)
    await create_expense_reversal(db_session, expense)

    restored = await restore_worker_payout_for_expense(db_session, expense.id)

    assert restored is True
    payout = (await db_session.execute(select(WorkerPayout))).scalar_one()
    assert payout.cancelled_at is None
    report = (await attach_client.get("/api/workers/payouts/report")).json()
    assert Decimal(report["total_paid"]) == Decimal("5260.00")


async def test_editing_the_expense_moves_the_payout_with_it(attach_client, db_session):
    _, expense, response = await attach_card_expense(attach_client, db_session)
    assert response.status_code == 200

    expense.amount = Decimal("7000.00")
    expense.date = date(2026, 9, 25)
    expense.paid_date = date(2026, 9, 25)
    await sync_worker_payout_from_expense(db_session, expense)
    await db_session.flush()

    payout = (await db_session.execute(select(WorkerPayout))).scalar_one()
    assert Decimal(payout.cash_paid_amount) == Decimal("7000.00")
    assert Decimal(payout.gross_amount) == Decimal("7000.00")
    assert payout.date == date(2026, 9, 25)
    report = (await attach_client.get("/api/workers/payouts/report")).json()
    assert Decimal(report["total_paid"]) == Decimal("7000.00")


async def make_calculated_payout(db, *, gross="100000.00", cash_paid="100000.00"):
    """Зарплата, посчитанная по ставке: выплачена полностью, суммы совпали."""
    worker = Worker(name="Andrei Timokhov", monthly_rate=Decimal(gross))
    db.add(worker)
    await db.flush()
    expense = await make_card_expense(db, amount=cash_paid)
    payout = WorkerPayout(
        worker_id=worker.id,
        expense_id=expense.id,
        payout_type="monthly",
        date=expense.date,
        monthly_rate=Decimal(gross),
        gross_amount=Decimal(gross),
        cash_paid_amount=Decimal(cash_paid),
        remaining_amount=Decimal("0"),
        description="worker_payout:monthly: Andrei Timokhov",
        origin=PAYOUT_ORIGIN_CALCULATED,
    )
    db.add(payout)
    await db.flush()
    return worker, expense, payout


async def test_editing_the_expense_keeps_a_fully_paid_accrual_untouched(attach_client, db_session):
    # Начислено и выдано совпадают, но это расчёт по ставке, а не привязка:
    # исправление суммы траты не должно переписывать заработок.
    _, expense, payout = await make_calculated_payout(db_session)

    expense.amount = Decimal("90000.00")
    await sync_worker_payout_from_expense(db_session, expense)
    await db_session.flush()

    assert Decimal(payout.gross_amount) == Decimal("100000.00")
    assert Decimal(payout.cash_paid_amount) == Decimal("90000.00")
    assert Decimal(payout.remaining_amount) == Decimal("10000.00")


async def test_editing_the_expense_moves_a_linked_accrual(attach_client, db_session):
    _, expense, response = await attach_card_expense(attach_client, db_session)
    assert response.json()["payout"]["origin"] == PAYOUT_ORIGIN_EXPENSE_LINK

    expense.amount = Decimal("6000.00")
    await sync_worker_payout_from_expense(db_session, expense)
    await db_session.flush()

    payout = (await db_session.execute(select(WorkerPayout))).scalar_one()
    assert Decimal(payout.gross_amount) == Decimal("6000.00")
    assert Decimal(payout.cash_paid_amount) == Decimal("6000.00")
    assert Decimal(payout.remaining_amount) == Decimal("0")


async def test_attach_is_rejected_for_a_foreign_currency_expense(attach_client, db_session):
    _, _, response = await attach_card_expense(attach_client, db_session, currency="EUR")

    assert response.status_code == 400
    assert (await db_session.execute(select(WorkerPayout))).scalars().all() == []


async def test_unlink_removes_the_payout_and_keeps_the_expense(attach_client, db_session):
    _, expense, response = await attach_card_expense(attach_client, db_session)
    payout_id = response.json()["payout"]["id"]

    unlinked = await attach_client.delete(f"/api/workers/payouts/{payout_id}/link")

    assert unlinked.status_code == 200
    assert unlinked.json()["expense_id"] == expense.id
    assert (await db_session.execute(select(WorkerPayout))).scalars().all() == []
    kept = (await db_session.execute(select(Expense).where(Expense.id == expense.id))).scalar_one()
    assert Decimal(kept.amount) == Decimal("5260.00")
    assert kept.description == "Kartica 4025480007356295 : SALAS RUSTIK"


async def test_unlink_returns_404_for_unknown_payout(attach_client, db_session):
    assert (await attach_client.delete("/api/workers/payouts/999/link")).status_code == 404


async def test_the_same_expense_can_be_attached_again_after_unlinking(attach_client, db_session):
    worker, expense, response = await attach_card_expense(attach_client, db_session)
    payout_id = response.json()["payout"]["id"]
    await attach_client.delete(f"/api/workers/payouts/{payout_id}/link")

    again = await attach_client.post(
        "/api/workers/payouts/attach",
        json={
            "expense_id": expense.id,
            "worker_id": worker.id,
            "payout_type": "purchase",
            "period_start": "2026-09-01",
            "period_end": "2026-09-30",
        },
    )

    assert again.status_code == 200


async def test_deleting_the_expense_clears_the_payout(attach_client, db_session):
    _, expense, _ = await attach_card_expense(attach_client, db_session)

    removed = await unlink_worker_payout_from_expense(db_session, expense.id)

    assert removed is True
    assert (await db_session.execute(select(WorkerPayout))).scalars().all() == []


async def test_foreign_currency_on_a_linked_expense_is_refused(attach_client, db_session):
    _, expense, _ = await attach_card_expense(attach_client, db_session)

    expense.currency = "EUR"
    with pytest.raises(PayoutCurrencyError):
        await sync_worker_payout_from_expense(db_session, expense)


async def test_moving_the_expense_date_moves_the_planned_salary_mark(attach_client, db_session):
    worker = Worker(name="Andrei Timokhov")
    db_session.add(worker)
    await db_session.flush()
    plan = PlannedExpense(
        name="Andrei Timokhov",
        amount=Decimal("50000.00"),
        currency="RSD",
        period="monthly",
        payment_day=5,
        start_date=date(2026, 1, 5),
        is_active=True,
        worker_id=worker.id,
    )
    db_session.add(plan)
    await db_session.flush()
    expense = await make_card_expense(db_session, entry_date=date(2026, 9, 4))
    await attach_client.post(
        "/api/workers/payouts/attach",
        json={"expense_id": expense.id, "worker_id": worker.id, "payout_type": "monthly"},
    )

    marked = (await db_session.execute(select(PlannedExpensePayment))).scalar_one()
    assert marked.due_date == date(2026, 9, 5)

    expense.date = date(2026, 8, 4)
    expense.paid_date = date(2026, 8, 4)
    await sync_worker_payout_from_expense(db_session, expense)
    await db_session.flush()

    moved = (await db_session.execute(select(PlannedExpensePayment))).scalar_one()
    assert moved.due_date == date(2026, 8, 5)


async def test_cancelled_payout_releases_its_planned_salary_mark(attach_client, db_session):
    worker = Worker(name="Andrei Timokhov")
    db_session.add(worker)
    await db_session.flush()
    db_session.add(
        PlannedExpense(
            name="Andrei Timokhov",
            amount=Decimal("50000.00"),
            currency="RSD",
            period="monthly",
            payment_day=5,
            start_date=date(2026, 1, 5),
            is_active=True,
            worker_id=worker.id,
        )
    )
    await db_session.flush()
    expense = await make_card_expense(db_session, entry_date=date(2026, 9, 4))
    await attach_client.post(
        "/api/workers/payouts/attach",
        json={"expense_id": expense.id, "worker_id": worker.id, "payout_type": "monthly"},
    )
    assert (await db_session.execute(select(PlannedExpensePayment))).scalars().all() != []

    await create_expense_reversal(db_session, expense)

    assert (await db_session.execute(select(PlannedExpensePayment))).scalars().all() == []


async def test_merging_a_linked_expense_is_refused(attach_client, db_session):
    _, kept, _ = await attach_card_expense(attach_client, db_session)
    duplicate = await make_card_expense(db_session, description="Kartica duplicate")

    with pytest.raises(ValueError, match="Unlink the worker payout"):
        await merge_duplicate_expenses(db_session, kept.id, [duplicate.id])


async def test_merging_is_allowed_once_the_worker_link_is_gone(attach_client, db_session):
    _, kept, response = await attach_card_expense(attach_client, db_session)
    duplicate = await make_card_expense(db_session, description="Kartica duplicate")
    await attach_client.delete(f"/api/workers/payouts/{response.json()['payout']['id']}/link")

    merged = await merge_duplicate_expenses(db_session, kept.id, [duplicate.id])

    assert merged.id == kept.id


async def test_purchase_needs_the_salary_period_it_belongs_to(attach_client, db_session):
    worker = Worker(name="Andrei Timokhov")
    db_session.add(worker)
    await db_session.flush()
    expense = await make_card_expense(db_session, entry_date=date(2026, 9, 30))

    response = await attach_client.post(
        "/api/workers/payouts/attach",
        json={"expense_id": expense.id, "worker_id": worker.id, "payout_type": "purchase"},
    )

    # Без периода трата 30 сентября закрыла бы октябрьскую зарплату.
    assert response.status_code == 400
    assert (await db_session.execute(select(WorkerPayout))).scalars().all() == []
