from datetime import date
from decimal import Decimal

import pytest

from backend.models import Worker, WorkerPayout
from backend.worker_payout_service import get_open_trip_settlement_summary


async def _add_payout(
    db,
    *,
    worker_id: int,
    payout_type: str,
    period_start: date,
    period_end: date,
    remaining_amount: Decimal,
) -> WorkerPayout:
    payout = WorkerPayout(
        worker_id=worker_id,
        payout_type=payout_type,
        date=period_end,
        period_start=period_start,
        period_end=period_end,
        gross_amount=Decimal("50000"),
        cash_paid_amount=Decimal("35000"),
        remaining_amount=remaining_amount,
        description=f"{payout_type} test",
    )
    db.add(payout)
    await db.flush()
    return payout


@pytest.mark.asyncio
async def test_open_trip_settlements_exclude_closed_and_future_from_month_forecast(db_session) -> None:
    first_worker = Worker(name="First worker")
    second_worker = Worker(name="Second worker")
    db_session.add_all([first_worker, second_worker])
    await db_session.flush()

    await _add_payout(
        db_session,
        worker_id=first_worker.id,
        payout_type="trip_advance",
        period_start=date(2026, 7, 10),
        period_end=date(2026, 7, 20),
        remaining_amount=Decimal("15000"),
    )
    await _add_payout(
        db_session,
        worker_id=first_worker.id,
        payout_type="trip_advance",
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 5),
        remaining_amount=Decimal("12000"),
    )
    await _add_payout(
        db_session,
        worker_id=first_worker.id,
        payout_type="trip_final",
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 5),
        remaining_amount=Decimal("0"),
    )
    await _add_payout(
        db_session,
        worker_id=second_worker.id,
        payout_type="trip_advance",
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 5),
        remaining_amount=Decimal("20000"),
    )

    summary = await get_open_trip_settlement_summary(db_session, due_by=date(2026, 7, 31))

    assert summary.total == Decimal("35000")
    assert summary.due_total == Decimal("15000")
    assert summary.count == 2
