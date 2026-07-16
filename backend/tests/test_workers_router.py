from datetime import date
from decimal import Decimal

from backend.models import Worker
from backend.routers.workers_router import _calculate_payout
from backend.schemas import WorkerPayoutCreate


def _trip_payout_data() -> WorkerPayoutCreate:
    return WorkerPayoutCreate(
        worker_id=1,
        payout_type="trip_final",
        date=date(2026, 7, 13),
        period_start=date(2026, 7, 13),
        period_end=date(2026, 7, 17),
        lodging_night_rate=Decimal("1500"),
    )


def test_permanent_worker_regular_day_rate_is_not_added_to_trip() -> None:
    worker = Worker(
        worker_type="permanent",
        regular_day_rate=Decimal("6000"),
        trip_work_day_rate=Decimal("0"),
        trip_per_diem_rate=Decimal("2500"),
        trip_food_rate=Decimal("3000"),
    )

    result = _calculate_payout(worker, _trip_payout_data())

    assert result["trip_work_day_rate"] == Decimal("0")
    assert result["gross_amount"] == Decimal("33500")


def test_temporary_worker_zero_trip_rate_is_also_calculated_as_zero() -> None:
    worker = Worker(
        worker_type="temporary",
        regular_day_rate=Decimal("6000"),
        trip_work_day_rate=Decimal("0"),
        trip_per_diem_rate=Decimal("2500"),
        trip_food_rate=Decimal("3000"),
    )

    result = _calculate_payout(worker, _trip_payout_data())

    assert result["trip_work_day_rate"] == Decimal("0")
    assert result["gross_amount"] == Decimal("33500")
