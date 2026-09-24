"""Сервис обязательных платежей — по ТЗ решений Пореске управе."""

import calendar
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import MonthlyObligation, PaymentType, TaxSchemePeriod, YearDecision
from backend.state_machine import initialize_obligation_status, refresh_obligation_due_status
from backend.tax_scheme_service import ensure_default_tax_scheme


def deadline_for_month(year: int, month: int, due_day: int = 15, month_offset: int = 1) -> date:
    """Calculate a configurable due date and clamp it to the target month's last day."""
    target_index = year * 12 + (month - 1) + month_offset
    target_year, target_month_index = divmod(target_index, 12)
    target_month = target_month_index + 1
    target_day = min(due_day, calendar.monthrange(target_year, target_month)[1])
    return date(target_year, target_month, target_day)


def payment_purpose_with_year(template: str, year: int) -> str:
    """Подставить год в шаблон сврха уплате (YYYY)."""
    return template.replace("YYYY", str(year))


def payment_reference_for_year(decision: YearDecision, year: int) -> str:
    """Use the next-year reference while a previous year's rule is carried forward."""
    if year == decision.year + 1 and decision.poziv_na_broj_next:
        return decision.poziv_na_broj_next
    return decision.poziv_na_broj


async def configured_obligation_years(db: AsyncSession) -> list[int]:
    """Return years that can be generated from the configured active rules."""
    result = await db.execute(
        select(YearDecision.year, YearDecision.is_provisional, YearDecision.poziv_na_broj_next).where(
            YearDecision.is_active == True
        )
    )
    years: set[int] = set()
    for rule_year, is_provisional, next_year_reference in result.all():
        years.add(rule_year)
        if is_provisional or next_year_reference:
            years.add(rule_year + 1)
    return sorted(years)


async def regenerate_configured_obligations(db: AsyncSession) -> list[int]:
    """Reconcile every year implied by active rules without seeding a clean install."""
    years = await configured_obligation_years(db)
    for year in years:
        await get_or_create_obligations(db, year)
    return years


async def get_or_create_obligations(
    db: AsyncSession, year: int, payment_type_code: str | None = None
) -> list[MonthlyObligation]:
    """Rebuild unpaid obligations from every effective scheme segment in the year."""
    today = date.today()
    await ensure_default_tax_scheme(db, initial_date=date(year, 1, 1))
    filter_payment_type_id = None
    if payment_type_code:
        filter_payment_type_id = await db.scalar(select(PaymentType.id).where(PaymentType.code == payment_type_code))

    # Always generate every payment type. A UI filter must never deactivate hidden rows.
    q = select(YearDecision).where(
        YearDecision.is_active == True,
        (
            (YearDecision.year == year)
            | (
                (YearDecision.year == (year - 1))
                & ((YearDecision.is_provisional == True) | (YearDecision.poziv_na_broj_next.is_not(None)))
            )
        ),
    )
    q = q.order_by(YearDecision.payment_type_id, YearDecision.is_provisional.asc(), YearDecision.period_start.desc())
    r = await db.execute(q)
    decisions = list(r.scalars().all())

    period_result = await db.execute(
        select(TaxSchemePeriod)
        .where(
            TaxSchemePeriod.period_start <= date(year, 12, 31),
            (TaxSchemePeriod.period_end.is_(None)) | (TaxSchemePeriod.period_end >= date(year, 1, 1)),
        )
        .order_by(TaxSchemePeriod.period_start)
    )
    scheme_periods = list(period_result.scalars().all())
    existing_result = await db.execute(select(MonthlyObligation).where(MonthlyObligation.year == year))
    existing = list(existing_result.scalars().all())

    desired_ids: set[int] = set()
    claimed_existing_ids: set[int] = set()
    generated: list[MonthlyObligation] = []
    for month in range(1, 13):
        month_start = date(year, month, 1)
        month_end = date(year, month, calendar.monthrange(year, month)[1])
        active_periods = [
            period
            for period in scheme_periods
            if period.period_start <= month_end and (period.period_end is None or period.period_end >= month_start)
        ]
        for scheme_period in active_periods:
            segment_start = max(month_start, scheme_period.period_start)
            segment_end = min(month_end, scheme_period.period_end or month_end)
            candidates = [decision for decision in decisions if decision.tax_scheme_id == scheme_period.tax_scheme_id]
            candidates_by_type: dict[int, tuple[int, YearDecision]] = {}
            for decision in candidates:
                if (
                    decision.year == year
                    and decision.period_start <= segment_end
                    and decision.period_end >= segment_start
                ):
                    priority = 1
                elif decision.year == year - 1 and (decision.is_provisional or decision.poziv_na_broj_next):
                    priority = 0
                else:
                    continue

                existing_candidate = candidates_by_type.get(decision.payment_type_id)
                if existing_candidate is None or (priority, decision.period_start) > (
                    existing_candidate[0],
                    existing_candidate[1].period_start,
                ):
                    candidates_by_type[decision.payment_type_id] = (priority, decision)
            by_type = {payment_type_id: candidate for payment_type_id, (_, candidate) in candidates_by_type.items()}

            for payment_type_id, decision in by_type.items():
                if decision.year == year:
                    accrual_start = max(segment_start, decision.period_start)
                    accrual_end = min(segment_end, decision.period_end)
                    if accrual_start > accrual_end:
                        continue
                else:
                    accrual_start, accrual_end = segment_start, segment_end
                active_days = (accrual_end - accrual_start).days + 1
                month_days = (month_end - month_start).days + 1
                if decision.prorate_partial_month:
                    amount = (Decimal(decision.monthly_amount) * Decimal(active_days) / Decimal(month_days)).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                else:
                    amount = Decimal(decision.monthly_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

                matching_existing = [
                    item
                    for item in existing
                    if item.id not in claimed_existing_ids
                    and item.month == month
                    and item.payment_type_id == payment_type_id
                    and (
                        item.tax_scheme_period_id == scheme_period.id
                        or (
                            item.tax_scheme_period_id is None
                            and item.tax_scheme_id in (None, scheme_period.tax_scheme_id)
                        )
                    )
                ]
                obligation = max(
                    matching_existing,
                    key=lambda item: (
                        item.status == "paid",
                        item.tax_scheme_period_id == scheme_period.id,
                        item.is_active,
                        item.id,
                    ),
                    default=None,
                )
                if obligation is not None:
                    claimed_existing_ids.add(obligation.id)
                deadline = (
                    scheme_period.closing_deadline
                    if scheme_period.period_end == accrual_end and scheme_period.closing_deadline
                    else deadline_for_month(year, month, decision.due_day, decision.due_month_offset)
                )
                if obligation is None:
                    obligation = MonthlyObligation(
                        year=year,
                        month=month,
                        tax_scheme_id=scheme_period.tax_scheme_id,
                        tax_scheme_period_id=scheme_period.id,
                        payment_type_id=payment_type_id,
                        decision_id=decision.id,
                        amount=amount,
                        accrual_period_start=accrual_start,
                        accrual_period_end=accrual_end,
                        deadline=deadline,
                        is_active=True,
                    )
                    initialize_obligation_status(obligation, "unpaid" if deadline >= today else "overdue")
                    db.add(obligation)
                    await db.flush()
                    existing.append(obligation)
                else:
                    obligation.tax_scheme_id = scheme_period.tax_scheme_id
                    obligation.tax_scheme_period_id = scheme_period.id
                    obligation.decision_id = decision.id
                    obligation.accrual_period_start = accrual_start
                    obligation.accrual_period_end = accrual_end
                    obligation.is_active = True
                    if obligation.status != "paid":
                        obligation.amount = amount
                        obligation.deadline = deadline
                        refresh_obligation_due_status(obligation, today=today)
                desired_ids.add(obligation.id)
                generated.append(obligation)

    for obligation in existing:
        if obligation.id not in desired_ids and obligation.status != "paid":
            obligation.is_active = False
        elif obligation.status == "paid" and obligation not in generated:
            generated.append(obligation)

    generated.sort(key=lambda item: (item.month, item.accrual_period_start or date.min, item.payment_type_id, item.id))
    if filter_payment_type_id is not None:
        return [item for item in generated if item.payment_type_id == filter_payment_type_id]
    if payment_type_code and filter_payment_type_id is None:
        return []
    return generated
