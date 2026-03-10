"""Report exports."""
from datetime import date
from io import BytesIO, StringIO
import csv
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.models import Income, Enterprise, User
from backend.auth import get_current_user_required
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os
import reportlab

router = APIRouter(prefix="/reports", tags=["reports"])

KPO_PRODUCTS_CONTRACT_TYPES = {"supply"}
CYRILLIC_TO_LATIN = {
    "А": "A", "а": "a", "Б": "B", "б": "b", "В": "V", "в": "v",
    "Г": "G", "г": "g", "Д": "D", "д": "d", "Ђ": "Dj", "ђ": "dj",
    "Е": "E", "е": "e", "Ж": "Z", "ж": "z", "З": "Z", "з": "z",
    "И": "I", "и": "i", "Ј": "J", "ј": "j", "К": "K", "к": "k",
    "Л": "L", "л": "l", "Љ": "Lj", "љ": "lj", "М": "M", "м": "m",
    "Н": "N", "н": "n", "Њ": "Nj", "њ": "nj", "О": "O", "о": "o",
    "П": "P", "п": "p", "Р": "R", "р": "r", "С": "S", "с": "s",
    "Т": "T", "т": "t", "Ћ": "C", "ћ": "c", "У": "U", "у": "u",
    "Ф": "F", "ф": "f", "Х": "H", "х": "h", "Ц": "C", "ц": "c",
    "Ч": "C", "ч": "c", "Џ": "Dz", "џ": "dz", "Ш": "S", "ш": "s",
}
_UNICODE_FONT_NAME = "KPOVera"
_UNICODE_FONT_REGISTERED = False


def _register_unicode_font() -> str:
    global _UNICODE_FONT_REGISTERED
    if not _UNICODE_FONT_REGISTERED:
        vera_path = os.path.join(os.path.dirname(reportlab.__file__), "fonts", "Vera.ttf")
        pdfmetrics.registerFont(TTFont(_UNICODE_FONT_NAME, vera_path))
        _UNICODE_FONT_REGISTERED = True
    return _UNICODE_FONT_NAME


def _to_serbian_latin(value: str | None) -> str:
    if value is None:
        return ""
    text = str(value)
    return "".join(CYRILLIC_TO_LATIN.get(char, char) for char in text)


def _format_amount(value: float | int | None) -> str:
    amount = float(value or 0)
    formatted = f"{amount:,.2f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def _split_kpo_amounts(income: Income) -> tuple[float, float]:
    contract_type = getattr(getattr(income, "contract", None), "contract_type", None)
    amount = float(income.amount_rsd or 0)
    if contract_type in KPO_PRODUCTS_CONTRACT_TYPES:
        return amount, 0.0
    return 0.0, amount


def _build_kpo_description(income: Income) -> str:
    client = income.client_name or (income.client.name if income.client else "") or "-"
    parts = [
        f"Racun {income.invoice_number}",
        client,
    ]
    if income.description:
        parts.append(income.description)
    return _to_serbian_latin(" / ".join(part for part in parts if part))


async def _load_kpo_incomes(db: AsyncSession, year: int, month: int | None) -> list[Income]:
    query = (
        select(Income)
        .options(selectinload(Income.client), selectinload(Income.contract))
        .where(
            Income.issued_date >= date(year, 1, 1),
            Income.issued_date <= date(year, 12, 31),
            Income.status != "cancelled",
        )
        .order_by(Income.issued_date, Income.id)
    )
    if month:
        import calendar

        last = calendar.monthrange(year, month)[1]
        query = query.where(Income.issued_date >= date(year, month, 1), Income.issued_date <= date(year, month, last))
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/kpo/csv")
async def export_kpo_csv(
    year: int = Query(...),
    month: int = Query(None, description="Месяц (опционально)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Export KPO as CSV."""
    incomes = await _load_kpo_incomes(db, year, month)

    csv_buffer = StringIO()
    writer = csv.writer(csv_buffer, delimiter=";", lineterminator="\n")
    writer.writerow(["Redni broj", "Datum i opis knjizenja", "Prihod od prodaje proizvoda", "Prihod od izvrsenih usluga", "Ukupni prihodi od delatnosti"])
    total_products = 0.0
    total_services = 0.0
    total_all = 0.0
    for index, income in enumerate(incomes, start=1):
        products_amount, services_amount = _split_kpo_amounts(income)
        total_amount = products_amount + services_amount
        total_products += products_amount
        total_services += services_amount
        total_all += total_amount
        writer.writerow([
            index,
            f"{income.issued_date} {_build_kpo_description(income)}",
            _format_amount(products_amount),
            _format_amount(services_amount),
            _format_amount(total_amount),
        ])
    writer.writerow(["", "UKUPNO", _format_amount(total_products), _format_amount(total_services), _format_amount(total_all)])

    content = csv_buffer.getvalue().encode("utf-8-sig")
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
    """Export KPO as PDF."""
    incomes = await _load_kpo_incomes(db, year, month)

    r_ent = await db.execute(select(Enterprise).limit(1))
    ent = r_ent.scalar_one_or_none()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1*cm, bottomMargin=1*cm)
    styles = getSampleStyleSheet()
    font_name = _register_unicode_font()
    styles["Title"].fontName = font_name
    styles["Normal"].fontName = font_name
    styles["BodyText"].fontName = font_name
    header_style = ParagraphStyle(
        "KPOHeader",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=8,
        leading=10,
    )
    elements = []

    title = Paragraph(
        _to_serbian_latin(
            f"Poslovna knjiga o ostvarenom prometu pausalno oporezovanih preduzetnika - {year}"
            + (f" / {month:02d}" if month else "")
        ),
        styles["Title"]
    )
    elements.append(title)
    elements.append(Spacer(1, 0.35*cm))

    if ent:
        elements.append(Paragraph(f"<b>Obveznik:</b> {_to_serbian_latin(ent.name)}", header_style))
        elements.append(Paragraph(f"<b>PIB:</b> {_to_serbian_latin(ent.pib or '-')}", header_style))
        if ent.address:
            elements.append(Paragraph(f"<b>Adresa:</b> {_to_serbian_latin(ent.address)}", header_style))
    period_label = f"01.01.{year} - 31.12.{year}" if not month else f"{month:02d}.{year}"
    elements.append(Paragraph(f"<b>Period:</b> {period_label}", header_style))
    elements.append(Spacer(1, 0.25*cm))

    data = [[
        Paragraph("<b>Redni broj</b>", header_style),
        Paragraph("<b>Datum i opis knjizenja</b>", header_style),
        Paragraph("<b>Prihod od prodaje proizvoda</b>", header_style),
        Paragraph("<b>Prihod od izvrsenih usluga</b>", header_style),
        Paragraph("<b>Ukupni prihodi od delatnosti</b>", header_style),
    ]]
    total_products = 0.0
    total_services = 0.0
    total_all = 0.0
    body_style = ParagraphStyle(
        "KPOBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=8,
        leading=10,
    )
    for index, income in enumerate(incomes, start=1):
        products_amount, services_amount = _split_kpo_amounts(income)
        total_amount = products_amount + services_amount
        total_products += products_amount
        total_services += services_amount
        total_all += total_amount
        data.append([
            str(index),
            Paragraph(_to_serbian_latin(f"{income.issued_date} - {_build_kpo_description(income)}"), body_style),
            _format_amount(products_amount) if products_amount else "",
            _format_amount(services_amount) if services_amount else "",
            _format_amount(total_amount),
        ])

    data.append([
        "",
        Paragraph("<b>UKUPNO</b>", body_style),
        _format_amount(total_products),
        _format_amount(total_services),
        _format_amount(total_all),
    ])

    table = Table(
        data,
        colWidths=[1.6*cm, 8.9*cm, 2.3*cm, 2.3*cm, 2.5*cm],
        repeatRows=1,
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9e2f3")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LEADING", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f8fafc")]),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black),
        ("FONTNAME", (0, -1), (-1, -1), font_name),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 0.7*cm))
    elements.append(Paragraph("M.P. ____________________", header_style))
    elements.append(Spacer(1, 0.25*cm))
    elements.append(Paragraph("Potpis odgovornog lica ____________________", header_style))

    doc.build(elements)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=kpo_{year}{f'_{month:02d}' if month else ''}.pdf"}
    )
