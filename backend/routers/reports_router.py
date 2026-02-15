"""Роутер отчётов и экспорта."""
from datetime import date
from io import BytesIO
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.models import Income, Client, Enterprise, User
from backend.auth import get_current_user_required
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.units import cm

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/kpo/csv")
async def export_kpo_csv(
    year: int = Query(...),
    month: int = Query(None, description="Месяц (опционально)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Экспорт книги КПО в CSV."""
    q = select(Income).options(selectinload(Income.client)).where(
        Income.issued_date >= date(year, 1, 1),
        Income.issued_date <= date(year, 12, 31)
    ).order_by(Income.issued_date, Income.id)
    if month:
        import calendar
        last = calendar.monthrange(year, month)[1]
        q = q.where(Income.issued_date >= date(year, month, 1), Income.issued_date <= date(year, month, last))
    r = await db.execute(q)
    incomes = list(r.scalars().all())

    lines = ["Дата;№ счёта;Клиент;Основание;Сумма (RSD)"]
    for i in incomes:
        client = i.client_name or (i.client.name if i.client else "")
        lines.append(f"{i.issued_date};{i.invoice_number};{client};{i.description or ''};{i.amount_rsd:.2f}")

    content = "\n".join(lines).encode("utf-8-sig")
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=kpo_{year}{f'_{month:02d}' if month else ''}.csv"}
    )


@router.get("/kpo/pdf")
async def export_kpo_pdf(
    year: int = Query(...),
    month: int = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Экспорт книги КПО в PDF."""
    q = select(Income).options(selectinload(Income.client)).where(
        Income.issued_date >= date(year, 1, 1),
        Income.issued_date <= date(year, 12, 31)
    ).order_by(Income.issued_date, Income.id)
    if month:
        import calendar
        last = calendar.monthrange(year, month)[1]
        q = q.where(Income.issued_date >= date(year, month, 1), Income.issued_date <= date(year, month, last))
    r = await db.execute(q)
    incomes = list(r.scalars().all())

    r_ent = await db.execute(select(Enterprise).limit(1))
    ent = r_ent.scalar_one_or_none()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1*cm, bottomMargin=1*cm)
    styles = getSampleStyleSheet()
    elements = []

    title = Paragraph(
        f"Књига о оствареним приходима (КПО) - {year}" + (f" / {month}" if month else ""),
        styles["Title"]
    )
    elements.append(title)
    elements.append(Spacer(1, 0.5*cm))

    if ent:
        elements.append(Paragraph(f"<b>Предузеће:</b> {ent.name}", styles["Normal"]))
        elements.append(Paragraph(f"<b>PIB:</b> {ent.pib or '-'}", styles["Normal"]))
        elements.append(Spacer(1, 0.3*cm))

    data = [["Датум", "Бр. рачуна", "Клијент", "Основа", "Износ (RSD)"]]
    total = 0
    for i in incomes:
        client = i.client_name or (i.client.name if i.client else "-")
        data.append([str(i.issued_date), i.invoice_number, client[:30], (i.description or "")[:40], f"{i.amount_rsd:,.2f}"])
        total += i.amount_rsd

    data.append(["", "", "", "УКУПНО:", f"{total:,.2f}"])

    t = Table(data, colWidths=[2*cm, 3*cm, 4*cm, 5*cm, 3*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (4, 0), (4, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("BACKGROUND", (0, 1), (-1, -2), colors.beige),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    elements.append(t)

    doc.build(elements)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=kpo_{year}{f'_{month:02d}' if month else ''}.pdf"}
    )
