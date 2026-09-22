"""Зарплата за месяц закрывается частями: деньгами и покупками в её счёт."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.auth import get_current_user_required, require_edit_access
from backend.database import get_db
from backend.expense_service import unlink_worker_payout_from_expense
from backend.models import Expense, PlannedExpense, PlannedExpensePayment, Worker, WorkerPayout
from backend.planned_expenses_service import sync_worker_payout_planned_payment
from backend.routers.planned_expenses_router import router as planned_router
from backend.routers.workers_router import router as workers_router
from backend.services import create_expense_reversal

SALARY = Decimal("100000.00")
PURCHASE = Decimal("20000.00")
MONEY = Decimal("80000.00")
DUE_DATE = date(2026, 9, 5)


@pytest.fixture
async def client(db_session):
    app = FastAPI()
    app.include_router(workers_router, prefix="/api")
    app.include_router(planned_router, prefix="/api")

    async def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user_required] = lambda: SimpleNamespace(id=1, role="admin")
    app.dependency_overrides[require_edit_access] = lambda: SimpleNamespace(id=1, role="admin")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http_client:
        yield http_client


async def make_worker_with_salary_plan(db):
    worker = Worker(name="Andrei Timokhov", monthly_rate=SALARY)
    db.add(worker)
    await db.flush()
    db.add(
        PlannedExpense(
            name="Andrei Timokhov",
            amount=SALARY,
            currency="RSD",
            period="monthly",
            payment_day=DUE_DATE.day,
            start_date=date(2026, 1, 5),
            is_active=True,
            worker_id=worker.id,
        )
    )
    await db.flush()
    return worker


async def make_expense(db, amount, *, entry_date=date(2026, 9, 4), description="Kartica : SALAS RUSTIK"):
    expense = Expense(
        date=entry_date,
        description=description,
        amount=Decimal(amount),
        currency="RSD",
        category="Зарплата",
        source="bank_import",
        status="paid",
        paid_date=entry_date,
    )
    db.add(expense)
    await db.flush()
    return expense


async def add_money_payout(db, worker, amount, *, payout_date=date(2026, 9, 5)):
    """Обычная выплата зарплаты деньгами, заведённая модулем выплат."""
    payout = WorkerPayout(
        worker_id=worker.id,
        payout_type="monthly",
        date=payout_date,
        monthly_rate=SALARY,
        gross_amount=SALARY,
        cash_paid_amount=Decimal(amount),
        remaining_amount=SALARY - Decimal(amount),
        description="worker_payout:monthly: Andrei Timokhov",
    )
    db.add(payout)
    await db.flush()
    await sync_worker_payout_planned_payment(db, payout)
    return payout


async def settled_total(db):
    rows = (await db.execute(select(PlannedExpensePayment))).scalars().all()
    return sum((Decimal(row.amount) for row in rows), Decimal("0"))


async def occurrence(client):
    items = (await client.get("/api/planned-expenses/upcoming", params={"days": 365})).json()
    return next(item for item in items if item["due_date"] == DUE_DATE.isoformat())


async def test_purchase_and_money_together_close_the_month(client, db_session):
    worker = await make_worker_with_salary_plan(db_session)
    purchase_expense = await make_expense(db_session, PURCHASE)
    await client.post(
        "/api/workers/payouts/attach",
        json={
            "expense_id": purchase_expense.id,
            "worker_id": worker.id,
            "payout_type": "purchase",
            "period_start": "2026-09-01",
            "period_end": "2026-09-30",
        },
    )

    after_purchase = await occurrence(client)
    assert Decimal(str(after_purchase["paid_amount"])) == PURCHASE
    assert Decimal(str(after_purchase["remaining_amount"])) == Decimal("80000.00")
    # Остаток есть, значит напоминание открыто.
    assert after_purchase["is_paid"] is False

    await add_money_payout(db_session, worker, MONEY)

    closed = await occurrence(client)
    assert Decimal(str(closed["paid_amount"])) == SALARY
    assert Decimal(str(closed["remaining_amount"])) == Decimal("0")
    assert closed["is_paid"] is True

    report = (await client.get("/api/workers/payouts/report")).json()
    row = report["workers"][0]
    assert Decimal(str(row["money_paid"])) == MONEY
    assert Decimal(str(row["purchase_paid"])) == PURCHASE
    assert Decimal(str(row["regular_paid"])) + Decimal(str(row["purchase_paid"])) == SALARY


async def test_unlinking_the_purchase_reopens_the_remainder(client, db_session):
    worker = await make_worker_with_salary_plan(db_session)
    purchase_expense = await make_expense(db_session, PURCHASE)
    attached = (
        await client.post(
            "/api/workers/payouts/attach",
            json={
                "expense_id": purchase_expense.id,
                "worker_id": worker.id,
                "payout_type": "purchase",
                "period_start": "2026-09-01",
                "period_end": "2026-09-30",
            },
        )
    ).json()["payout"]
    await add_money_payout(db_session, worker, MONEY)
    assert (await occurrence(client))["is_paid"] is True

    await client.delete(f"/api/workers/payouts/{attached['id']}/link")

    reopened = await occurrence(client)
    assert Decimal(str(reopened["paid_amount"])) == MONEY
    assert Decimal(str(reopened["remaining_amount"])) == PURCHASE
    assert reopened["is_paid"] is False
    report = (await client.get("/api/workers/payouts/report")).json()
    assert Decimal(str(report["workers"][0]["purchase_paid"])) == Decimal("0")


async def test_reversing_the_purchase_reopens_the_remainder(client, db_session):
    worker = await make_worker_with_salary_plan(db_session)
    purchase_expense = await make_expense(db_session, PURCHASE)
    await client.post(
        "/api/workers/payouts/attach",
        json={
            "expense_id": purchase_expense.id,
            "worker_id": worker.id,
            "payout_type": "purchase",
            "period_start": "2026-09-01",
            "period_end": "2026-09-30",
        },
    )
    await add_money_payout(db_session, worker, MONEY)
    assert (await occurrence(client))["is_paid"] is True

    await create_expense_reversal(db_session, purchase_expense)

    reopened = await occurrence(client)
    assert Decimal(str(reopened["remaining_amount"])) == PURCHASE
    assert reopened["is_paid"] is False


async def test_a_second_purchase_cannot_settle_more_than_the_month_owes(client, db_session):
    worker = await make_worker_with_salary_plan(db_session)
    await add_money_payout(db_session, worker, MONEY)
    big_purchase = await make_expense(db_session, Decimal("50000.00"))

    await client.post(
        "/api/workers/payouts/attach",
        json={
            "expense_id": big_purchase.id,
            "worker_id": worker.id,
            "payout_type": "purchase",
            "period_start": "2026-09-01",
            "period_end": "2026-09-30",
        },
    )

    # Зарплата закрыта ровно на свою сумму, лишнее к периоду не приписано.
    assert await settled_total(db_session) == SALARY
    closed = await occurrence(client)
    assert Decimal(str(closed["remaining_amount"])) == Decimal("0")
    # В доходе работника покупка при этом учтена целиком.
    report = (await client.get("/api/workers/payouts/report")).json()
    assert Decimal(str(report["workers"][0]["purchase_paid"])) == Decimal("50000.00")


async def test_marking_by_hand_closes_only_what_is_left(client, db_session):
    worker = await make_worker_with_salary_plan(db_session)
    purchase_expense = await make_expense(db_session, PURCHASE)
    await client.post(
        "/api/workers/payouts/attach",
        json={
            "expense_id": purchase_expense.id,
            "worker_id": worker.id,
            "payout_type": "purchase",
            "period_start": "2026-09-01",
            "period_end": "2026-09-30",
        },
    )

    plan = (await db_session.execute(select(PlannedExpense))).scalar_one()
    marked = await client.post(
        "/api/planned-expenses/mark-paid",
        json={
            "planned_expense_id": plan.id,
            "due_date": DUE_DATE.isoformat(),
            "paid_date": DUE_DATE.isoformat(),
        },
    )

    assert marked.status_code == 200
    assert Decimal(str(marked.json()["amount"])) == Decimal("80000.00")
    assert await settled_total(db_session) == SALARY
    assert (await occurrence(client))["is_paid"] is True

    again = await client.post(
        "/api/planned-expenses/mark-paid",
        json={
            "planned_expense_id": plan.id,
            "due_date": DUE_DATE.isoformat(),
            "paid_date": DUE_DATE.isoformat(),
        },
    )
    assert again.status_code == 400


async def test_deleting_the_purchase_expense_reopens_the_remainder(client, db_session):
    worker = await make_worker_with_salary_plan(db_session)
    purchase_expense = await make_expense(db_session, PURCHASE)
    await client.post(
        "/api/workers/payouts/attach",
        json={
            "expense_id": purchase_expense.id,
            "worker_id": worker.id,
            "payout_type": "purchase",
            "period_start": "2026-09-01",
            "period_end": "2026-09-30",
        },
    )
    await add_money_payout(db_session, worker, MONEY)

    await unlink_worker_payout_from_expense(db_session, purchase_expense.id)

    assert Decimal(str((await occurrence(client))["remaining_amount"])) == PURCHASE


async def test_the_split_does_not_depend_on_the_order_of_operations(client, db_session):
    """Сторно одной выплаты перераспределяет остальные, а не оставляет их урезанными."""
    worker = await make_worker_with_salary_plan(db_session)
    purchase_expense = await make_expense(db_session, PURCHASE)
    await client.post(
        "/api/workers/payouts/attach",
        json={
            "expense_id": purchase_expense.id,
            "worker_id": worker.id,
            "payout_type": "purchase",
            "period_start": "2026-09-01",
            "period_end": "2026-09-30",
        },
    )
    # Деньгами выдали всю зарплату, но раскладка идёт по датам выплат, а не по
    # порядку заведения: покупка от 4 сентября считается первой и целиком.
    money_payout = await add_money_payout(db_session, worker, SALARY)
    purchase_mark = (
        await db_session.execute(
            select(PlannedExpensePayment).where(PlannedExpensePayment.worker_payout_id != money_payout.id)
        )
    ).scalar_one()
    assert Decimal(purchase_mark.amount) == PURCHASE
    assert await settled_total(db_session) == SALARY

    money_payout.cancelled_at = date(2026, 9, 30)
    await db_session.flush()
    await sync_worker_payout_planned_payment(db_session, money_payout)

    # После сторно денежной выплаты покупка снова считается целиком.
    marks = (await db_session.execute(select(PlannedExpensePayment))).scalars().all()
    assert len(marks) == 1
    assert Decimal(marks[0].amount) == PURCHASE
    assert Decimal(str((await occurrence(client))["remaining_amount"])) == Decimal("80000.00")


async def test_unmarking_by_hand_keeps_confirmations_of_real_payouts(client, db_session):
    worker = await make_worker_with_salary_plan(db_session)
    purchase_expense = await make_expense(db_session, PURCHASE)
    await client.post(
        "/api/workers/payouts/attach",
        json={
            "expense_id": purchase_expense.id,
            "worker_id": worker.id,
            "payout_type": "purchase",
            "period_start": "2026-09-01",
            "period_end": "2026-09-30",
        },
    )
    plan = (await db_session.execute(select(PlannedExpense))).scalar_one()
    body = {"planned_expense_id": plan.id, "due_date": DUE_DATE.isoformat()}

    refused = await client.post("/api/planned-expenses/mark-unpaid", json=body)

    assert refused.status_code == 400
    assert await settled_total(db_session) == PURCHASE

    # Ручную отметку снять можно — подтверждение покупки при этом остаётся.
    await client.post("/api/planned-expenses/mark-paid", json={**body, "paid_date": DUE_DATE.isoformat()})
    removed = await client.post("/api/planned-expenses/mark-unpaid", json=body)

    assert removed.status_code == 200
    assert await settled_total(db_session) == PURCHASE


async def test_the_same_split_whichever_was_entered_first(client, db_session):
    """Деньги сначала или покупка сначала — раскладка одинаковая."""
    worker = await make_worker_with_salary_plan(db_session)
    await add_money_payout(db_session, worker, SALARY)
    purchase_expense = await make_expense(db_session, PURCHASE)

    await client.post(
        "/api/workers/payouts/attach",
        json={
            "expense_id": purchase_expense.id,
            "worker_id": worker.id,
            "payout_type": "purchase",
            "period_start": "2026-09-01",
            "period_end": "2026-09-30",
        },
    )

    marks = {
        mark.worker_payout_id: Decimal(mark.amount)
        for mark in (await db_session.execute(select(PlannedExpensePayment))).scalars().all()
    }
    assert sorted(marks.values()) == [PURCHASE, Decimal("80000.00")]
    assert await settled_total(db_session) == SALARY
