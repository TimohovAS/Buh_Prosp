"""Роутер обязательных платежей (решения Пореске управе) — ТЗ."""
from datetime import date
from typing import Optional
import calendar
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import get_db
from backend.services import create_expense_reversal
from backend.models import PaymentType, YearDecision, MonthlyObligation, Enterprise, User, Expense
from backend.schemas import (
    PaymentTypeResponse,
    YearDecisionCreate,
    YearDecisionUpdate,
    YearDecisionResponse,
    MonthlyObligationResponse,
    ObligationMarkPaid,
    IPSQRData,
)
from backend.auth import get_current_user_required, require_edit_access
from backend.payments_service import (
    ensure_payment_types,
    get_or_create_obligations,
    deadline_for_month,
    payment_purpose_with_year,
    presets_2026,
)

router = APIRouter(prefix="/obligations", tags=["obligations"])


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
    await ensure_payment_types(db)
    obligations = await get_or_create_obligations(db, year, None)
    return {"ok": True, "count": len(obligations)}


@router.get("/types", response_model=list[PaymentTypeResponse])
async def list_payment_types(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Список типов платежей."""
    await ensure_payment_types(db)
    r = await db.execute(select(PaymentType).order_by(PaymentType.sort_order))
    return [PaymentTypeResponse.model_validate(t) for t in r.scalars().all()]


@router.get("/calendar", response_model=list[MonthlyObligationResponse])
async def list_obligations(
    year: int = Query(..., description="Год"),
    payment_type: Optional[str] = Query(None, description="Код типа: tax, pio, health, unemployment"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Календарь обязательств за год. Создаёт обязательства если их нет (по решениям)."""
    await ensure_payment_types(db)
    obligations = await get_or_create_obligations(db, year, payment_type)
    pt_ids = list({ob.payment_type_id for ob in obligations})
    type_map = {}
    if pt_ids:
        r_pt = await db.execute(select(PaymentType).where(PaymentType.id.in_(pt_ids)))
        for t in r_pt.scalars().all():
            type_map[t.id] = t
    result = []
    for ob in obligations:
        pt = type_map.get(ob.payment_type_id)
        d = MonthlyObligationResponse(
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
        result.append(d)
    return result


@router.get("/decisions", response_model=list[YearDecisionResponse])
async def list_decisions(
    year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Список решений по годам."""
    q = select(YearDecision).order_by(
        YearDecision.year.desc(), YearDecision.payment_type_id
    )
    if year:
        q = q.where(YearDecision.year == year)
    r = await db.execute(q)
    items = r.scalars().all()
    pt_ids = list({d.payment_type_id for d in items})
    type_map = {}
    if pt_ids:
        r_pt = await db.execute(select(PaymentType).where(PaymentType.id.in_(pt_ids)))
        for t in r_pt.scalars().all():
            type_map[t.id] = t
    out = []
    for d in items:
        t = type_map.get(d.payment_type_id)
        out.append(YearDecisionResponse(
            **{k: getattr(d, k) for k in ["id", "year", "payment_type_id", "period_start", "period_end",
               "monthly_amount", "base_amount", "rate_percent", "recipient_name", "recipient_account",
               "sifra_placanja", "model", "poziv_na_broj", "poziv_na_broj_next", "payment_purpose",
               "currency", "is_provisional", "is_active"] if hasattr(d, k)},
            payment_type_code=t.code if t else None,
            payment_type_name=t.name_sr if t else None,
        ))
    return out


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
    pt = await db.get(PaymentType, dec.payment_type_id) if dec.payment_type_id else None
    return YearDecisionResponse(
        **{k: getattr(dec, k) for k in ["id", "year", "payment_type_id", "period_start", "period_end",
           "monthly_amount", "base_amount", "rate_percent", "recipient_name", "recipient_account",
           "sifra_placanja", "model", "poziv_na_broj", "poziv_na_broj_next", "payment_purpose",
           "currency", "is_provisional", "is_active"]},
        payment_type_code=pt.code if pt else None,
        payment_type_name=pt.name_sr if pt else None,
    )


@router.post("/decisions", response_model=YearDecisionResponse)
async def create_decision(
    data: YearDecisionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Добавить решение на год."""
    r = await db.execute(
        select(YearDecision).where(
            YearDecision.year == data.year,
            YearDecision.payment_type_id == data.payment_type_id,
            YearDecision.is_provisional == data.is_provisional,
        )
    )
    if r.scalar_one_or_none():
        raise HTTPException(400, "Решение на этот год и тип уже существует")
    dec = YearDecision(**data.model_dump())
    db.add(dec)
    await db.flush()
    await db.refresh(dec)
    pt = await db.get(PaymentType, dec.payment_type_id) if dec.payment_type_id else None
    return YearDecisionResponse(
        **{k: getattr(dec, k) for k in ["id", "year", "payment_type_id", "period_start", "period_end",
           "monthly_amount", "base_amount", "rate_percent", "recipient_name", "recipient_account",
           "sifra_placanja", "model", "poziv_na_broj", "poziv_na_broj_next", "payment_purpose",
           "currency", "is_provisional", "is_active"]},
        payment_type_code=pt.code if pt else None,
        payment_type_name=pt.name_sr if pt else None,
    )


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
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(dec, k, v)
    await db.flush()
    await db.refresh(dec)
    pt = await db.get(PaymentType, dec.payment_type_id) if dec.payment_type_id else None
    return YearDecisionResponse(
        **{k: getattr(dec, k) for k in ["id", "year", "payment_type_id", "period_start", "period_end",
           "monthly_amount", "base_amount", "rate_percent", "recipient_name", "recipient_account",
           "sifra_placanja", "model", "poziv_na_broj", "poziv_na_broj_next", "payment_purpose",
           "currency", "is_provisional", "is_active"]},
        payment_type_code=pt.code if pt else None,
        payment_type_name=pt.name_sr if pt else None,
    )


@router.post("/decisions/apply-preset-2026")
async def apply_preset_2026(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Применить пресет 2026 из ТЗ (Порез + PIO)."""
    await ensure_payment_types(db)
    r_pt = await db.execute(select(PaymentType).where(PaymentType.code.in_(["tax", "pio"])))
    types = {t.code: t for t in r_pt.scalars().all()}
    created = 0
    for p in presets_2026():
        pt = types.get(p["payment_type_code"])
        if not pt:
            continue
        r = await db.execute(
            select(YearDecision).where(
                YearDecision.year == p["year"],
                YearDecision.payment_type_id == pt.id,
                YearDecision.is_provisional == False,
            )
        )
        if r.scalar_one_or_none():
            continue
        dec = YearDecision(
            year=p["year"],
            payment_type_id=pt.id,
            period_start=date(p["year"], 1, 1),
            period_end=date(p["year"], 12, 31),
            monthly_amount=p["monthly_amount"],
            recipient_account=p["recipient_account"],
            poziv_na_broj=p["poziv_na_broj"],
            poziv_na_broj_next=p.get("poziv_na_broj_next"),
            payment_purpose=p["payment_purpose"],
        )
        db.add(dec)
        created += 1
    await db.flush()
    return {"ok": True, "created": created}


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
    pt = await db.get(PaymentType, ob.payment_type_id) if ob.payment_type_id else None
    pt_name = pt.name_sr if pt else "Плаћање"
    desc = f"{pt_name} {ob.month:02d}/{ob.year}"
    expense = Expense(
        date=data.paid_date,
        description=desc,
        amount=ob.amount,
        currency="RSD",
        category="tax",
        note=data.payment_reference,
        paid_date=data.paid_date,
        source="obligation",
        is_tax_related=True,
        created_by=current_user.id,
    )
    db.add(expense)
    await db.flush()
    ob.status = "paid"
    ob.paid_date = data.paid_date
    ob.payment_reference = data.payment_reference
    ob.expense_id = expense.id
    await db.flush()
    return MonthlyObligationResponse(
        id=ob.id, year=ob.year, month=ob.month, payment_type_id=ob.payment_type_id,
        payment_type_code=pt.code if pt else None,
        payment_type_name=pt.name_sr if pt else None,
        amount=ob.amount, deadline=ob.deadline.isoformat(), status=ob.status,
        paid_date=ob.paid_date, payment_reference=ob.payment_reference,
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
    if ob.expense_id:
        exp = await db.get(Expense, ob.expense_id)
        if exp and getattr(exp, "status", "paid") != "reversed" and not getattr(exp, "reversed_expense_id", None):
            await create_expense_reversal(
                db, exp,
                reverse_date=ob.paid_date,
                source="obligation",
                created_by=current_user.id,
            )
        ob.expense_id = None
    today = date.today()
    ob.status = "overdue" if ob.deadline < today else "unpaid"
    ob.paid_date = None
    ob.payment_reference = None
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
    purpose = payment_purpose_with_year(dec.payment_purpose, ob.year)
    return IPSQRData(
        payer=payer,
        recipient=dec.recipient_name,
        account=dec.recipient_account,
        amount=ob.amount,
        currency=dec.currency,
        purpose=purpose,
        model=dec.model,
        reference=dec.poziv_na_broj,
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
        select(MonthlyObligation).where(MonthlyObligation.year == y)
    )
    items = r.scalars().all()
    today = date.today()
    unpaid_count = sum(1 for i in items if i.status in ("unpaid", "overdue"))
    overdue_count = sum(1 for i in items if i.status == "overdue")
    overdue_sum = sum(i.amount for i in items if i.status == "overdue")
    next_deadline = None
    for i in sorted(items, key=lambda x: x.deadline):
        if i.status in ("unpaid", "overdue") and i.deadline >= today:
            next_deadline = i.deadline.isoformat()
            break
    return {
        "unpaid_count": unpaid_count,
        "overdue_count": overdue_count,
        "overdue_sum": overdue_sum,
        "next_deadline": next_deadline,
    }
