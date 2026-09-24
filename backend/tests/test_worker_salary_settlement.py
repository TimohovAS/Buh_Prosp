"""Зарплата за месяц закрывается частями: деньгами и покупками в её счёт."""

import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, update

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


async def test_saving_the_payout_form_after_a_purchase_pays_only_the_rest(client, db_session):
    """Главный пользовательский путь: форма отправляет cash_paid_amount = null."""
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

    saved = await client.post(
        "/api/workers/payouts",
        json={
            "worker_id": worker.id,
            "payout_type": "monthly",
            "date": DUE_DATE.isoformat(),
            "cash_paid_amount": None,
        },
    )

    assert saved.status_code == 200
    payout = saved.json()["payout"]
    # Ставка 100 000, но 20 000 уже выданы покупкой — деньгами причитается 80 000.
    assert Decimal(str(payout["cash_paid_amount"])) == MONEY
    assert Decimal(str(payout["gross_amount"])) == SALARY
    assert Decimal(str(payout["remaining_amount"])) == Decimal("0")

    report = (await client.get("/api/workers/payouts/report")).json()
    row = report["workers"][0]
    assert Decimal(str(row["money_paid"])) + Decimal(str(row["purchase_paid"])) == SALARY
    assert (await occurrence(client))["is_paid"] is True


async def test_a_purchase_covering_several_weeks_closes_them_all(client, db_session):
    worker = Worker(name="Denis Čistjakov", weekly_rate=Decimal("20000.00"))
    db_session.add(worker)
    await db_session.flush()
    db_session.add(
        PlannedExpense(
            name="Denis Čistjakov",
            amount=Decimal("20000.00"),
            currency="RSD",
            period="weekly",
            payment_day_of_week=0,
            start_date=date(2026, 9, 7),
            is_active=True,
            worker_id=worker.id,
        )
    )
    await db_session.flush()
    expense = await make_expense(db_session, Decimal("50000.00"), entry_date=date(2026, 9, 7))

    await client.post(
        "/api/workers/payouts/attach",
        json={
            "expense_id": expense.id,
            "worker_id": worker.id,
            "payout_type": "purchase",
            "period_start": "2026-09-07",
            "period_end": "2026-09-27",
        },
    )

    marks = (await db_session.execute(select(PlannedExpensePayment))).scalars().all()
    # 20 000 + 20 000 + 10 000: покупка закрывает три недели, а не одну.
    assert sorted(Decimal(mark.amount) for mark in marks) == [
        Decimal("10000.00"),
        Decimal("20000.00"),
        Decimal("20000.00"),
    ]
    assert await settled_total(db_session) == Decimal("50000.00")


async def test_removing_a_manual_mark_redistributes_the_purchase(client, db_session):
    worker = await make_worker_with_salary_plan(db_session)
    plan = (await db_session.execute(select(PlannedExpense))).scalar_one()
    body = {"planned_expense_id": plan.id, "due_date": DUE_DATE.isoformat()}
    # Сначала зарплату закрыли вручную целиком.
    await client.post("/api/planned-expenses/mark-paid", json={**body, "paid_date": DUE_DATE.isoformat()})
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
    assert await settled_total(db_session) == SALARY

    removed = await client.post("/api/planned-expenses/mark-unpaid", json=body)

    assert removed.status_code == 200
    # Место освободилось — покупка должна занять его, а не остаться ни при чём.
    assert await settled_total(db_session) == PURCHASE
    assert Decimal(str((await occurrence(client))["remaining_amount"])) == Decimal("80000.00")


async def attach_purchase(client, worker, expense, *, start="2026-09-01", end="2026-09-30"):
    response = await client.post(
        "/api/workers/payouts/attach",
        json={
            "expense_id": expense.id,
            "worker_id": worker.id,
            "payout_type": "purchase",
            "period_start": start,
            "period_end": end,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["payout"]


async def test_a_month_closed_by_a_purchase_is_not_paid_again_by_rate(client, db_session):
    worker = await make_worker_with_salary_plan(db_session)
    # Август выплачен как обычно, сентябрь целиком закрыт покупкой.
    await add_money_payout(db_session, worker, SALARY, payout_date=date(2026, 8, 5))
    await attach_purchase(client, worker, await make_expense(db_session, SALARY))

    saved = await client.post(
        "/api/workers/payouts",
        json={"worker_id": worker.id, "payout_type": "monthly", "date": DUE_DATE.isoformat(), "cash_paid_amount": None},
    )

    # Покупка закрыла всю зарплату — полная ставка сверху была бы переплатой.
    assert saved.status_code == 400
    assert "fully settled" in saved.json()["detail"]
    monthly = (await db_session.execute(select(WorkerPayout).where(WorkerPayout.payout_type == "monthly"))).scalars()
    assert [payout.date for payout in monthly] == [date(2026, 8, 5)]

    # С явным периодом сентября — тот же отказ.
    with_period = await client.post(
        "/api/workers/payouts",
        json={
            "worker_id": worker.id,
            "payout_type": "monthly",
            "date": DUE_DATE.isoformat(),
            "period_start": "2026-09-01",
            "period_end": "2026-09-30",
            "cash_paid_amount": None,
        },
    )
    assert with_period.status_code == 400

    # Явно названная сумма (премия сверху) по-прежнему проходит.
    bonus = await client.post(
        "/api/workers/payouts",
        json={"worker_id": worker.id, "payout_type": "monthly", "date": DUE_DATE.isoformat(), "cash_paid_amount": 5000},
    )
    assert bonus.status_code == 200


async def test_the_form_gets_the_remainder_of_the_month_it_is_paying(client, db_session):
    worker = await make_worker_with_salary_plan(db_session)
    # Сентябрь недоплачен: закрыто 20 000 покупкой.
    await attach_purchase(client, worker, await make_expense(db_session, PURCHASE))

    september = (await client.get(f"/api/workers/{worker.id}/salary-remaining", params={"date": "2026-09-05"})).json()
    october = (
        await client.get(
            f"/api/workers/{worker.id}/salary-remaining",
            params={"date": "2026-10-05", "period_start": "2026-10-01", "period_end": "2026-10-31"},
        )
    ).json()

    assert september["due_dates"] == ["2026-09-05"]
    assert Decimal(str(september["remaining"])) == MONEY
    assert Decimal(str(september["settled"])) == PURCHASE
    # Октябрьская зарплата — своя, не сентябрьский остаток.
    assert october["due_dates"] == ["2026-10-05"]
    assert Decimal(str(october["remaining"])) == SALARY
    assert Decimal(str(october["settled"])) == Decimal("0")


async def test_salary_remaining_reports_no_plan(client, db_session):
    worker = Worker(name="Without plan")
    db_session.add(worker)
    await db_session.flush()

    balance = (await client.get(f"/api/workers/{worker.id}/salary-remaining", params={"date": "2026-09-05"})).json()

    assert balance["has_plan"] is False


async def test_raising_the_rate_does_not_reopen_months_already_closed(client, db_session):
    worker = await make_worker_with_salary_plan(db_session)
    worker.pay_scheme = "monthly"
    await db_session.flush()
    await add_money_payout(db_session, worker, SALARY)
    assert (await occurrence(client))["is_paid"] is True

    from backend.planned_expenses_service import sync_worker_salary_plan, resync_worker_salary_settlements

    worker.monthly_rate = Decimal("120000.00")
    await sync_worker_salary_plan(db_session, worker, today=date(2026, 9, 23))
    await resync_worker_salary_settlements(db_session, worker.id)

    september = await occurrence(client)
    # Сентябрь заработан и выплачен по старой ставке — он остаётся закрытым.
    assert Decimal(str(september["amount"])) == SALARY
    assert september["is_paid"] is True
    items = (await client.get("/api/planned-expenses/upcoming", params={"days": 365})).json()
    october = next(item for item in items if item["due_date"] == "2026-10-05")
    assert Decimal(str(october["amount"])) == Decimal("120000.00")


async def test_resync_keeps_settlements_of_a_switched_off_plan(client, db_session):
    worker = await make_worker_with_salary_plan(db_session)
    old_plan = PlannedExpense(
        name="Old plan",
        amount=Decimal("40000.00"),
        currency="RSD",
        period="monthly",
        payment_day=5,
        start_date=date(2026, 1, 5),
        is_active=False,
        worker_id=worker.id,
    )
    db_session.add(old_plan)
    await db_session.flush()
    payout = await add_money_payout(db_session, worker, MONEY, payout_date=date(2026, 7, 5))
    payout.settled_plan_ids = json.dumps([old_plan.id])
    db_session.add(
        PlannedExpensePayment(
            planned_expense_id=old_plan.id,
            due_date=date(2026, 7, 5),
            paid_date=date(2026, 7, 5),
            amount=Decimal("40000.00"),
            worker_payout_id=payout.id,
        )
    )
    await db_session.flush()

    await sync_worker_payout_planned_payment(db_session, payout)

    kept = (
        await db_session.execute(
            select(PlannedExpensePayment).where(PlannedExpensePayment.planned_expense_id == old_plan.id)
        )
    ).scalar_one()
    assert Decimal(kept.amount) == Decimal("40000.00")
    # Выплата без периода закрывает один платёж — свой, на прежнем плане. На тот
    # же день действующего плана она второй раз не засчитывается.
    active_total = sum(
        Decimal(mark.amount)
        for mark in (
            await db_session.execute(
                select(PlannedExpensePayment).where(PlannedExpensePayment.planned_expense_id != old_plan.id)
            )
        ).scalars()
    )
    assert active_total == Decimal("0")


async def test_a_closed_month_is_not_rolled_into_the_next_one(client, db_session):
    """Сентябрь закрыт; выплата 7 сентября без периода не уходит в октябрь."""
    worker = await make_worker_with_salary_plan(db_session)
    await attach_purchase(client, worker, await make_expense(db_session, SALARY))

    balance = (await client.get(f"/api/workers/{worker.id}/salary-remaining", params={"date": "2026-09-07"})).json()
    saved = await client.post(
        "/api/workers/payouts",
        json={"worker_id": worker.id, "payout_type": "monthly", "date": "2026-09-07", "cash_paid_amount": None},
    )

    # Ближайший платёж — 5 сентября, он закрыт: не 100 000 «за октябрь», а отказ.
    assert balance["due_dates"] == ["2026-09-05"]
    assert Decimal(str(balance["remaining"])) == Decimal("0")
    assert saved.status_code == 400


async def test_the_form_names_the_payday_a_late_september_payout_counts_for(client, db_session):
    """23 сентября ближе к 5 октября: форма должна это показать, а не молчать."""
    worker = await make_worker_with_salary_plan(db_session)
    await attach_purchase(client, worker, await make_expense(db_session, SALARY))

    balance = (await client.get(f"/api/workers/{worker.id}/salary-remaining", params={"date": "2026-09-23"})).json()

    assert balance["has_plan"] is True
    assert balance["due_dates"] == ["2026-10-05"]
    assert Decimal(str(balance["remaining"])) == SALARY
    assert Decimal(str(balance["settled"])) == Decimal("0")


async def test_moving_a_payout_to_another_worker_takes_its_whole_amount(client, db_session):
    first = await make_worker_with_salary_plan(db_session)
    # План первого работника выключен и хранит погашение от этой выплаты.
    old_plan = (await db_session.execute(select(PlannedExpense))).scalar_one()
    second = Worker(name="Denis Čistjakov", monthly_rate=SALARY)
    db_session.add(second)
    await db_session.flush()
    db_session.add(
        PlannedExpense(
            name="Denis Čistjakov",
            amount=SALARY,
            currency="RSD",
            period="monthly",
            payment_day=DUE_DATE.day,
            start_date=date(2026, 1, 5),
            is_active=True,
            worker_id=second.id,
        )
    )
    await db_session.flush()
    expense = await make_expense(db_session, MONEY, entry_date=DUE_DATE)
    payout = (
        await client.post(
            "/api/workers/payouts/attach",
            json={"expense_id": expense.id, "worker_id": first.id, "payout_type": "monthly"},
        )
    ).json()["payout"]
    old_plan.is_active = False
    await db_session.flush()

    moved = await client.patch(
        f"/api/workers/payouts/{payout['id']}/link",
        json={"worker_id": second.id, "payout_type": "monthly"},
    )

    assert moved.status_code == 200
    marks = (
        (
            await db_session.execute(
                select(PlannedExpensePayment).where(PlannedExpensePayment.worker_payout_id == payout["id"])
            )
        )
        .scalars()
        .all()
    )
    # Всё засчитано второму работнику, у первого не осталось ничего.
    assert [mark.planned_expense_id for mark in marks] != [old_plan.id]
    assert sum((Decimal(mark.amount) for mark in marks), Decimal("0")) == MONEY
    assert all(mark.planned_expense_id != old_plan.id for mark in marks)


async def test_a_reversed_payout_leaves_no_settlement_on_a_switched_off_plan(client, db_session):
    worker = await make_worker_with_salary_plan(db_session)
    plan = (await db_session.execute(select(PlannedExpense))).scalar_one()
    expense = await make_expense(db_session, MONEY, entry_date=DUE_DATE)
    await client.post(
        "/api/workers/payouts/attach",
        json={"expense_id": expense.id, "worker_id": worker.id, "payout_type": "monthly"},
    )
    plan.is_active = False
    await db_session.flush()

    await create_expense_reversal(db_session, expense)

    # Деньги вернулись — погашение не должно пережить сторно даже как история.
    assert (await db_session.execute(select(PlannedExpensePayment))).scalars().all() == []


async def test_bringing_a_worker_back_restores_earlier_rate_periods(client, db_session):
    from backend.planned_expenses_service import sync_worker_salary_plan

    worker = await make_worker_with_salary_plan(db_session)
    worker.pay_scheme = "monthly"
    await db_session.flush()
    await add_money_payout(db_session, worker, SALARY)
    worker.monthly_rate = Decimal("120000.00")
    await sync_worker_salary_plan(db_session, worker, today=date(2026, 9, 23))
    assert len((await db_session.execute(select(PlannedExpense))).scalars().all()) == 2

    worker.is_active = False
    await sync_worker_salary_plan(db_session, worker, today=date(2026, 9, 24))
    worker.is_active = True
    await sync_worker_salary_plan(db_session, worker, today=date(2026, 9, 25))

    plans = (await db_session.execute(select(PlannedExpense).order_by(PlannedExpense.id))).scalars().all()
    # Обе части — прошлая со старой ставкой и текущая — снова в расчёте.
    assert [plan.is_active for plan in plans] == [True, True]
    september = await occurrence(client)
    assert Decimal(str(september["amount"])) == SALARY
    assert september["is_paid"] is True


async def history_mark_on_switched_off_plan(db, worker, *, amount):
    """Выплата, погашение которой лежит на выключенном плане работника."""
    old_plan = PlannedExpense(
        name="Old plan",
        amount=Decimal("40000.00"),
        currency="RSD",
        period="monthly",
        payment_day=5,
        start_date=date(2026, 1, 5),
        is_active=False,
        worker_id=worker.id,
    )
    db.add(old_plan)
    await db.flush()
    expense = await make_expense(db, amount, entry_date=date(2026, 7, 5))
    payout = WorkerPayout(
        worker_id=worker.id,
        expense_id=expense.id,
        payout_type="monthly",
        date=date(2026, 7, 5),
        gross_amount=Decimal(amount),
        cash_paid_amount=Decimal(amount),
        remaining_amount=Decimal("0"),
        description="Andrei Timokhov",
        origin="expense_link",
        settled_plan_ids=json.dumps([old_plan.id]),
    )
    db.add(payout)
    await db.flush()
    db.add(
        PlannedExpensePayment(
            planned_expense_id=old_plan.id,
            due_date=date(2026, 7, 5),
            paid_date=date(2026, 7, 5),
            amount=Decimal(amount),
            worker_payout_id=payout.id,
        )
    )
    await db.flush()
    return old_plan, expense, payout


async def test_reducing_a_payout_trims_its_settlement_on_a_switched_off_plan(client, db_session):
    from backend.expense_service import sync_worker_payout_from_expense

    worker = await make_worker_with_salary_plan(db_session)
    old_plan, expense, payout = await history_mark_on_switched_off_plan(db_session, worker, amount="40000.00")

    # Выплату исправили: на самом деле выдали 20 000.
    expense.amount = Decimal("20000.00")
    await sync_worker_payout_from_expense(db_session, expense)
    await db_session.flush()

    marks = (
        (
            await db_session.execute(
                select(PlannedExpensePayment).where(PlannedExpensePayment.worker_payout_id == payout.id)
            )
        )
        .scalars()
        .all()
    )
    assert Decimal(payout.cash_paid_amount) == Decimal("20000.00")
    # Погашение не может остаться больше выданного.
    assert sum((Decimal(mark.amount) for mark in marks), Decimal("0")) == Decimal("20000.00")
    assert all(mark.planned_expense_id == old_plan.id for mark in marks)


async def test_turning_a_payout_into_a_trip_clears_its_settlement_history(client, db_session):
    worker = await make_worker_with_salary_plan(db_session)
    _, _, payout = await history_mark_on_switched_off_plan(db_session, worker, amount="40000.00")

    changed = await client.patch(
        f"/api/workers/payouts/{payout.id}/link",
        json={
            "worker_id": worker.id,
            "payout_type": "trip_final",
            "period_start": "2026-07-01",
            "period_end": "2026-07-03",
        },
    )

    assert changed.status_code == 200
    # Командировочные зарплату не закрывают — и в истории тоже.
    assert (
        await db_session.execute(
            select(PlannedExpensePayment).where(PlannedExpensePayment.worker_payout_id == payout.id)
        )
    ).scalars().all() == []


async def test_settlement_history_follows_a_corrected_payout_date(client, db_session):
    from backend.expense_service import sync_worker_payout_from_expense

    worker = await make_worker_with_salary_plan(db_session)
    old_plan, expense, payout = await history_mark_on_switched_off_plan(db_session, worker, amount="40000.00")

    # Дату выплаты исправили: не 5 июля, а 5 августа.
    expense.date = date(2026, 8, 5)
    expense.paid_date = date(2026, 8, 5)
    await sync_worker_payout_from_expense(db_session, expense)
    await db_session.flush()

    marks = (
        (
            await db_session.execute(
                select(PlannedExpensePayment).where(PlannedExpensePayment.worker_payout_id == payout.id)
            )
        )
        .scalars()
        .all()
    )
    assert [(mark.planned_expense_id, mark.due_date) for mark in marks] == [(old_plan.id, date(2026, 8, 5))]


async def test_restoring_a_payout_amount_restores_its_settlement(client, db_session):
    from backend.expense_service import sync_worker_payout_from_expense

    worker = await make_worker_with_salary_plan(db_session)
    old_plan, expense, payout = await history_mark_on_switched_off_plan(db_session, worker, amount="40000.00")

    expense.amount = Decimal("20000.00")
    await sync_worker_payout_from_expense(db_session, expense)
    expense.amount = Decimal("40000.00")
    await sync_worker_payout_from_expense(db_session, expense)
    await db_session.flush()

    marks = (
        (
            await db_session.execute(
                select(PlannedExpensePayment).where(PlannedExpensePayment.worker_payout_id == payout.id)
            )
        )
        .scalars()
        .all()
    )
    # Урезанная часть не потерялась и вернулась туда же, на свой план.
    assert [(mark.planned_expense_id, Decimal(mark.amount)) for mark in marks] == [(old_plan.id, Decimal("40000.00"))]


@pytest.mark.parametrize(
    "draft",
    [
        # Зарплата после покупки на 20 000 — к выдаче 80 000.
        {"payout_type": "monthly", "date": "2026-09-05"},
        # Тип переключили на аванс за командировку — считается по своей формуле.
        {
            "payout_type": "trip_advance",
            "date": "2026-09-14",
            "period_start": "2026-09-14",
            "period_end": "2026-09-16",
            "trip_days": 3,
        },
        # Сумму назвали явно — она и сохраняется.
        {"payout_type": "monthly", "date": "2026-09-05", "cash_paid_amount": 30000},
    ],
)
async def test_the_preview_shows_exactly_what_saving_will_store(client, db_session, draft):
    worker = await make_worker_with_salary_plan(db_session)
    worker.trip_advance_day_rate = Decimal("3000.00")
    worker.lodging_night_rate = Decimal("1500.00")
    await db_session.flush()
    await attach_purchase(client, worker, await make_expense(db_session, PURCHASE))
    body = {"worker_id": worker.id, "cash_paid_amount": None, **draft}

    preview = (await client.post("/api/workers/payouts/preview", json=body)).json()
    saved = await client.post("/api/workers/payouts", json=body)

    assert saved.status_code == 200, saved.text
    stored = saved.json()["payout"]
    for field in ("gross_amount", "cash_paid_amount", "remaining_amount"):
        assert Decimal(str(preview[field])) == Decimal(str(stored[field])), field


async def test_the_preview_of_a_monthly_payout_after_a_purchase(client, db_session):
    worker = await make_worker_with_salary_plan(db_session)
    await attach_purchase(client, worker, await make_expense(db_session, PURCHASE))

    preview = (
        await client.post(
            "/api/workers/payouts/preview",
            json={"worker_id": worker.id, "payout_type": "monthly", "date": "2026-09-05", "cash_paid_amount": None},
        )
    ).json()

    assert Decimal(str(preview["cash_paid_amount"])) == MONEY
    assert preview["fully_settled"] is False
    assert preview["salary"]["due_dates"] == ["2026-09-05"]
    assert Decimal(str(preview["salary"]["settled"])) == PURCHASE


async def test_the_preview_says_when_nothing_is_left_to_pay(client, db_session):
    worker = await make_worker_with_salary_plan(db_session)
    await attach_purchase(client, worker, await make_expense(db_session, SALARY))

    closed = (
        await client.post(
            "/api/workers/payouts/preview",
            json={"worker_id": worker.id, "payout_type": "monthly", "date": "2026-09-07", "cash_paid_amount": None},
        )
    ).json()
    purchase_without_amount = (
        await client.post(
            "/api/workers/payouts/preview",
            json={
                "worker_id": worker.id,
                "payout_type": "purchase",
                "date": "2026-09-07",
                "period_start": "2026-09-01",
                "period_end": "2026-09-30",
                "cash_paid_amount": None,
            },
        )
    ).json()

    assert closed["fully_settled"] is True
    assert Decimal(str(closed["cash_paid_amount"])) == Decimal("0")
    # Покупку без суммы форма сохранить не даст: выдавать нечего.
    assert Decimal(str(purchase_without_amount["cash_paid_amount"])) == Decimal("0")


async def two_plans_on_the_same_payday(db):
    """Выключенный план №1, которому уже принадлежит выплата, и действующий №2."""
    worker = await make_worker_with_salary_plan(db)
    first_plan = (await db.execute(select(PlannedExpense))).scalar_one()
    expense = await make_expense(db, MONEY, entry_date=DUE_DATE)
    await db.flush()
    return worker, first_plan, expense


async def marks_of(db, payout_id):
    return [
        (mark.planned_expense_id, mark.due_date)
        for mark in (
            await db.execute(select(PlannedExpensePayment).where(PlannedExpensePayment.worker_payout_id == payout_id))
        ).scalars()
    ]


async def test_cancelling_a_reversal_returns_the_payout_to_its_switched_off_plan(client, db_session):
    from backend.expense_service import restore_worker_payout_for_expense

    worker, first_plan, expense = await two_plans_on_the_same_payday(db_session)
    payout = (
        await client.post(
            "/api/workers/payouts/attach",
            json={"expense_id": expense.id, "worker_id": worker.id, "payout_type": "monthly"},
        )
    ).json()["payout"]
    # План №1 выключили и завели действующий №2 с тем же днём выплаты.
    first_plan.is_active = False
    second_plan = PlannedExpense(
        name="Andrei Timokhov",
        amount=SALARY,
        currency="RSD",
        period="monthly",
        payment_day=DUE_DATE.day,
        start_date=date(2026, 1, 5),
        is_active=True,
        worker_id=worker.id,
    )
    db_session.add(second_plan)
    await db_session.flush()
    assert await marks_of(db_session, payout["id"]) == [(first_plan.id, DUE_DATE)]

    await create_expense_reversal(db_session, expense)
    assert await marks_of(db_session, payout["id"]) == []
    expense.reversed_expense_id = None
    await restore_worker_payout_for_expense(db_session, expense.id)

    # Выплата вернулась на свой план, а не ушла на действующий №2.
    assert await marks_of(db_session, payout["id"]) == [(first_plan.id, DUE_DATE)]


async def test_a_round_trip_through_a_trip_type_keeps_the_payout_on_its_plan(client, db_session):
    worker, first_plan, expense = await two_plans_on_the_same_payday(db_session)
    payout = (
        await client.post(
            "/api/workers/payouts/attach",
            json={"expense_id": expense.id, "worker_id": worker.id, "payout_type": "monthly"},
        )
    ).json()["payout"]
    first_plan.is_active = False
    db_session.add(
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
    await db_session.flush()

    for payout_type, period in (("trip_final", ("2026-09-01", "2026-09-03")), ("monthly", (None, None))):
        changed = await client.patch(
            f"/api/workers/payouts/{payout['id']}/link",
            json={
                "worker_id": worker.id,
                "payout_type": payout_type,
                "period_start": period[0],
                "period_end": period[1],
            },
        )
        assert changed.status_code == 200, changed.text

    assert await marks_of(db_session, payout["id"]) == [(first_plan.id, DUE_DATE)]


async def test_a_deleted_plan_id_reused_by_a_new_plan_does_not_inherit_the_payout(client, db_session):
    worker, first_plan, expense = await two_plans_on_the_same_payday(db_session)
    payout = (
        await client.post(
            "/api/workers/payouts/attach",
            json={"expense_id": expense.id, "worker_id": worker.id, "payout_type": "monthly"},
        )
    ).json()["payout"]
    stored = (await db_session.execute(select(WorkerPayout).where(WorkerPayout.id == payout["id"]))).scalar_one()
    assert first_plan.id in json.loads(stored.settled_plan_ids)
    deleted_id = first_plan.id

    removed = await client.delete(f"/api/planned-expenses/{deleted_id}")
    assert removed.status_code == 200
    # SQLite выдаёт ID удалённого последним плана новому — повторяем это явно.
    reused = PlannedExpense(
        id=deleted_id,
        name="Someone else's plan",
        amount=Decimal("5000.00"),
        currency="RSD",
        period="monthly",
        payment_day=DUE_DATE.day,
        start_date=date(2026, 1, 5),
        is_active=False,
        worker_id=worker.id,
    )
    db_session.add(reused)
    await db_session.flush()
    await sync_worker_payout_planned_payment(db_session, stored)

    # Связь с удалённым планом забыта: новый план под тем же ID ей не наследник.
    assert json.loads(stored.settled_plan_ids) == []
    assert await marks_of(db_session, payout["id"]) == []


async def test_the_plan_of_an_old_payout_can_be_set_by_hand(client, db_session):
    worker, first_plan, expense = await two_plans_on_the_same_payday(db_session)
    payout = (
        await client.post(
            "/api/workers/payouts/attach",
            json={"expense_id": expense.id, "worker_id": worker.id, "payout_type": "monthly"},
        )
    ).json()["payout"]
    first_plan.is_active = False
    second_plan = PlannedExpense(
        name="Andrei Timokhov",
        amount=SALARY,
        currency="RSD",
        period="monthly",
        payment_day=DUE_DATE.day,
        start_date=date(2026, 1, 5),
        is_active=True,
        worker_id=worker.id,
    )
    db_session.add(second_plan)
    await db_session.flush()
    stored = (await db_session.execute(select(WorkerPayout).where(WorkerPayout.id == payout["id"]))).scalar_one()
    # Как у старой выплаты: ни отметки, ни списка планов — связь потеряна.
    stored.settled_plan_ids = None
    await db_session.execute(
        delete(PlannedExpensePayment).where(PlannedExpensePayment.worker_payout_id == payout["id"])
    )
    await sync_worker_payout_planned_payment(db_session, stored)
    assert await marks_of(db_session, payout["id"]) == [(second_plan.id, DUE_DATE)]

    fixed = await client.put(f"/api/workers/payouts/{payout['id']}/settled-plans", json={"plan_ids": [first_plan.id]})

    assert fixed.status_code == 200
    assert fixed.json()["settled_plan_ids"] == [first_plan.id]
    assert await marks_of(db_session, payout["id"]) == [(first_plan.id, DUE_DATE)]


async def test_a_plan_of_another_worker_cannot_be_set_by_hand(client, db_session):
    worker, _, expense = await two_plans_on_the_same_payday(db_session)
    other = Worker(name="Other")
    db_session.add(other)
    await db_session.flush()
    foreign = PlannedExpense(
        name="Other",
        amount=SALARY,
        currency="RSD",
        period="monthly",
        payment_day=5,
        start_date=date(2026, 1, 5),
        is_active=True,
        worker_id=other.id,
    )
    db_session.add(foreign)
    await db_session.flush()
    payout = (
        await client.post(
            "/api/workers/payouts/attach",
            json={"expense_id": expense.id, "worker_id": worker.id, "payout_type": "monthly"},
        )
    ).json()["payout"]

    refused = await client.put(f"/api/workers/payouts/{payout['id']}/settled-plans", json={"plan_ids": [foreign.id]})

    assert refused.status_code == 400


async def payout_marked_on_plan_five(client, db_session):
    """Выплата уже отмечена на выключенном плане, рядом ещё два плана на тот же день."""
    worker = await make_worker_with_salary_plan(db_session)
    plan_one = (await db_session.execute(select(PlannedExpense))).scalar_one()

    def same_day_plan(active):
        return PlannedExpense(
            name="Andrei Timokhov",
            amount=SALARY,
            currency="RSD",
            period="monthly",
            payment_day=DUE_DATE.day,
            start_date=date(2026, 1, 5),
            is_active=active,
            worker_id=worker.id,
        )

    plan_five, plan_six = same_day_plan(False), same_day_plan(False)
    db_session.add_all([plan_five, plan_six])
    await db_session.flush()
    _, _, payout = await history_mark_on_switched_off_plan(db_session, worker, amount="40000.00")
    # Переносим историю выплаты на «план №5» с днём платежа на её дату.
    await db_session.execute(delete(PlannedExpensePayment).where(PlannedExpensePayment.worker_payout_id == payout.id))
    payout.date = DUE_DATE
    payout.settled_plan_ids = json.dumps([plan_five.id])
    await sync_worker_payout_planned_payment(db_session, payout)
    assert await marks_of(db_session, payout.id) == [(plan_five.id, DUE_DATE)]
    return worker, payout, plan_one, plan_five, plan_six


async def test_setting_plans_by_hand_overrides_an_existing_mark(client, db_session):
    _, payout, _, plan_five, plan_six = await payout_marked_on_plan_five(client, db_session)

    moved = await client.put(f"/api/workers/payouts/{payout.id}/settled-plans", json={"plan_ids": [plan_six.id]})

    assert moved.status_code == 200
    # Старая отметка на №5 не возвращает его в список: решение человека главнее.
    assert moved.json()["settled_plan_ids"] == [plan_six.id]
    assert await marks_of(db_session, payout.id) == [(plan_six.id, DUE_DATE)]


async def test_an_empty_list_by_hand_removes_the_switched_off_plan(client, db_session):
    _, payout, plan_one, plan_five, _ = await payout_marked_on_plan_five(client, db_session)

    cleared = await client.put(f"/api/workers/payouts/{payout.id}/settled-plans", json={"plan_ids": []})

    assert cleared.status_code == 200
    # Связь с выключенным планом снята — выплата ложится на действующий, и в
    # списке теперь он, а не №5.
    assert cleared.json()["settled_plan_ids"] == [plan_one.id]
    assert await marks_of(db_session, payout.id) == [(plan_one.id, DUE_DATE)]


async def test_old_payouts_without_a_confirmed_plan_wait_for_review(client, db_session):
    worker = await make_worker_with_salary_plan(db_session)
    plan = (await db_session.execute(select(PlannedExpense))).scalar_one()
    plan.is_active = False
    await db_session.flush()

    def legacy(payout_type, cancelled):
        return WorkerPayout(
            worker_id=worker.id,
            payout_type=payout_type,
            date=DUE_DATE,
            gross_amount=MONEY,
            cash_paid_amount=MONEY,
            remaining_amount=Decimal("0"),
            description="legacy",
            cancelled_at=date(2026, 9, 10) if cancelled else None,
        )

    reversed_salary, former_salary_now_trip = legacy("monthly", True), legacy("trip_final", False)
    fresh_trip = WorkerPayout(
        worker_id=worker.id,
        payout_type="trip_final",
        date=DUE_DATE,
        gross_amount=MONEY,
        cash_paid_amount=MONEY,
        remaining_amount=Decimal("0"),
        description="new",
    )
    db_session.add_all([reversed_salary, former_salary_now_trip, fresh_trip])
    await db_session.flush()
    # NULL бывает только у строк, что были до миграции: так их и получаем.
    await db_session.execute(
        update(WorkerPayout)
        .where(WorkerPayout.id.in_([reversed_salary.id, former_salary_now_trip.id]))
        .values(settled_plan_ids=None)
    )
    await db_session.flush()

    review = (await client.get("/api/workers/payouts/plan-review")).json()

    # Ни сторнированную, ни ставшую командировочной не угадываем — обе на проверку.
    assert [item["payout_id"] for item in review] == [reversed_salary.id, former_salary_now_trip.id]
    assert review[0]["candidate_plan_ids"] == [plan.id]
    # Новая выплата создаётся с «[]» и на проверку не попадает.
    assert fresh_trip.settled_plan_ids == "[]"

    await client.put(f"/api/workers/payouts/{reversed_salary.id}/settled-plans", json={"plan_ids": [plan.id]})
    await client.put(f"/api/workers/payouts/{former_salary_now_trip.id}/settled-plans", json={"plan_ids": []})

    assert (await client.get("/api/workers/payouts/plan-review")).json() == []
