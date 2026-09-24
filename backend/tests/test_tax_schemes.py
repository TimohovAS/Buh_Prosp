from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from backend.models import MonthlyObligation, PaymentType, TaxScheme, TaxSchemePeriod, YearDecision
from backend.payments_service import (
    configured_obligation_years,
    get_or_create_obligations,
    payment_reference_for_year,
    regenerate_configured_obligations,
)
from backend.routers.obligations_router import list_obligations
from backend.state_machine import obligation_status_for_date
from backend.tax_scheme_service import (
    activate_tax_scheme,
    ensure_default_tax_scheme,
)


pytestmark = pytest.mark.asyncio


async def _legacy_decision(db, scheme, payment_type, amount, account):
    decision = YearDecision(
        year=2026,
        tax_scheme_id=scheme.id,
        payment_type_id=payment_type.id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        monthly_amount=Decimal(amount),
        recipient_account=account,
        poziv_na_broj="2624190000007887475",
        payment_purpose=f"{payment_type.code} YYYY",
    )
    db.add(decision)
    await db.flush()
    return decision


async def _setup_legacy_scheme(db):
    for order, (code, name) in enumerate(
        [
            ("tax", "Tax"),
            ("pio", "PIO"),
            ("health", "Health"),
            ("unemployment", "Unemployment"),
        ],
        start=1,
    ):
        db.add(PaymentType(code=code, name_sr=name, sort_order=order))
    await db.flush()
    scheme = await ensure_default_tax_scheme(db)
    result = await db.execute(select(PaymentType))
    types = {item.code: item for item in result.scalars().all()}
    await _legacy_decision(db, scheme, types["tax"], "5122.16", "840-711122843-32")
    await _legacy_decision(db, scheme, types["pio"], "12311.28", "840-721419843-40")
    return scheme, types


async def _setup_primary_scheme(db, types):
    scheme = TaxScheme(
        code="primary_activity",
        name="Основная деятельность предпринимателя",
        description="Тестовая схема с полным набором взносов",
    )
    db.add(scheme)
    await db.flush()
    await activate_tax_scheme(
        db,
        scheme,
        date(2026, 9, 21),
        closing_deadline=date(2026, 10, 7),
        note="Тестовый переход",
    )
    rules = {
        "tax": ("5122.16", "840-711122843-32"),
        "pio": ("12311.28", "840-721313843-74"),
        "health": ("5283.59", "840-721325843-61"),
        "unemployment": ("384.73", "840-721331843-06"),
    }
    for code, (amount, account) in rules.items():
        decision = YearDecision(
            year=2026,
            tax_scheme_id=scheme.id,
            payment_type_id=types[code].id,
            period_start=date(2026, 9, 21),
            period_end=date(2026, 12, 31),
            monthly_amount=Decimal(amount),
            recipient_name="Test recipient",
            recipient_account=account,
            poziv_na_broj="test-reference",
            poziv_na_broj_next="next-reference",
            payment_purpose=f"{code} YYYY",
        )
        db.add(decision)
    await db.flush()
    return scheme


async def test_primary_activity_transition_prorates_september_from_decisions(db_session):
    legacy, types = await _setup_legacy_scheme(db_session)

    primary = await _setup_primary_scheme(db_session, types)
    obligations = await get_or_create_obligations(db_session, 2026)

    september = {(item.tax_scheme_id, item.payment_type_id): item for item in obligations if item.month == 9}
    closing_tax = september[(legacy.id, types["tax"].id)]
    closing_pio = september[(legacy.id, types["pio"].id)]
    assert closing_tax.amount == Decimal("3414.77")
    assert closing_pio.amount == Decimal("8207.52")
    assert closing_tax.amount + closing_pio.amount == Decimal("11622.29")
    assert closing_tax.deadline == date(2026, 10, 7)
    assert closing_pio.deadline == date(2026, 10, 7)
    assert closing_tax.accrual_period_start == date(2026, 9, 1)
    assert closing_tax.accrual_period_end == date(2026, 9, 20)

    primary_september = {
        payment_type_id: september[(primary.id, payment_type_id)]
        for payment_type_id in [types[code].id for code in ("tax", "pio", "health", "unemployment")]
    }
    assert primary_september[types["tax"].id].amount == Decimal("1707.39")
    assert primary_september[types["pio"].id].amount == Decimal("4103.76")
    assert primary_september[types["health"].id].amount == Decimal("1761.20")
    assert primary_september[types["unemployment"].id].amount == Decimal("128.24")
    assert all(item.accrual_period_start == date(2026, 9, 21) for item in primary_september.values())
    assert all(item.accrual_period_end == date(2026, 9, 30) for item in primary_september.values())

    august = [item for item in obligations if item.month == 8]
    assert {item.payment_type_id for item in august} == {types["tax"].id, types["pio"].id}
    assert all(item.tax_scheme_id == legacy.id for item in august)

    october = {item.payment_type_id: item.amount for item in obligations if item.month == 10}
    assert october == {
        types["tax"].id: Decimal("5122.16"),
        types["pio"].id: Decimal("12311.28"),
        types["health"].id: Decimal("5283.59"),
        types["unemployment"].id: Decimal("384.73"),
    }


async def test_switching_back_splits_the_month_between_scheme_periods(db_session):
    legacy, types = await _setup_legacy_scheme(db_session)
    primary = await _setup_primary_scheme(db_session, types)
    await get_or_create_obligations(db_session, 2026)

    await activate_tax_scheme(db_session, legacy, date(2026, 11, 10), note="Основная работа возобновлена")
    obligations = await get_or_create_obligations(db_session, 2026)

    november = {
        (item.tax_scheme_id, item.payment_type_id): item
        for item in obligations
        if item.month == 11 and item.status != "paid"
    }
    assert november[(primary.id, types["tax"].id)].amount == Decimal("1536.65")
    assert november[(primary.id, types["pio"].id)].amount == Decimal("3693.38")
    assert november[(primary.id, types["health"].id)].amount == Decimal("1585.08")
    assert november[(primary.id, types["unemployment"].id)].amount == Decimal("115.42")
    assert november[(legacy.id, types["tax"].id)].amount == Decimal("3585.51")
    assert november[(legacy.id, types["pio"].id)].amount == Decimal("8617.90")
    assert all(
        item.accrual_period_end == date(2026, 11, 9)
        for (scheme_id, _), item in november.items()
        if scheme_id == primary.id
    )
    assert all(
        item.accrual_period_start == date(2026, 11, 10)
        for (scheme_id, _), item in november.items()
        if scheme_id == legacy.id
    )


async def test_payment_type_filter_never_deactivates_other_obligations(db_session):
    _, types = await _setup_legacy_scheme(db_session)
    await _setup_primary_scheme(db_session, types)
    await get_or_create_obligations(db_session, 2026)

    filtered = await get_or_create_obligations(db_session, 2026, payment_type_code="tax")
    assert filtered
    assert {item.payment_type_id for item in filtered} == {types["tax"].id}

    active_october_result = await db_session.execute(
        select(MonthlyObligation).where(
            MonthlyObligation.month == 10,
            MonthlyObligation.is_active == True,
        )
    )
    assert {item.payment_type_id for item in active_october_result.scalars().all()} == {
        types["tax"].id,
        types["pio"].id,
        types["health"].id,
        types["unemployment"].id,
    }


async def test_calendar_filter_is_read_only(db_session):
    _, types = await _setup_legacy_scheme(db_session)
    await _setup_primary_scheme(db_session, types)
    await get_or_create_obligations(db_session, 2026)
    await db_session.commit()

    class ReadOnlySession:
        async def execute(self, statement):
            return await db_session.execute(statement)

        async def commit(self):
            raise AssertionError("GET /calendar must not commit")

    response = await list_obligations(
        year=2026,
        payment_type="tax",
        db=ReadOnlySession(),
        current_user=None,
    )
    assert response
    assert {item.payment_type_id for item in response} == {types["tax"].id}


async def test_scheme_period_can_be_inserted_before_a_future_period(db_session):
    earlier = TaxScheme(name="Историческая схема")
    future = TaxScheme(name="Будущая схема")
    db_session.add_all([earlier, future])
    await db_session.flush()

    future_period = await activate_tax_scheme(db_session, future, date(2026, 10, 1))
    earlier_period = await activate_tax_scheme(db_session, earlier, date(2025, 1, 1))

    assert earlier_period.period_start == date(2025, 1, 1)
    assert earlier_period.period_end == date(2026, 9, 30)
    assert future_period.period_start == date(2026, 10, 1)
    assert future_period.period_end is None


async def test_default_scheme_starts_with_the_first_historical_rule(db_session):
    scheme = await ensure_default_tax_scheme(db_session, initial_date=date(2025, 1, 1))
    result = await db_session.execute(select(TaxSchemePeriod).where(TaxSchemePeriod.tax_scheme_id == scheme.id))
    period = result.scalar_one()

    assert period.period_start == date(2025, 1, 1)


async def test_next_year_obligations_use_previous_decision_and_next_reference(db_session):
    _, types = await _setup_legacy_scheme(db_session)
    primary = await _setup_primary_scheme(db_session, types)

    obligations = await get_or_create_obligations(db_session, 2027)
    january = [item for item in obligations if item.month == 1 and item.tax_scheme_id == primary.id]

    assert len(january) == 4
    assert {item.amount for item in january} == {
        Decimal("5122.16"),
        Decimal("12311.28"),
        Decimal("5283.59"),
        Decimal("384.73"),
    }
    assert {item.deadline for item in january} == {date(2027, 2, 15)}
    decisions = [await db_session.get(YearDecision, item.decision_id) for item in january]
    assert all(decision.year == 2026 for decision in decisions)
    assert all(payment_reference_for_year(decision, 2027) == "next-reference" for decision in decisions)


async def test_new_year_rule_replaces_only_its_own_payment_type(db_session):
    _, types = await _setup_legacy_scheme(db_session)
    primary = await _setup_primary_scheme(db_session, types)
    current_tax = YearDecision(
        year=2027,
        tax_scheme_id=primary.id,
        payment_type_id=types["tax"].id,
        period_start=date(2027, 4, 1),
        period_end=date(2027, 12, 31),
        monthly_amount=Decimal("6000.00"),
        recipient_name="Test recipient",
        recipient_account="840-711122843-32",
        poziv_na_broj="current-tax-reference",
        payment_purpose="tax YYYY",
    )
    db_session.add(current_tax)
    await db_session.flush()

    obligations = await get_or_create_obligations(db_session, 2027)
    april = {item.payment_type_id: item for item in obligations if item.month == 4 and item.tax_scheme_id == primary.id}

    assert set(april) == {types[code].id for code in ("tax", "pio", "health", "unemployment")}
    assert april[types["tax"].id].amount == Decimal("6000.00")
    assert april[types["tax"].id].decision_id == current_tax.id
    for code in ("pio", "health", "unemployment"):
        carried_decision = await db_session.get(YearDecision, april[types[code].id].decision_id)
        assert carried_decision.year == 2026
        assert payment_reference_for_year(carried_decision, 2027) == "next-reference"


async def test_startup_reconciliation_does_not_seed_clean_install(db_session):
    assert await configured_obligation_years(db_session) == []
    assert await regenerate_configured_obligations(db_session) == []
    assert await db_session.scalar(select(TaxScheme.id)) is None


async def test_unpaid_status_becomes_overdue_at_read_time_without_mutation(db_session):
    obligation = MonthlyObligation(
        year=2026,
        month=9,
        payment_type_id=1,
        amount=Decimal("11622.29"),
        deadline=date(2026, 10, 7),
        status="unpaid",
    )

    assert obligation_status_for_date(obligation, today=date(2026, 10, 8)) == "overdue"
    assert obligation.status == "unpaid"


@pytest.mark.parametrize("paid_has_scheme_period", [False, True])
async def test_reconciliation_preserves_paid_obligation_and_disables_empty_duplicate(
    db_session, paid_has_scheme_period
):
    scheme, types = await _setup_legacy_scheme(db_session)
    period = await db_session.scalar(select(TaxSchemePeriod).where(TaxSchemePeriod.tax_scheme_id == scheme.id))
    decision = await db_session.scalar(
        select(YearDecision).where(
            YearDecision.tax_scheme_id == scheme.id,
            YearDecision.payment_type_id == types["tax"].id,
        )
    )
    paid = MonthlyObligation(
        year=2026,
        month=1,
        tax_scheme_id=scheme.id,
        tax_scheme_period_id=period.id if paid_has_scheme_period else None,
        payment_type_id=types["tax"].id,
        decision_id=decision.id,
        amount=Decimal("5122.16"),
        deadline=date(2026, 2, 15),
        status="paid",
        paid_date=date(2026, 2, 10),
        payment_reference="paid-transaction",
        is_active=True,
    )
    duplicate = MonthlyObligation(
        year=2026,
        month=1,
        tax_scheme_id=scheme.id,
        tax_scheme_period_id=period.id,
        payment_type_id=types["tax"].id,
        decision_id=decision.id,
        amount=Decimal("5122.16"),
        deadline=date(2026, 2, 15),
        status="overdue",
        is_active=True,
    )
    db_session.add_all([paid, duplicate])
    await db_session.flush()

    await get_or_create_obligations(db_session, 2026)

    assert paid.status == "paid"
    assert paid.paid_date == date(2026, 2, 10)
    assert paid.payment_reference == "paid-transaction"
    assert paid.tax_scheme_period_id == period.id
    assert paid.is_active is True
    assert duplicate.is_active is False
    active_rows = await db_session.scalars(
        select(MonthlyObligation).where(
            MonthlyObligation.year == 2026,
            MonthlyObligation.month == 1,
            MonthlyObligation.payment_type_id == types["tax"].id,
            MonthlyObligation.is_active == True,
        )
    )
    assert list(active_rows) == [paid]


async def test_rule_can_use_custom_deadline_and_disable_proration(db_session):
    scheme, _ = await _setup_legacy_scheme(db_session)
    custom_type = PaymentType(code="license_fee", name_sr="License fee", sort_order=10)
    db_session.add(custom_type)
    await db_session.flush()
    db_session.add(
        YearDecision(
            year=2026,
            tax_scheme_id=scheme.id,
            payment_type_id=custom_type.id,
            period_start=date(2026, 9, 21),
            period_end=date(2026, 12, 31),
            monthly_amount=Decimal("100.00"),
            recipient_name="Municipality",
            recipient_account="test-account",
            poziv_na_broj="test-reference",
            payment_purpose="License fee YYYY",
            due_day=31,
            due_month_offset=0,
            prorate_partial_month=False,
        )
    )
    await db_session.flush()

    obligations = await get_or_create_obligations(db_session, 2026)
    september = next(item for item in obligations if item.month == 9 and item.payment_type_id == custom_type.id)
    assert september.amount == Decimal("100.00")
    assert september.deadline == date(2026, 9, 30)
