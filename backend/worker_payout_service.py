from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import case, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from backend.decimal_utils import ZERO_DECIMAL, to_decimal
from backend.models import WorkerPayout


@dataclass(frozen=True)
class OpenTripSettlementSummary:
    total: Decimal
    due_total: Decimal
    count: int


async def get_open_trip_settlement_summary(
    db: AsyncSession,
    *,
    due_by: date,
) -> OpenTripSettlementSummary:
    """Return unpaid trip advances that do not yet have a matching final settlement."""
    final_payout = aliased(WorkerPayout)
    matching_final_exists = exists(
        select(final_payout.id).where(
            final_payout.worker_id == WorkerPayout.worker_id,
            final_payout.payout_type == "trip_final",
            final_payout.period_start.is_not_distinct_from(WorkerPayout.period_start),
            final_payout.period_end.is_not_distinct_from(WorkerPayout.period_end),
        )
    )
    due_date = func.coalesce(WorkerPayout.period_end, WorkerPayout.date)
    result = await db.execute(
        select(
            func.coalesce(func.sum(WorkerPayout.remaining_amount), 0),
            func.coalesce(
                func.sum(
                    case(
                        (due_date <= due_by, WorkerPayout.remaining_amount),
                        else_=ZERO_DECIMAL,
                    )
                ),
                0,
            ),
            func.count(WorkerPayout.id),
        ).where(
            WorkerPayout.payout_type == "trip_advance",
            WorkerPayout.remaining_amount > ZERO_DECIMAL,
            ~matching_final_exists,
        )
    )
    total, due_total, count = result.one()
    return OpenTripSettlementSummary(
        total=to_decimal(total or ZERO_DECIMAL),
        due_total=to_decimal(due_total or ZERO_DECIMAL),
        count=int(count or 0),
    )
