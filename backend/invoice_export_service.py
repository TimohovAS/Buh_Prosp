from decimal import Decimal
from xml.etree import ElementTree as ET

from backend.decimal_utils import to_decimal
from backend.models import Client, Enterprise, Income, IncomeItem

UBL_INVOICE_NS = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
CBC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
CAC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
SERBIAN_CIUS_CUSTOMIZATION_ID = "urn:cen.eu:en16931:2017#compliant#urn:mfin.gov.rs:srbdt:2021"
NON_VAT_CATEGORY = "O"
NON_VAT_RATE = Decimal("0")
NON_VAT_EXEMPTION_REASON = "Nije u sistemu PDV-a"
# TODO: Add cbc:TaxExemptionReasonCode after confirming the exact Serbian
# eFaktura code for a small non-VAT taxpayer / pausalac. Do not reuse
# PDV-RS-11-1-4: that code belongs to a different exemption basis.

ET.register_namespace("", UBL_INVOICE_NS)
ET.register_namespace("cbc", CBC_NS)
ET.register_namespace("cac", CAC_NS)


def _money(value: Decimal | float | int | None) -> str:
    return f"{to_decimal(value or 0):.2f}"


def _quantity(value: Decimal | float | int | None) -> str:
    return f"{to_decimal(value or 0):.3f}".rstrip("0").rstrip(".")


def _tag(ns: str, name: str) -> str:
    return f"{{{ns}}}{name}"


def _unit_code(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    return {
        "kom": "H87",
        "kom.": "H87",
        "pcs": "H87",
        "piece": "H87",
        "dan": "DAY",
        "day": "DAY",
        "sat": "HUR",
        "hour": "HUR",
        "h": "HUR",
    }.get(normalized, normalized.upper() or "H87")


def _pib_number(value: str | None) -> str:
    normalized = (value or "").strip().upper()
    if normalized.startswith("RS"):
        normalized = normalized[2:].strip()
    return normalized


def _vat_identifier(value: str | None) -> str:
    pib = _pib_number(value)
    return f"RS{pib}" if pib else ""


def _sub(parent: ET.Element, ns: str, name: str, text: str | None = None, **attrs: str) -> ET.Element:
    node = ET.SubElement(parent, _tag(ns, name), attrs)
    if text is not None:
        node.text = text
    return node


def _party(parent: ET.Element, tag_name: str, name: str | None, pib: str | None, address: str | None) -> None:
    party_wrapper = _sub(parent, CAC_NS, tag_name)
    party = _sub(party_wrapper, CAC_NS, "Party")
    pib_number = _pib_number(pib)
    if pib_number:
        _sub(party, CBC_NS, "EndpointID", pib_number, schemeID="9948")

    if address:
        postal_address = _sub(party, CAC_NS, "PostalAddress")
        _sub(postal_address, CBC_NS, "StreetName", address)
        country = _sub(postal_address, CAC_NS, "Country")
        _sub(country, CBC_NS, "IdentificationCode", "RS")

    party_tax_scheme = _sub(party, CAC_NS, "PartyTaxScheme")
    _sub(party_tax_scheme, CBC_NS, "CompanyID", _vat_identifier(pib))
    tax_scheme = _sub(party_tax_scheme, CAC_NS, "TaxScheme")
    _sub(tax_scheme, CBC_NS, "ID", "VAT")

    legal_entity = _sub(party, CAC_NS, "PartyLegalEntity")
    _sub(legal_entity, CBC_NS, "RegistrationName", name or "")


def _line_items(income: Income) -> list[IncomeItem]:
    items = list(getattr(income, "items", []) or [])
    if items:
        return items
    fallback = IncomeItem(
        line_no=1,
        name=income.description or income.invoice_number,
        quantity=Decimal("1"),
        unit="kom",
        unit_price=income.amount_rsd,
        total_amount=income.amount_rsd,
        tax_category=NON_VAT_CATEGORY,
        tax_rate=NON_VAT_RATE,
    )
    return [fallback]


def build_income_efaktura_xml(income: Income, enterprise: Enterprise, client: Client | None = None) -> bytes:
    currency = income.currency or "RSD"
    items = _line_items(income)
    line_total = sum((to_decimal(item.total_amount or 0) for item in items), Decimal("0"))
    payable_total = to_decimal(income.amount_rsd or line_total)

    invoice = ET.Element(_tag(UBL_INVOICE_NS, "Invoice"))
    _sub(invoice, CBC_NS, "CustomizationID", SERBIAN_CIUS_CUSTOMIZATION_ID)
    _sub(invoice, CBC_NS, "ID", income.invoice_number)
    _sub(invoice, CBC_NS, "IssueDate", income.issued_date.isoformat())
    if income.due_date:
        _sub(invoice, CBC_NS, "DueDate", income.due_date.isoformat())
    _sub(invoice, CBC_NS, "InvoiceTypeCode", "380")
    if income.note:
        _sub(invoice, CBC_NS, "Note", income.note)
    _sub(invoice, CBC_NS, "DocumentCurrencyCode", currency)

    _party(invoice, "AccountingSupplierParty", enterprise.name, enterprise.pib, enterprise.address)
    customer_name = client.name if client else income.client_name
    customer_pib = client.pib if client else None
    customer_address = client.address if client else None
    _party(invoice, "AccountingCustomerParty", customer_name, customer_pib, customer_address)

    tax_total = _sub(invoice, CAC_NS, "TaxTotal")
    _sub(tax_total, CBC_NS, "TaxAmount", "0.00", currencyID=currency)
    tax_subtotal = _sub(tax_total, CAC_NS, "TaxSubtotal")
    _sub(tax_subtotal, CBC_NS, "TaxableAmount", _money(line_total), currencyID=currency)
    _sub(tax_subtotal, CBC_NS, "TaxAmount", "0.00", currencyID=currency)
    tax_category = _sub(tax_subtotal, CAC_NS, "TaxCategory")
    _sub(tax_category, CBC_NS, "ID", NON_VAT_CATEGORY)
    _sub(tax_category, CBC_NS, "Percent", "0.00")
    _sub(tax_category, CBC_NS, "TaxExemptionReason", NON_VAT_EXEMPTION_REASON)
    tax_scheme = _sub(tax_category, CAC_NS, "TaxScheme")
    _sub(tax_scheme, CBC_NS, "ID", "VAT")

    monetary_total = _sub(invoice, CAC_NS, "LegalMonetaryTotal")
    _sub(monetary_total, CBC_NS, "LineExtensionAmount", _money(line_total), currencyID=currency)
    _sub(monetary_total, CBC_NS, "TaxExclusiveAmount", _money(line_total), currencyID=currency)
    _sub(monetary_total, CBC_NS, "TaxInclusiveAmount", _money(payable_total), currencyID=currency)
    _sub(monetary_total, CBC_NS, "PayableAmount", _money(payable_total), currencyID=currency)

    for index, item in enumerate(items, start=1):
        line = _sub(invoice, CAC_NS, "InvoiceLine")
        _sub(line, CBC_NS, "ID", str(index))
        _sub(line, CBC_NS, "InvoicedQuantity", _quantity(item.quantity or 1), unitCode=_unit_code(item.unit))
        _sub(line, CBC_NS, "LineExtensionAmount", _money(item.total_amount), currencyID=currency)
        item_node = _sub(line, CAC_NS, "Item")
        _sub(item_node, CBC_NS, "Name", item.name)
        classified_tax = _sub(item_node, CAC_NS, "ClassifiedTaxCategory")
        _sub(classified_tax, CBC_NS, "ID", NON_VAT_CATEGORY)
        _sub(classified_tax, CBC_NS, "Percent", _money(NON_VAT_RATE))
        line_tax_scheme = _sub(classified_tax, CAC_NS, "TaxScheme")
        _sub(line_tax_scheme, CBC_NS, "ID", "VAT")
        price = _sub(line, CAC_NS, "Price")
        _sub(price, CBC_NS, "PriceAmount", _money(item.unit_price), currencyID=currency)

    return ET.tostring(invoice, encoding="utf-8", xml_declaration=True)
