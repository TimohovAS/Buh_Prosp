from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from backend.decimal_utils import ZERO_DECIMAL, to_decimal
from backend.models import Worker, WorkerPayout


@dataclass(frozen=True)
class OpenTripSettlementItem:
    payout_id: int
    worker_name: str
    remaining_amount: Decimal
    period_start: date | None
    period_end: date


@dataclass(frozen=True)
class OpenTripSettlementSummary:
    total: Decimal
    due_total: Decimal
    count: int
    items: tuple[OpenTripSettlementItem, ...]


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
            WorkerPayout.id,
            Worker.name,
            WorkerPayout.remaining_amount,
            WorkerPayout.period_start,
            due_date.label("period_end"),
        )
        .outerjoin(Worker, Worker.id == WorkerPayout.worker_id)
        .where(
            WorkerPayout.payout_type == "trip_advance",
            WorkerPayout.remaining_amount > ZERO_DECIMAL,
            ~matching_final_exists,
        )
        .order_by(due_date.asc(), Worker.name.asc(), WorkerPayout.id.asc())
    )
    items = tuple(
        OpenTripSettlementItem(
            payout_id=row.id,
            worker_name=row.name or "",
            remaining_amount=to_decimal(row.remaining_amount or ZERO_DECIMAL),
            period_start=row.period_start,
            period_end=row.period_end,
        )
        for row in result.all()
    )
    return OpenTripSettlementSummary(
        total=sum((item.remaining_amount for item in items), ZERO_DECIMAL),
        due_total=sum(
            (item.remaining_amount for item in items if item.period_end <= due_by),
            ZERO_DECIMAL,
        ),
        count=len(items),
        items=items,
    )
