"""Роутер обязательных платежей (решения Пореске управе) — ТЗ."""

from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from backend.database import get_db
from backend.obligation_payment_service import (
    mark_obligation_paid as apply_obligation_payment,
    reset_obligation_payment,
)
from backend.models import Enterprise, MonthlyObligation, PaymentType, TaxScheme, TaxSchemePeriod, User, YearDecision
from backend.state_machine import InvalidStatusTransition, obligation_status_for_date
from backend.schemas import (
    PaymentTypeCreate,
    PaymentTypeResponse,
    PaymentTypeUpdate,
    YearDecisionCreate,
    YearDecisionUpdate,
    YearDecisionResponse,
    MonthlyObligationResponse,
    ObligationMarkPaid,
    IPSQRData,
    TaxSchemeActivate,
    TaxSchemeCreate,
    TaxSchemeResponse,
    TaxSchemeUpdate,
)
from backend.auth import get_current_user_required, require_edit_access
from backend.payment_qr_service import build_ips_payload, normalize_ips_payment_purpose, render_qr_png_data_url
from backend.payments_service import (
    get_or_create_obligations,
    payment_reference_for_year,
    payment_purpose_with_year,
)
from backend.tax_scheme_service import activate_tax_scheme, ensure_default_tax_scheme

router = APIRouter(prefix="/obligations", tags=["obligations"])


async def _scheme_response(db: AsyncSession, scheme_id: int) -> TaxSchemeResponse:
    result = await db.execute(
        select(TaxScheme).options(selectinload(TaxScheme.periods)).where(TaxScheme.id == scheme_id)
    )
    return TaxSchemeResponse.model_validate(result.scalar_one())


async def _decision_response(db: AsyncSession, decision: YearDecision) -> YearDecisionResponse:
    payment_type = await db.get(PaymentType, decision.payment_type_id) if decision.payment_type_id else None
    tax_scheme = await db.get(TaxScheme, decision.tax_scheme_id) if decision.tax_scheme_id else None
    return YearDecisionResponse(
        **{
            key: getattr(decision, key)
            for key in [
                "id",
                "year",
                "tax_scheme_id",
                "payment_type_id",
                "period_start",
                "period_end",
                "monthly_amount",
                "base_amount",
                "rate_percent",
                "recipient_name",
                "recipient_account",
                "sifra_placanja",
                "model",
                "poziv_na_broj",
                "poziv_na_broj_next",
                "payment_purpose",
                "currency",
                "due_day",
                "due_month_offset",
                "prorate_partial_month",
                "is_provisional",
                "is_active",
            ]
        },
        payment_type_code=payment_type.code if payment_type else None,
        payment_type_name=payment_type.name_sr if payment_type else None,
        tax_scheme_name=tax_scheme.name if tax_scheme else None,
    )


async def _validate_decision_period(
    db: AsyncSession,
    *,
    year: int,
    scheme_id: int,
    payment_type_id: int,
    period_start: date,
    period_end: date,
    is_provisional: bool,
    exclude_id: int | None = None,
) -> None:
    if period_start > period_end:
        raise HTTPException(400, "Начало периода должно быть раньше его окончания")
    if period_start.year != year or period_end.year != year:
        raise HTTPException(400, "Период правила должен находиться внутри выбранного года")
    query = select(YearDecision).where(
        YearDecision.year == year,
        YearDecision.tax_scheme_id == scheme_id,
        YearDecision.payment_type_id == payment_type_id,
        YearDecision.is_provisional == is_provisional,
        YearDecision.is_active == True,
    )
    if exclude_id is not None:
        query = query.where(YearDecision.id != exclude_id)
    result = await db.execute(query)
    for existing in result.scalars().all():
        if existing.period_start <= period_end and existing.period_end >= period_start:
            raise HTTPException(400, "Период пересекается с другим активным правилом этой схемы")


@router.post("/generate")
async def generate_obligations(
    year: int = Query(..., description="Год"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """
    Создать/обновить MonthlyObligation на 12 месяцев по активным YearDecision.
    Берёт YearDecision где year=YYYY и is_active=true.
    Не создаёт дубликаты и не изменяет оплаченные обязательства.
    """
    obligations = await get_or_create_obligations(db, year, None)
    await db.commit()
    return {"ok": True, "count": len(obligations)}


@router.get("/types", response_model=list[PaymentTypeResponse])
async def list_payment_types(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Список типов платежей."""
    r = await db.execute(select(PaymentType).order_by(PaymentType.is_archived, PaymentType.sort_order, PaymentType.id))
    return [PaymentTypeResponse.model_validate(t) for t in r.scalars().all()]


@router.post("/types", response_model=PaymentTypeResponse)
async def create_payment_type(
    data: PaymentTypeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Create a custom payment type for this installation."""
    code = data.code.strip().lower()
    if await db.scalar(select(PaymentType.id).where(PaymentType.code == code)) is not None:
        raise HTTPException(400, "Тип платежа с таким кодом уже существует")
    payment_type = PaymentType(
        code=code,
        name_sr=data.name_sr.strip(),
        name_ru=(data.name_ru or "").strip() or None,
        sort_order=data.sort_order,
    )
    db.add(payment_type)
    await db.commit()
    await db.refresh(payment_type)
    return PaymentTypeResponse.model_validate(payment_type)


@router.patch("/types/{type_id}", response_model=PaymentTypeResponse)
async def update_payment_type(
    type_id: int,
    data: PaymentTypeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Rename, reorder or archive a user-configurable payment type."""
    payment_type = await db.get(PaymentType, type_id)
    if payment_type is None:
        raise HTTPException(404, "Тип платежа не найден")
    values = data.model_dump(exclude_unset=True)
    if "code" in values and values["code"] is not None:
        code = values["code"].strip().lower()
        duplicate_id = await db.scalar(
            select(PaymentType.id).where(PaymentType.code == code, PaymentType.id != payment_type.id)
        )
        if duplicate_id is not None:
            raise HTTPException(400, "Тип платежа с таким кодом уже существует")
        values["code"] = code
    if "name_sr" in values:
        values["name_sr"] = (values["name_sr"] or "").strip()
        if not values["name_sr"]:
            raise HTTPException(400, "Название типа платежа не может быть пустым")
    if "name_ru" in values and isinstance(values["name_ru"], str):
        values["name_ru"] = values["name_ru"].strip() or None
    for key, value in values.items():
        setattr(payment_type, key, value)
    await db.commit()
    await db.refresh(payment_type)
    return PaymentTypeResponse.model_validate(payment_type)


@router.get("/schemes", response_model=list[TaxSchemeResponse])
async def list_tax_schemes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Схемы налогообложения и полная история периодов их применения."""
    result = await db.execute(
        select(TaxScheme).options(selectinload(TaxScheme.periods)).order_by(TaxScheme.is_archived, TaxScheme.id)
    )
    return [TaxSchemeResponse.model_validate(item) for item in result.scalars().all()]


@router.post("/schemes", response_model=TaxSchemeResponse)
async def create_tax_scheme(
    data: TaxSchemeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    scheme = TaxScheme(name=data.name.strip(), description=(data.description or "").strip() or None)
    db.add(scheme)
    await db.commit()
    return await _scheme_response(db, scheme.id)


@router.patch("/schemes/{scheme_id}", response_model=TaxSchemeResponse)
async def update_tax_scheme(
    scheme_id: int,
    data: TaxSchemeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    scheme = await db.get(TaxScheme, scheme_id)
    if scheme is None:
        raise HTTPException(404, "Налоговая схема не найдена")
    for key, value in data.model_dump(exclude_unset=True).items():
        if isinstance(value, str):
            value = value.strip() or None
        if key == "name" and value is None:
            raise HTTPException(400, "Название налоговой схемы не может быть пустым")
        if key == "is_archived" and value:
            open_period_id = await db.scalar(
                select(TaxSchemePeriod.id)
                .where(TaxSchemePeriod.tax_scheme_id == scheme.id, TaxSchemePeriod.period_end.is_(None))
                .limit(1)
            )
            if open_period_id is not None:
                raise HTTPException(400, "Сначала примените другую схему, затем архивируйте эту")
        setattr(scheme, key, value)
    await db.commit()
    return await _scheme_response(db, scheme.id)


@router.post("/schemes/{scheme_id}/activate", response_model=TaxSchemeResponse)
async def activate_scheme(
    scheme_id: int,
    data: TaxSchemeActivate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    scheme = await db.get(TaxScheme, scheme_id)
    if scheme is None or scheme.is_archived:
        raise HTTPException(404, "Активная налоговая схема не найдена")
    rule_id = await db.scalar(
        select(YearDecision.id)
        .where(
            YearDecision.tax_scheme_id == scheme.id,
            YearDecision.is_active == True,
            (YearDecision.year == data.effective_from.year)
            | (
                (YearDecision.year == data.effective_from.year - 1)
                & ((YearDecision.is_provisional == True) | (YearDecision.poziv_na_broj_next.is_not(None)))
            ),
        )
        .limit(1)
    )
    if rule_id is None:
        raise HTTPException(400, "Сначала добавьте для схемы хотя бы одно налоговое решение")
    try:
        await activate_tax_scheme(
            db,
            scheme,
            data.effective_from,
            closing_deadline=data.closing_deadline,
            note=data.note,
        )
        await get_or_create_obligations(db, data.effective_from.year, None)
        await get_or_create_obligations(db, data.effective_from.year + 1, None)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return await _scheme_response(db, scheme.id)


@router.get("/years", response_model=list[int])
async def list_obligation_years(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Доступные годы для календаря обязательств."""
    decision_result = await db.execute(
        select(YearDecision.year, YearDecision.is_provisional, YearDecision.poziv_na_broj_next)
    )
    obligation_result = await db.execute(select(MonthlyObligation.year))
    years = {value for (value,) in obligation_result.all() if value is not None}
    for decision_year, is_provisional, next_year_reference in decision_result.all():
        years.add(decision_year)
        if is_provisional or next_year_reference:
            years.add(decision_year + 1)
    years.add(date.today().year)
    return sorted(years, reverse=True)


@router.get("/calendar", response_model=list[MonthlyObligationResponse])
async def list_obligations(
    year: int = Query(..., description="Год"),
    payment_type: Optional[str] = Query(None, description="Пользовательский код типа платежа"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Read-only calendar. Recalculation is performed only by explicit edit operations."""
    query = select(MonthlyObligation).where(
        MonthlyObligation.year == year,
        MonthlyObligation.is_active == True,
    )
    if payment_type:
        query = query.join(PaymentType).where(PaymentType.code == payment_type)
    obligations_result = await db.execute(
        query.order_by(
            MonthlyObligation.month,
            MonthlyObligation.accrual_period_start,
            MonthlyObligation.payment_type_id,
            MonthlyObligation.id,
        )
    )
    obligations = list(obligations_result.scalars().all())
    pt_ids = list({ob.payment_type_id for ob in obligations})
    scheme_ids = list({ob.tax_scheme_id for ob in obligations if ob.tax_scheme_id})
    type_map = {}
    scheme_map = {}
    if pt_ids:
        r_pt = await db.execute(select(PaymentType).where(PaymentType.id.in_(pt_ids)))
        for t in r_pt.scalars().all():
            type_map[t.id] = t
    if scheme_ids:
        r_scheme = await db.execute(select(TaxScheme).where(TaxScheme.id.in_(scheme_ids)))
        scheme_map = {scheme.id: scheme for scheme in r_scheme.scalars().all()}
    result = []
    for ob in obligations:
        pt = type_map.get(ob.payment_type_id)
        d = MonthlyObligationResponse(
            id=ob.id,
            year=ob.year,
            month=ob.month,
            tax_scheme_id=ob.tax_scheme_id,
            tax_scheme_period_id=ob.tax_scheme_period_id,
            tax_scheme_name=scheme_map.get(ob.tax_scheme_id).name if scheme_map.get(ob.tax_scheme_id) else None,
            payment_type_id=ob.payment_type_id,
            payment_type_code=pt.code if pt else None,
            payment_type_name=pt.name_sr if pt else None,
            amount=ob.amount,
            accrual_period_start=ob.accrual_period_start,
            accrual_period_end=ob.accrual_period_end,
            deadline=ob.deadline.isoformat(),
            status=obligation_status_for_date(ob),
            paid_date=ob.paid_date,
            payment_reference=ob.payment_reference,
        )
        result.append(d)
    return result


@router.get("/decisions", response_model=list[YearDecisionResponse])
async def list_decisions(
    year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Список решений по годам."""
    q = select(YearDecision).order_by(YearDecision.year.desc(), YearDecision.payment_type_id)
    if year:
        q = q.where(YearDecision.year == year)
    r = await db.execute(q)
    items = r.scalars().all()
    return [await _decision_response(db, decision) for decision in items]


@router.get("/decisions/{dec_id}", response_model=YearDecisionResponse)
async def get_decision(
    dec_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Получить решение по id."""
    dec = await db.get(YearDecision, dec_id)
    if not dec:
        raise HTTPException(404, "Решение не найдено")
    return await _decision_response(db, dec)


@router.post("/decisions", response_model=YearDecisionResponse)
async def create_decision(
    data: YearDecisionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Добавить решение на год."""
    default_scheme = await ensure_default_tax_scheme(db, initial_date=data.period_start)
    scheme_id = data.tax_scheme_id or default_scheme.id
    if await db.get(TaxScheme, scheme_id) is None:
        raise HTTPException(400, "Налоговая схема не найдена")
    payment_type = await db.get(PaymentType, data.payment_type_id)
    if payment_type is None or payment_type.is_archived:
        raise HTTPException(400, "Активный тип платежа не найден")
    await _validate_decision_period(
        db,
        year=data.year,
        scheme_id=scheme_id,
        payment_type_id=data.payment_type_id,
        period_start=data.period_start,
        period_end=data.period_end,
        is_provisional=data.is_provisional,
    )
    payload = data.model_dump()
    payload["tax_scheme_id"] = scheme_id
    dec = YearDecision(**payload)
    db.add(dec)
    await db.flush()
    await get_or_create_obligations(db, dec.year, None)
    if dec.poziv_na_broj_next:
        await get_or_create_obligations(db, dec.year + 1, None)
    await db.commit()
    await db.refresh(dec)
    return await _decision_response(db, dec)


@router.patch("/decisions/{dec_id}", response_model=YearDecisionResponse)
async def update_decision(
    dec_id: int,
    data: YearDecisionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Обновить решение."""
    dec = await db.get(YearDecision, dec_id)
    if not dec:
        raise HTTPException(404, "Решение не найдено")
    values = data.model_dump(exclude_unset=True)
    period_start = values.get("period_start", dec.period_start)
    period_end = values.get("period_end", dec.period_end)
    scheme_id = values.get("tax_scheme_id", dec.tax_scheme_id)
    if scheme_id is None:
        scheme_id = (await ensure_default_tax_scheme(db, initial_date=period_start)).id
    is_provisional = values.get("is_provisional", dec.is_provisional)
    await _validate_decision_period(
        db,
        year=dec.year,
        scheme_id=scheme_id,
        payment_type_id=dec.payment_type_id,
        period_start=period_start,
        period_end=period_end,
        is_provisional=is_provisional,
        exclude_id=dec.id,
    )
    for k, v in values.items():
        if k == "tax_scheme_id" and v is not None and await db.get(TaxScheme, v) is None:
            raise HTTPException(400, "Налоговая схема не найдена")
        setattr(dec, k, v)
    await db.flush()
    await get_or_create_obligations(db, dec.year, None)
    await get_or_create_obligations(db, dec.year + 1, None)
    await db.commit()
    await db.refresh(dec)
    return await _decision_response(db, dec)


@router.patch("/obligations/{ob_id}/mark-paid", response_model=MonthlyObligationResponse)
async def mark_obligation_paid(
    ob_id: int,
    data: ObligationMarkPaid,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Отметить обязательство как оплаченное и создать запись в расходах."""
    ob = await db.get(MonthlyObligation, ob_id)
    if not ob:
        raise HTTPException(404, "Обязательство не найдено")
    try:
        await apply_obligation_payment(
            db,
            ob,
            data.paid_date,
            payment_reference=data.payment_reference,
            created_by=current_user.id,
            payment_method="manual",
        )
    except InvalidStatusTransition as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    await db.refresh(ob)
    pt = await db.get(PaymentType, ob.payment_type_id) if ob.payment_type_id else None
    return MonthlyObligationResponse(
        id=ob.id,
        year=ob.year,
        month=ob.month,
        payment_type_id=ob.payment_type_id,
        payment_type_code=pt.code if pt else None,
        payment_type_name=pt.name_sr if pt else None,
        amount=ob.amount,
        deadline=ob.deadline.isoformat(),
        status=ob.status,
        paid_date=ob.paid_date,
        payment_reference=ob.payment_reference,
    )


@router.patch("/obligations/{ob_id}/mark-unpaid")
async def mark_obligation_unpaid(
    ob_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Отменить отметку об оплате. Расход сторнируется через reverse, не удаляется."""
    ob = await db.get(MonthlyObligation, ob_id)
    if not ob:
        raise HTTPException(404, "Обязательство не найдено")
    try:
        await reset_obligation_payment(db, ob, created_by=current_user.id)
    except InvalidStatusTransition as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return {"ok": True}


@router.get("/obligations/{ob_id}/ips-qr", response_model=IPSQRData)
async def get_ips_qr(
    ob_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Данные для IPS QR (NBS) по обязательству."""
    ob = await db.get(MonthlyObligation, ob_id)
    if not ob or not ob.decision_id:
        raise HTTPException(404, "Обязательство не найдено")
    dec = await db.get(YearDecision, ob.decision_id)
    if not dec:
        raise HTTPException(404, "Решение не найдено")
    ent = await db.execute(select(Enterprise).limit(1))
    e = ent.scalar_one_or_none()
    payer = f"{e.name or 'Предузетник'}" if e else "Предузетник"
    if e and e.address:
        payer += f", {e.address}"
    purpose = normalize_ips_payment_purpose(payment_purpose_with_year(dec.payment_purpose, ob.year))
    payment_reference = payment_reference_for_year(dec, ob.year)
    try:
        payload = build_ips_payload(
            recipient_account=dec.recipient_account,
            recipient_name=dec.recipient_name,
            amount=ob.amount,  # реальная сумма обязательства, чтобы не вводить вручную
            sifra_placanja=dec.sifra_placanja,
            payment_purpose=purpose,
            model=dec.model,
            poziv_na_broj=payment_reference,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return IPSQRData(
        payer=payer,
        recipient=dec.recipient_name,
        account=dec.recipient_account,
        amount=ob.amount,
        currency=dec.currency,
        purpose=purpose,
        model=dec.model,
        reference=payment_reference,
        payload=payload,
        qr_png=render_qr_png_data_url(payload),
    )


@router.get("/summary")
async def get_obligations_summary(
    year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Сводка: к оплате, просрочено (для дашборда)."""
    y = year or date.today().year
    r = await db.execute(
        select(MonthlyObligation).where(
            MonthlyObligation.year == y,
            MonthlyObligation.is_active == True,
        )
    )
    items = r.scalars().all()
    today = date.today()
    statuses = {item.id: obligation_status_for_date(item, today=today) for item in items}
    unpaid_count = sum(1 for item in items if statuses[item.id] in ("unpaid", "overdue"))
    overdue_count = sum(1 for item in items if statuses[item.id] == "overdue")
    overdue_sum = sum(item.amount for item in items if statuses[item.id] == "overdue")
    next_deadline = None
    for item in sorted(items, key=lambda value: value.deadline):
        if statuses[item.id] in ("unpaid", "overdue") and item.deadline >= today:
            next_deadline = item.deadline.isoformat()
            break
    return {
        "unpaid_count": unpaid_count,
        "overdue_count": overdue_count,
        "overdue_sum": overdue_sum,
        "next_deadline": next_deadline,
    }
