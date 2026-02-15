"""Сервис обязательных платежей — по ТЗ решений Пореске управе."""
from datetime import date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import PaymentType, YearDecision, MonthlyObligation


def deadline_for_month(year: int, month: int) -> date:
    """Дедлайн = 15-е число месяца, следующего за отчётным."""
    next_m = month + 1
    next_y = year
    if next_m > 12:
        next_m = 1
        next_y = year + 1
    return date(next_y, next_m, 15)


def payment_purpose_with_year(template: str, year: int) -> str:
    """Подставить год в шаблон сврха уплате (YYYY)."""
    return template.replace("YYYY", str(year))


async def ensure_payment_types(db: AsyncSession) -> None:
    """Создать типы платежей если их нет."""
    r = await db.execute(select(PaymentType).limit(1))
    if r.scalar_one_or_none():
        return
    types = [
        PaymentType(code="tax", name_sr="Порез на приход", name_ru="Налог на доход", sort_order=1),
        PaymentType(code="pio", name_sr="Допринос за ПИО", name_ru="Взнос ПИО", sort_order=2),
        PaymentType(code="health", name_sr="Здравствено осигурање", name_ru="Медстрах", sort_order=3),
        PaymentType(code="unemployment", name_sr="Незапосленост", name_ru="Безработица", sort_order=4),
    ]
    for t in types:
        db.add(t)
    await db.flush()


async def get_or_create_obligations(
    db: AsyncSession, year: int, payment_type_code: str | None = None
) -> list[MonthlyObligation]:
    """Получить или создать месячные обязательства за год. Обновить overdue."""
    today = date.today()
    # Решения на год: своё или привремене с прошлого
    q = (
        select(YearDecision)
        .where(YearDecision.year == year, YearDecision.is_active == True)
        .join(PaymentType)
    )
    if payment_type_code:
        q = q.where(PaymentType.code == payment_type_code)
    q = q.order_by(YearDecision.payment_type_id, YearDecision.is_provisional.asc())
    r = await db.execute(q)
    decisions = r.scalars().all()
    # Группируем по payment_type_id, берём первое (не provisional предпочтительнее)
    by_type = {}
    for d in decisions:
        if d.payment_type_id not in by_type or not d.is_provisional:
            by_type[d.payment_type_id] = d

    result = []
    for pt_id, dec in by_type.items():
        for month in range(1, 13):
            r2 = await db.execute(
                select(MonthlyObligation).where(
                    MonthlyObligation.year == year,
                    MonthlyObligation.month == month,
                    MonthlyObligation.payment_type_id == pt_id,
                )
            )
            ob = r2.scalar_one_or_none()
            if not ob:
                dl = deadline_for_month(year, month)
                ob = MonthlyObligation(
                    year=year,
                    month=month,
                    payment_type_id=pt_id,
                    decision_id=dec.id,
                    amount=dec.monthly_amount,
                    deadline=dl,
                    status="unpaid" if dl >= today else "overdue",
                )
                db.add(ob)
                await db.flush()
            elif ob.status != "paid":
                # Обновляем только неоплаченные: overdue и amount
                if ob.deadline < today:
                    ob.status = "overdue"
                ob.amount = dec.monthly_amount
            result.append(ob)
    result.sort(key=lambda x: (x.month, x.payment_type_id))
    return result


def presets_2026() -> list[dict]:
    """Пресеты из ТЗ для 2026 года."""
    return [
        {
            "payment_type_code": "tax",
            "year": 2026,
            "monthly_amount": 5122.16,
            "recipient_account": "840-71122843-32",
            "poziv_na_broj": "2624190000007887475",
            "poziv_na_broj_next": "2024190000008031910",
            "payment_purpose": "Porez na paušalni prihod za YYYY. godinu",
        },
        {
            "payment_type_code": "pio",
            "year": 2026,
            "monthly_amount": 12311.28,
            "recipient_account": "840-721419843-40",
            "poziv_na_broj": "2624190000007887475",
            "poziv_na_broj_next": "2024190000008031910",
            "payment_purpose": "Doprinos za PIO za YYYY. godinu",
        },
    ]
