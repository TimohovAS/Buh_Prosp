"""Effective-dated, reusable tax and statutory-payment schemes."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import MonthlyObligation, TaxScheme, TaxSchemePeriod, YearDecision


async def ensure_default_tax_scheme(db: AsyncSession, *, initial_date: date | None = None) -> TaxScheme:
    """Create a reusable wrapper around existing unassigned rules on first use."""
    result = await db.execute(select(TaxScheme).order_by(TaxScheme.id).limit(1))
    scheme = result.scalar_one_or_none()
    created = scheme is None
    if scheme is None:
        scheme = TaxScheme(
            code="default",
            name="Текущая схема",
            description="Базовая схема обязательных платежей",
        )
        db.add(scheme)
        await db.flush()

    orphan_result = await db.execute(select(YearDecision).where(YearDecision.tax_scheme_id.is_(None)))
    orphan_decisions = list(orphan_result.scalars().all())
    for decision in orphan_decisions:
        decision.tax_scheme_id = scheme.id

    orphan_obligations_result = await db.execute(
        select(MonthlyObligation).where(MonthlyObligation.tax_scheme_id.is_(None))
    )
    orphan_obligations = list(orphan_obligations_result.scalars().all())
    decision_schemes = {decision.id: decision.tax_scheme_id for decision in orphan_decisions}
    for obligation in orphan_obligations:
        obligation.tax_scheme_id = decision_schemes.get(obligation.decision_id, scheme.id)

    period_result = await db.execute(select(TaxSchemePeriod).where(TaxSchemePeriod.tax_scheme_id == scheme.id).limit(1))
    if period_result.scalar_one_or_none() is None and (created or orphan_decisions):
        starts = [decision.period_start for decision in orphan_decisions if decision.period_start]
        db.add(
            TaxSchemePeriod(
                tax_scheme_id=scheme.id,
                period_start=min(starts) if starts else initial_date or date(date.today().year, 1, 1),
                note="Начальный период схемы",
            )
        )
    await db.flush()
    return scheme


async def activate_tax_scheme(
    db: AsyncSession,
    scheme: TaxScheme,
    effective_from: date,
    *,
    closing_deadline: date | None = None,
    note: str | None = None,
) -> TaxSchemePeriod:
    """Insert or append a non-overlapping scheme period, including historical periods."""
    result = await db.execute(select(TaxSchemePeriod).order_by(TaxSchemePeriod.period_start))
    periods = list(result.scalars().all())
    current = next(
        (
            period
            for period in periods
            if period.period_start <= effective_from
            and (period.period_end is None or period.period_end >= effective_from)
        ),
        None,
    )
    if current and current.tax_scheme_id == scheme.id:
        return current
    next_period = next((period for period in periods if period.period_start > effective_from), None)
    period_end = next_period.period_start - timedelta(days=1) if next_period else None
    inherited_closing_deadline = None
    if current:
        if current.period_start == effective_from:
            raise ValueError("На эту дату уже начинается другая налоговая схема")
        period_end = current.period_end
        inherited_closing_deadline = current.closing_deadline
        current.period_end = effective_from - timedelta(days=1)
        current.closing_deadline = closing_deadline

    period = TaxSchemePeriod(
        tax_scheme_id=scheme.id,
        period_start=effective_from,
        period_end=period_end,
        closing_deadline=inherited_closing_deadline,
        note=(note or "").strip() or None,
    )
    db.add(period)
    await db.flush()
    return period
