"""Сервисный слой для доходов (КПО) и обработки eFaktura."""
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional
from xml.etree import ElementTree as ET

from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Income
from backend.decimal_utils import to_decimal

EF_NS = {
    "env": "urn:eFaktura:MinFinrs:envelop:schema",
    "inv": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
}


def _extract_party_info(invoice: ET.Element, path: str) -> tuple[Optional[str], Optional[str]]:
    name = normalize_whitespace(
        invoice.findtext(f"{path}/cac:Party/cac:PartyName/cbc:Name", default="", namespaces=EF_NS)
    ) or normalize_whitespace(
        invoice.findtext(
            f"{path}/cac:Party/cac:PartyLegalEntity/cbc:RegistrationName",
            default="",
            namespaces=EF_NS,
        )
    )
    tax_id = normalize_whitespace(
        invoice.findtext(
            f"{path}/cac:Party/cac:PartyTaxScheme/cbc:CompanyID",
            default="",
            namespaces=EF_NS,
        )
    ) or normalize_whitespace(
        invoice.findtext(f"{path}/cac:Party/cbc:EndpointID", default="", namespaces=EF_NS)
    )
    return name, normalize_pib(tax_id)

def normalize_whitespace(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    compact = " ".join(value.split()).strip()
    return compact or None

def normalize_pib(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    if not digits:
        return None
    return digits[-9:] if len(digits) > 9 else digits

def normalize_name(value: Optional[str]) -> Optional[str]:
    text = normalize_whitespace(value)
    return text.lower() if text else None

def parse_invoice_number_parts(value: Optional[str]) -> tuple[Optional[int], Optional[int]]:
    """
    Разобрать номер фактуры в форматах YYYY-NNNN и NNNN-YYYY.
    Возвращает (year, serial) или (None, None), если шаблон не распознан.
    """
    s = (normalize_whitespace(value) or "").upper()
    if not s:
        return None, None
    m_year_first = re.fullmatch(r"(20\d{2})-(\d{1,10})", s)
    if m_year_first:
        return int(m_year_first.group(1)), int(m_year_first.group(2))
    m_num_first = re.fullmatch(r"(\d{1,10})-(20\d{2})", s)
    if m_num_first:
        return int(m_num_first.group(2)), int(m_num_first.group(1))
    return None, None

def invoice_identity(invoice_number: Optional[str], invoice_year: Optional[int]) -> tuple[Optional[int], str]:
    """
    Нормализованный ключ фактуры для сравнения дублей.
    Для числовых форматов сравниваем по (year, serial без ведущих нулей).
    """
    raw = (normalize_whitespace(invoice_number) or "").upper()
    parsed_year, serial = parse_invoice_number_parts(raw)
    year_key = parsed_year if parsed_year is not None else invoice_year
    if serial is not None:
        return year_key, str(serial)
    return year_key, raw

def to_number_year_format(invoice_number: Optional[str], fallback_year: Optional[int] = None) -> str:
    """Привести распознанный номер к формату NNNN-YYYY."""
    raw = (normalize_whitespace(invoice_number) or "")
    parsed_year, serial = parse_invoice_number_parts(raw)
    year_val = parsed_year if parsed_year is not None else fallback_year
    if serial is not None and year_val is not None:
        return f"{serial:04d}-{year_val}"
    return raw

async def has_invoice_duplicate(
    db: AsyncSession,
    invoice_number: str,
    invoice_year: int,
    exclude_income_id: Optional[int] = None,
) -> bool:
    """
    Проверка дубля с учётом форматов YYYY-NNNN и NNNN-YYYY.
    Нужна для старых данных, где могут встречаться оба формата.
    """
    target_year, target_key = invoice_identity(invoice_number, invoice_year)
    r = await db.execute(
        select(Income.id, Income.invoice_number, Income.invoice_year, Income.issued_date).where(
            or_(
                Income.invoice_year == invoice_year,
                and_(
                    Income.invoice_year.is_(None),
                    Income.issued_date >= date(invoice_year, 1, 1),
                    Income.issued_date <= date(invoice_year, 12, 31),
                ),
            )
        )
    )
    for income_id, existing_number, existing_year, issued_date in r.fetchall():
        if exclude_income_id is not None and int(income_id) == int(exclude_income_id):
            continue
        year_val = int(existing_year) if existing_year is not None else (issued_date.year if issued_date else None)
        ex_year, ex_key = invoice_identity(existing_number, year_val)
        if ex_year == target_year and ex_key == target_key:
            return True
    return False

def parse_efaktura_invoice(xml_bytes: bytes, file_name: str) -> dict:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError(f"{file_name}: не удалось прочитать XML ({exc})") from exc

    invoice = root.find("env:DocumentBody/inv:Invoice", EF_NS)
    if invoice is None and root.tag.endswith("Invoice"):
        invoice = root
    if invoice is None:
        raise ValueError(f"{file_name}: не найден блок Invoice")

    invoice_number = normalize_whitespace(invoice.findtext("cbc:ID", default="", namespaces=EF_NS))
    if not invoice_number:
        raise ValueError(f"{file_name}: отсутствует номер фактуры (cbc:ID)")

    issue_raw = normalize_whitespace(invoice.findtext("cbc:IssueDate", default="", namespaces=EF_NS))
    if not issue_raw:
        raise ValueError(f"{file_name}: отсутствует дата фактуры (cbc:IssueDate)")
    try:
        issue_date = date.fromisoformat(issue_raw)
    except ValueError as exc:
        raise ValueError(f"{file_name}: некорректная дата фактуры ({issue_raw})") from exc

    due_raw = normalize_whitespace(invoice.findtext("cbc:DueDate", default="", namespaces=EF_NS))
    due_date = None
    if due_raw:
        try:
            due_date = date.fromisoformat(due_raw)
        except ValueError as exc:
            raise ValueError(f"{file_name}: некорректная дата оплаты (cbc:DueDate={due_raw})") from exc

    amount_raw = normalize_whitespace(
        invoice.findtext("cac:LegalMonetaryTotal/cbc:PayableAmount", default="", namespaces=EF_NS)
    )
    if not amount_raw:
        raise ValueError(f"{file_name}: отсутствует сумма к оплате (cbc:PayableAmount)")
    normalized_amount = amount_raw.replace("\u00A0", "").replace(" ", "").replace(",", ".")
    try:
        amount_rsd = to_decimal(Decimal(normalized_amount))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{file_name}: некорректная сумма ({amount_raw})") from exc

    customer_name, customer_pib = _extract_party_info(invoice, "cac:AccountingCustomerParty")
    supplier_name, supplier_pib = _extract_party_info(invoice, "cac:AccountingSupplierParty")

    line_titles: list[str] = []
    for node in invoice.findall("cac:InvoiceLine/cac:Item/cbc:Name", EF_NS):
        line_name = normalize_whitespace(node.text)
        if line_name:
            line_titles.append(line_name)
    description = "; ".join(line_titles) if line_titles else f"eFaktura {invoice_number}"
    if len(description) > 500:
        description = f"{description[:497]}..."

    currency = normalize_whitespace(invoice.findtext("cbc:DocumentCurrencyCode", default="RSD", namespaces=EF_NS)) or "RSD"

    return {
        "invoice_number": to_number_year_format(invoice_number, issue_date.year),
        "issued_date": issue_date,
        "due_date": due_date,
        "amount_rsd": amount_rsd,
        "currency": currency,
        "client_name": customer_name,
        "customer_name": customer_name,
        "customer_pib": customer_pib,
        "supplier_name": supplier_name,
        "supplier_pib": supplier_pib,
        "description": description,
    }

def invoice_year_from_number(invoice_number: str) -> Optional[int]:
    """Год из номера YYYY-NNNN или NNNN-YYYY."""
    y, _ = parse_invoice_number_parts(invoice_number)
    return y


