import unittest
from datetime import date
from decimal import Decimal
from xml.etree import ElementTree as ET

from backend.invoice_export_service import (
    CAC_NS,
    CBC_NS,
    SERBIAN_CIUS_CUSTOMIZATION_ID,
    UBL_INVOICE_NS,
    build_income_efaktura_xml,
)
from backend.models import Client, Enterprise, Income, IncomeItem
from backend.income_service import parse_efaktura_invoice
from backend.routers.income_router import _is_legacy_full_invoice_item, _normalize_income_items
from backend.schemas import IncomeItemCreate
from backend.scripts.backfill_income_items_from_efaktura import canonical_invoice_number


NS = {
    "inv": UBL_INVOICE_NS,
    "cbc": CBC_NS,
    "cac": CAC_NS,
}


class IncomeInvoiceItemsTest(unittest.TestCase):
    def test_normalize_items_forces_non_vat(self):
        items, total = _normalize_income_items(
            [
                IncomeItemCreate(
                    name="Service",
                    quantity=Decimal("2"),
                    unit_price=Decimal("500"),
                    tax_category="S",
                    tax_rate=Decimal("20"),
                )
            ]
        )

        self.assertEqual(total, Decimal("1000"))
        self.assertEqual(items[0]["tax_category"], "O")
        self.assertEqual(items[0]["tax_rate"], Decimal("0"))

    def test_efaktura_xml_uses_serbian_non_vat_profile(self):
        enterprise = Enterprise(name="Seller", pib="123456789", address="Seller address")
        client = Client(name="Buyer", pib="987654321", address="Buyer address")
        income = Income(
            issued_date=date(2026, 6, 26),
            invoice_number="0001-2026",
            client_name="Buyer",
            amount_rsd=Decimal("1200"),
            currency="RSD",
        )
        income.items = [
            IncomeItem(
                line_no=1,
                name="Service",
                quantity=Decimal("1"),
                unit="kom",
                unit_price=Decimal("1200"),
                total_amount=Decimal("1200"),
                tax_category="S",
                tax_rate=Decimal("20"),
            )
        ]

        root = ET.fromstring(build_income_efaktura_xml(income, enterprise, client))

        self.assertEqual(root.findtext("cbc:CustomizationID", namespaces=NS), SERBIAN_CIUS_CUSTOMIZATION_ID)
        self.assertIsNone(root.find("cbc:ProfileID", namespaces=NS))
        self.assertEqual(root.findtext("cbc:InvoiceTypeCode", namespaces=NS), "380")
        self.assertEqual(root.findtext("cac:TaxTotal/cbc:TaxAmount", namespaces=NS), "0.00")
        self.assertIsNone(root.find(".//cbc:TaxExemptionReasonCode", namespaces=NS))
        self.assertEqual(root.findtext(".//cac:ClassifiedTaxCategory/cbc:ID", namespaces=NS), "O")
        self.assertEqual(root.findtext(".//cac:ClassifiedTaxCategory/cbc:Percent", namespaces=NS), "0.00")

    def test_parse_efaktura_invoice_extracts_line_prices(self):
        xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:ID>0023-2026</cbc:ID>
  <cbc:IssueDate>2026-06-22</cbc:IssueDate>
  <cbc:DueDate>2026-07-13</cbc:DueDate>
  <cbc:DocumentCurrencyCode>RSD</cbc:DocumentCurrencyCode>
  <cac:AccountingSupplierParty>
    <cac:Party><cac:PartyLegalEntity><cbc:RegistrationName>Seller</cbc:RegistrationName></cac:PartyLegalEntity></cac:Party>
  </cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty>
    <cac:Party><cac:PartyLegalEntity><cbc:RegistrationName>Buyer</cbc:RegistrationName></cac:PartyLegalEntity></cac:Party>
  </cac:AccountingCustomerParty>
  <cac:InvoiceLine>
    <cbc:ID>1</cbc:ID>
    <cbc:InvoicedQuantity unitCode="H87">2</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="RSD">2400.00</cbc:LineExtensionAmount>
    <cac:Item>
      <cbc:Name>Izlazak na teren - lokal</cbc:Name>
      <cac:ClassifiedTaxCategory><cbc:ID>SS</cbc:ID><cbc:Percent>0</cbc:Percent></cac:ClassifiedTaxCategory>
    </cac:Item>
    <cac:Price><cbc:PriceAmount currencyID="RSD">1200.00</cbc:PriceAmount></cac:Price>
  </cac:InvoiceLine>
  <cac:InvoiceLine>
    <cbc:ID>2</cbc:ID>
    <cbc:InvoicedQuantity unitCode="H87">1</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="RSD">1170.00</cbc:LineExtensionAmount>
    <cac:Item><cbc:Name>Defektaza kvara</cbc:Name></cac:Item>
    <cac:Price><cbc:PriceAmount currencyID="RSD">1170.00</cbc:PriceAmount></cac:Price>
  </cac:InvoiceLine>
  <cac:LegalMonetaryTotal><cbc:PayableAmount currencyID="RSD">3570.00</cbc:PayableAmount></cac:LegalMonetaryTotal>
</Invoice>
"""

        parsed = parse_efaktura_invoice(xml, "sample.xml")

        self.assertEqual(parsed["amount_rsd"], Decimal("3570.00"))
        self.assertEqual(len(parsed["items"]), 2)
        self.assertEqual(parsed["items"][0]["name"], "Izlazak na teren - lokal")
        self.assertEqual(parsed["items"][0]["quantity"], Decimal("2"))
        self.assertEqual(parsed["items"][0]["unit"], "kom")
        self.assertEqual(parsed["items"][0]["unit_price"], Decimal("1200.00"))
        self.assertEqual(parsed["items"][0]["total_amount"], Decimal("2400.00"))

    def test_backfill_canonical_invoice_number_keeps_suffix(self):
        self.assertEqual(canonical_invoice_number("0012-2026-A"), "12-2026-A")
        self.assertEqual(canonical_invoice_number("12-2026-A"), "12-2026-A")
        self.assertEqual(canonical_invoice_number("0012-2026-A2"), "12-2026-A2")
        self.assertEqual(canonical_invoice_number("2026-0012-A2"), "12-2026-A2")

    def test_detects_legacy_full_invoice_item(self):
        income = Income(
            issued_date=date(2026, 6, 26),
            invoice_number="0023-2026",
            description="Izlazak na teren - lokal; Defektaza kvara",
            amount_rsd=Decimal("9070"),
        )
        item = IncomeItem(
            name="Izlazak na teren - lokal; Defektaza kvara",
            quantity=Decimal("1"),
            unit_price=Decimal("9070"),
            total_amount=Decimal("9070"),
        )
        real_item = IncomeItem(
            name="Izlazak na teren - lokal",
            quantity=Decimal("2"),
            unit_price=Decimal("1200"),
            total_amount=Decimal("2400"),
        )

        self.assertTrue(_is_legacy_full_invoice_item(item, income))
        self.assertFalse(_is_legacy_full_invoice_item(real_item, income))


if __name__ == "__main__":
    unittest.main()
