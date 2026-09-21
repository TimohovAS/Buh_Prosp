from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.auth import get_current_user_required
from backend.database import get_db
from backend.models import Worker, WorkerPayout
from backend.routers.workers_router import router


@pytest.fixture
async def report_client(db_session):
    app = FastAPI()
    app.include_router(router, prefix="/api")

    async def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user_required] = lambda: SimpleNamespace(id=1, role="observer")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def add_payout(db, worker, amount, payout_date, payout_type="regular", **kwargs):
    payout = WorkerPayout(
        worker_id=worker.id,
        date=payout_date,
        payout_type=payout_type,
        cash_paid_amount=Decimal(amount),
        gross_amount=kwargs.pop("gross_amount", Decimal(amount)),
        description="Worker payout",
        **kwargs,
    )
    db.add(payout)
    await db.flush()
    return payout


async def test_report_counts_actual_cash_once_and_keeps_archived_workers(report_client, db_session):
    worker = Worker(name="Same name")
    archived = Worker(name="Same name", is_active=False)
    db_session.add_all([worker, archived, Worker(name="No payouts")])
    await db_session.flush()
    await add_payout(db_session, worker, "100.11", date(2026, 8, 1), "monthly")
    await add_payout(db_session, worker, "200.22", date(2026, 8, 2), "weekly")
    trip_period = {"period_start": date(2026, 8, 3), "period_end": date(2026, 8, 7)}
    await add_payout(
        db_session,
        worker,
        "3000.33",
        date(2026, 8, 3),
        "trip_advance",
        gross_amount=Decimal("10000.77"),
        remaining_amount=Decimal("7000.44"),
        **trip_period,
    )
    final = await add_payout(
        db_session,
        worker,
        "7000.44",
        date(2026, 8, 7),
        "trip_final",
        gross_amount=Decimal("10000.77"),
        advance_paid=Decimal("3000.33"),
        **trip_period,
    )
    last = await add_payout(db_session, archived, "50.55", date(2026, 8, 7))

    response = await report_client.get("/api/workers/payouts/report", params={"limit": 1})
    assert response.status_code == 200
    report = response.json()
    assert report["total_paid"] == 10351.65
    assert report["average_payout"] == 2070.33
    assert report["payout_count"] == 5
    assert report["worker_count"] == 2
    assert [item["id"] for item in report["items"]] == [last.id]
    assert report["workers"][0] == {
        "worker_id": worker.id,
        "worker_name": "Same name",
        "is_active": True,
        "total_paid": 10301.10,
        "money_paid": 10301.10,
        "purchase_paid": 0,
        "regular_paid": 300.33,
        "trip_paid": 10000.77,
        "lodging_paid": 0,
        "payout_count": 4,
        "last_payout_date": "2026-08-07",
    }
    assert report["workers"][1]["is_active"] is False
    next_page = (await report_client.get("/api/workers/payouts/report", params={"limit": 1, "offset": 1})).json()
    assert next_page["total_paid"] == report["total_paid"]
    assert next_page["workers"] == report["workers"]
    assert next_page["months"] == report["months"]
    assert next_page["items"][0]["id"] == final.id


async def test_report_filters_by_payment_date_inclusively_and_worker(report_client, db_session):
    worker = Worker(name="Worker")
    other = Worker(name="Other")
    db_session.add_all([worker, other])
    await db_session.flush()
    await add_payout(db_session, worker, "999", date(2026, 7, 31))
    first = await add_payout(db_session, worker, "10.01", date(2026, 8, 1), period_start=date(2026, 7, 1))
    last = await add_payout(db_session, worker, "20.02", date(2026, 8, 31), period_end=date(2026, 9, 30))
    await add_payout(db_session, worker, "999", date(2026, 9, 1))
    await add_payout(db_session, other, "999", date(2026, 8, 15))
    params = {"worker_id": worker.id, "date_from": "2026-08-01", "date_to": "2026-08-31"}
    report = (await report_client.get("/api/workers/payouts/report", params=params)).json()
    assert report["total_paid"] == 30.03
    assert report["average_payout"] == 15.02
    assert report["months"] == [
        {
            "month": "2026-08",
            "total_paid": 30.03,
            "money_paid": 30.03,
            "purchase_paid": 0,
            "regular_paid": 30.03,
            "trip_paid": 0,
            "lodging_paid": 0,
            "payout_count": 2,
        }
    ]
    assert report["payout_count"] == 2
    assert report["worker_count"] == 1
    assert [item["id"] for item in report["items"]] == [last.id, first.id]

    for params, expected in [
        ({"date_from": "2026-09-01"}, 999),
        ({"date_to": "2026-07-31"}, 999),
        ({"worker_id": other.id}, 999),
    ]:
        report = (await report_client.get("/api/workers/payouts/report", params=params)).json()
        assert report["total_paid"] == expected


async def test_report_totals_are_not_limited_to_history_page(report_client, db_session):
    worker = Worker(name="Worker")
    db_session.add(worker)
    await db_session.flush()
    db_session.add_all(
        [
            WorkerPayout(
                worker_id=worker.id,
                date=date(2026, 8, 1),
                payout_type="regular",
                cash_paid_amount=Decimal("1.01"),
                gross_amount=Decimal("1.01"),
                description="Payout",
            )
            for _ in range(501)
        ]
    )
    await db_session.flush()
    report = (await report_client.get("/api/workers/payouts/report", params={"offset": 500})).json()
    assert report["total_paid"] == 506.01
    assert report["months"][0]["total_paid"] == 506.01
    assert report["payout_count"] == 501
    assert len(report["items"]) == 1


async def test_empty_report_and_pagination_validation(report_client):
    response = await report_client.get("/api/workers/payouts/report")
    assert response.status_code == 200
    assert response.json() == {
        "total_paid": 0,
        "average_payout": 0,
        "payout_count": 0,
        "worker_count": 0,
        "workers": [],
        "months": [],
        "items": [],
    }
    for params in ({"limit": 0}, {"limit": 501}, {"offset": -1}, {"date_from": "invalid"}):
        assert (await report_client.get("/api/workers/payouts/report", params=params)).status_code == 422
    assert (
        await report_client.get(
            "/api/workers/payouts/report", params={"date_from": "2026-09-01", "date_to": "2026-08-01"}
        )
    ).status_code == 400


async def test_monthly_worker_statistics_separate_years_and_trip_cash(report_client, db_session):
    worker = Worker(name="Worker")
    other = Worker(name="Other")
    db_session.add_all([worker, other])
    await db_session.flush()
    await add_payout(db_session, worker, "100.01", date(2025, 8, 1))
    await add_payout(db_session, worker, "200.02", date(2026, 8, 1), "monthly")
    await add_payout(db_session, worker, "300.03", date(2026, 8, 31), "trip_advance", gross_amount=Decimal("1000.10"))
    await add_payout(
        db_session,
        worker,
        "700.07",
        date(2026, 9, 1),
        "trip_final",
        advance_paid=Decimal("300.03"),
        gross_amount=Decimal("1000.10"),
    )
    await add_payout(db_session, other, "9999", date(2026, 8, 1))
    report = (
        await report_client.get("/api/workers/payouts/report", params={"worker_id": worker.id, "limit": 1})
    ).json()
    assert report["months"] == [
        {
            "month": "2026-09",
            "total_paid": 700.07,
            "money_paid": 700.07,
            "purchase_paid": 0,
            "regular_paid": 0,
            "trip_paid": 700.07,
            "lodging_paid": 0,
            "payout_count": 1,
        },
        {
            "month": "2026-08",
            "total_paid": 500.05,
            "money_paid": 500.05,
            "purchase_paid": 0,
            "regular_paid": 200.02,
            "trip_paid": 300.03,
            "lodging_paid": 0,
            "payout_count": 2,
        },
        {
            "month": "2025-08",
            "total_paid": 100.01,
            "money_paid": 100.01,
            "purchase_paid": 0,
            "regular_paid": 100.01,
            "trip_paid": 0,
            "lodging_paid": 0,
            "payout_count": 1,
        },
    ]
    assert report["total_paid"] == 1300.13


async def test_lodging_is_excluded_from_trip_payouts_once_per_trip(report_client, db_session):
    """Жильё платят гостинице, а не работнику, и деньги на него выдаются один раз.

    lodging_amount дублируется на авансе и на окончательном расчёте одной поездки,
    поэтому вычитать его нужно только там, где оно реально ушло из кассы.
    """
    worker = Worker(name="Traveller")
    db_session.add(worker)
    await db_session.flush()
    # Поездка с авансом: жильё выдано вместе с авансом, в расчёте его уже нет.
    await add_payout(
        db_session,
        worker,
        "8000",
        date(2026, 8, 3),
        "trip_advance",
        gross_amount=Decimal("20000"),
        lodging_amount=Decimal("3000"),
    )
    await add_payout(
        db_session,
        worker,
        "12000",
        date(2026, 8, 7),
        "trip_final",
        gross_amount=Decimal("20000"),
        advance_paid=Decimal("8000"),
        lodging_amount=Decimal("3000"),
    )
    # Поездка без аванса: жильё ушло в окончательном расчёте.
    await add_payout(
        db_session,
        worker,
        "9000",
        date(2026, 8, 10),
        "trip_final",
        gross_amount=Decimal("9000"),
        lodging_amount=Decimal("2000"),
    )
    # Выдачу поправили вручную: вычитаем не больше, чем выдали.
    await add_payout(
        db_session,
        worker,
        "500",
        date(2026, 8, 12),
        "trip_advance",
        gross_amount=Decimal("5000"),
        lodging_amount=Decimal("900"),
    )

    report = (
        await report_client.get("/api/workers/payouts/report", params={"worker_id": worker.id, "limit": 1})
    ).json()
    summary = report["workers"][0]
    assert summary["total_paid"] == 29500
    assert summary["trip_paid"] == 24000
    assert summary["lodging_paid"] == 5500
    assert summary["regular_paid"] == 0
    # Составляющие всегда дают выданную из кассы сумму.
    assert summary["regular_paid"] + summary["trip_paid"] + summary["lodging_paid"] == summary["total_paid"]
    assert report["months"] == [
        {
            "month": "2026-08",
            "total_paid": 29500,
            "money_paid": 24000,
            "purchase_paid": 0,
            "regular_paid": 0,
            "trip_paid": 24000,
            "lodging_paid": 5500,
            "payout_count": 4,
        }
    ]


async def test_report_requires_authentication():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/workers/payouts/report")).status_code == 401


async def test_report_splits_money_purchases_and_trips(report_client, db_session):
    worker = Worker(name="Andrei Timokhov")
    db_session.add(worker)
    await db_session.flush()
    await add_payout(db_session, worker, "80000", date(2026, 9, 5), "monthly")
    await add_payout(db_session, worker, "20000", date(2026, 9, 18), "purchase")
    await add_payout(
        db_session,
        worker,
        "33500",
        date(2026, 9, 20),
        "trip_advance",
        gross_amount=Decimal("33500"),
        lodging_amount=Decimal("6000"),
        period_start=date(2026, 9, 20),
        period_end=date(2026, 9, 24),
    )

    report = (await report_client.get("/api/workers/payouts/report")).json()
    row = report["workers"][0]
    month = report["months"][0]

    assert row["money_paid"] == 107500
    assert row["purchase_paid"] == 20000
    assert row["regular_paid"] == 80000
    assert row["trip_paid"] == 27500
    assert row["lodging_paid"] == 6000
    assert row["total_paid"] == 133500
    # Полученное работником — без стоимости жилья, и складывается двумя способами.
    received = row["money_paid"] + row["purchase_paid"]
    assert received == 127500
    assert received == row["regular_paid"] + row["purchase_paid"] + row["trip_paid"]
    assert received + row["lodging_paid"] == row["total_paid"]
    assert {key: month[key] for key in ("money_paid", "purchase_paid", "regular_paid", "trip_paid")} == {
        "money_paid": 107500,
        "purchase_paid": 20000,
        "regular_paid": 80000,
        "trip_paid": 27500,
    }
