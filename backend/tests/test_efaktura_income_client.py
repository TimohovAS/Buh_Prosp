from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.efaktura_service import import_efaktura_documents
from backend.models import Client, Income
from backend.routers.income_router import _income_response


def _outgoing_invoice_xml(*, invoice_number: str, customer_name: str, customer_pib: str) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:ID>{invoice_number}</cbc:ID>
  <cbc:IssueDate>2026-09-21</cbc:IssueDate>
  <cbc:DocumentCurrencyCode>RSD</cbc:DocumentCurrencyCode>
  <cac:AccountingSupplierParty>
    <cac:Party><cac:PartyLegalEntity><cbc:RegistrationName>ProspEl</cbc:RegistrationName></cac:PartyLegalEntity></cac:Party>
  </cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty>
    <cac:Party>
      <cac:PartyName><cbc:Name>{customer_name}</cbc:Name></cac:PartyName>
      <cac:PartyTaxScheme><cbc:CompanyID>RS{customer_pib}</cbc:CompanyID></cac:PartyTaxScheme>
    </cac:Party>
  </cac:AccountingCustomerParty>
  <cac:LegalMonetaryTotal><cbc:PayableAmount currencyID="RSD">38245.00</cbc:PayableAmount></cac:LegalMonetaryTotal>
</Invoice>""".encode()


async def test_outgoing_efaktura_links_existing_client_by_pib_and_uses_directory_name(db_session):
    client = Client(name="Retail Park Four D.O.O. Beograd", pib="123456789")
    db_session.add(client)
    await db_session.flush()

    result = await import_efaktura_documents(
        db_session,
        user_id=1,
        documents=[
            {
                "file_name": "0041-2026.xml",
                "direction_hint": "outgoing",
                "content": _outgoing_invoice_xml(
                    invoice_number="0041-2026",
                    customer_name="AB KANON TEHNOBIRO DOO VRŠAC",
                    customer_pib="123456789",
                ),
            }
        ],
        source="upload",
    )

    assert result["created_income_count"] == 1
    assert result["created"][0]["counterparty_name"] == client.name
    income = await db_session.scalar(
        select(Income)
        .options(selectinload(Income.client), selectinload(Income.items))
        .where(Income.invoice_number == "0041-2026")
    )
    assert income.client_id == client.id
    assert _income_response(income).client_name == client.name
    assert len((await db_session.scalars(select(Client))).all()) == 1


async def test_outgoing_efaktura_creates_client_when_no_exact_match_exists(db_session):
    result = await import_efaktura_documents(
        db_session,
        user_id=1,
        documents=[
            {
                "file_name": "0042-2026.xml",
                "direction_hint": "outgoing",
                "content": _outgoing_invoice_xml(
                    invoice_number="0042-2026",
                    customer_name="New Customer DOO",
                    customer_pib="987654321",
                ),
            }
        ],
        source="upload",
    )

    assert result["created_income_count"] == 1
    client = await db_session.scalar(select(Client).where(Client.pib == "987654321"))
    income = await db_session.scalar(select(Income).where(Income.invoice_number == "0042-2026"))
    assert client is not None
    assert client.name == "New Customer DOO"
    assert income.client_id == client.id
    assert "client_name" not in Income.__table__.c
