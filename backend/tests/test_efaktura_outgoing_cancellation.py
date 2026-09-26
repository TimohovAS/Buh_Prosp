import json
from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import select

from backend import efaktura_service
from backend.efaktura_service import import_efaktura_documents, sync_efaktura_documents
from backend.models import EfakturaImportRecord, Enterprise, Income
from backend.schemas import EfakturaSyncResponse


ISSUED_DATE = date.today() - timedelta(days=7)
INVOICE_NUMBER = f"0041-{ISSUED_DATE.year}"
EXTERNAL_ID = "sef-0041"


def _outgoing_xml() -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:ID>{INVOICE_NUMBER}</cbc:ID>
  <cbc:IssueDate>{ISSUED_DATE.isoformat()}</cbc:IssueDate>
  <cbc:DocumentCurrencyCode>RSD</cbc:DocumentCurrencyCode>
  <cac:AccountingSupplierParty>
    <cac:Party><cac:PartyLegalEntity><cbc:RegistrationName>ProspEl</cbc:RegistrationName></cac:PartyLegalEntity></cac:Party>
  </cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty>
    <cac:Party>
      <cac:PartyName><cbc:Name>Retail Park Four D.O.O. Beograd</cbc:Name></cac:PartyName>
      <cac:PartyTaxScheme><cbc:CompanyID>RS123456789</cbc:CompanyID></cac:PartyTaxScheme>
    </cac:Party>
  </cac:AccountingCustomerParty>
  <cac:LegalMonetaryTotal><cbc:PayableAmount currencyID="RSD">38245.00</cbc:PayableAmount></cac:LegalMonetaryTotal>
</Invoice>""".encode()


async def _make_existing_income(db_session, make_client, make_income, *, amount="38245", paid_amount="0"):
    client = await make_client(db_session, name="Retail Park Four D.O.O. Beograd", pib="123456789")
    return await make_income(
        db_session,
        amount=Decimal(amount),
        paid_amount=Decimal(paid_amount),
        issued_date=ISSUED_DATE,
        invoice_number=INVOICE_NUMBER,
        client_id=client.id,
    )


def _mock_sef(monkeypatch, *, list_fails=False, changes=True, storno_list=False):
    def fake_http(url, **kwargs):
        if "/sales-invoice/changes?" in url:
            # Changes are available even if a cancelled invoice is absent from the ID list.
            payload = [{"SalesInvoiceId": EXTERNAL_ID, "NewInvoiceStatus": "Storno"}] if changes else []
            return json.dumps(payload).encode(), "application/json"
        if "/sales-invoice/ids?" in url:
            if list_fails:
                raise RuntimeError("SEF list unavailable")
            status = parse_qs(urlsplit(url).query).get("status", [None])[0]
            if status == "Storno" and storno_list:
                return json.dumps({"SalesInvoiceIds": [EXTERNAL_ID]}).encode(), "application/json"
            return b"[]", "application/json"
        if "/sales-invoice/xml?" in url:
            return _outgoing_xml(), "application/xml"
        raise AssertionError(f"Unexpected mocked SEF request: {url}, {kwargs}")

    monkeypatch.setattr(efaktura_service, "_http_request", fake_http)


async def _enable_sync(db_session):
    db_session.add(
        Enterprise(
            name="ProspEl",
            efaktura_enabled=True,
            efaktura_api_key="test-key",
            efaktura_sync_incoming=False,
            efaktura_sync_outgoing=True,
            efaktura_sync_lookback_days=10,
        )
    )
    await db_session.flush()


async def test_cancelled_sef_invoice_links_existing_income_and_cancels_it(
    db_session, make_client, make_income, monkeypatch
):
    income = await _make_existing_income(db_session, make_client, make_income)
    await _enable_sync(db_session)
    _mock_sef(monkeypatch)

    result = await sync_efaktura_documents(db_session, user_id=1)

    await db_session.refresh(income)
    record = await db_session.scalar(select(EfakturaImportRecord).where(EfakturaImportRecord.external_id == EXTERNAL_ID))
    assert income.status == "cancelled"
    assert record is not None and record.imported_record_id == income.id
    assert result["cancelled_count"] == 1
    assert result["warning_count"] == 0
    assert EfakturaSyncResponse.model_validate(result).cancelled[0].invoice_number == INVOICE_NUMBER

    repeated = await sync_efaktura_documents(db_session, user_id=1)
    assert repeated["cancelled_count"] == 0
    assert repeated["warning_count"] == 0


@pytest.mark.parametrize(
    ("amount", "paid_amount", "expected_reason"),
    [
        ("40000", "0", "different amount"),
        ("38245", "100", "has payments"),
    ],
)
async def test_cancelled_sef_invoice_warns_when_automatic_cancellation_is_unsafe(
    db_session, make_client, make_income, monkeypatch, amount, paid_amount, expected_reason
):
    income = await _make_existing_income(
        db_session, make_client, make_income, amount=amount, paid_amount=paid_amount
    )
    await _enable_sync(db_session)
    _mock_sef(monkeypatch)

    result = await sync_efaktura_documents(db_session, user_id=1)

    await db_session.refresh(income)
    assert income.status == "issued"
    assert result["cancelled_count"] == 0
    assert result["warning_count"] == 1
    assert expected_reason in result["warnings"][0]["reason"]
    assert EfakturaSyncResponse.model_validate(result).warnings[0].invoice_number == INVOICE_NUMBER


async def test_api_duplicate_links_external_id_for_future_status_changes(db_session, make_client, make_income):
    income = await _make_existing_income(db_session, make_client, make_income)

    result = await import_efaktura_documents(
        db_session,
        user_id=1,
        documents=[
            {
                "file_name": "outgoing-sef-0041.xml",
                "direction_hint": "outgoing",
                "external_id": EXTERNAL_ID,
                "content": _outgoing_xml(),
            }
        ],
        source="api",
    )

    record = await db_session.scalar(select(EfakturaImportRecord).where(EfakturaImportRecord.external_id == EXTERNAL_ID))
    assert result["created_count"] == 0
    assert result["skipped_count"] == 1
    assert result["warning_count"] == 0
    assert record is not None and record.imported_record_id == income.id
    assert len((await db_session.scalars(select(Income))).all()) == 1


async def test_status_change_is_applied_even_when_invoice_list_fails(db_session, make_client, make_income, monkeypatch):
    income = await _make_existing_income(db_session, make_client, make_income)
    await _enable_sync(db_session)
    _mock_sef(monkeypatch, list_fails=True)

    result = await sync_efaktura_documents(db_session, user_id=1)

    await db_session.refresh(income)
    assert income.status == "cancelled"
    assert result["cancelled_count"] == 1
    assert result["warning_count"] >= 1
    assert any("Could not list outgoing" in item["reason"] for item in result["warnings"])


async def test_storno_status_list_catches_same_day_cancellation(db_session, make_client, make_income, monkeypatch):
    income = await _make_existing_income(db_session, make_client, make_income)
    await _enable_sync(db_session)
    _mock_sef(monkeypatch, changes=False, storno_list=True)

    result = await sync_efaktura_documents(db_session, user_id=1)

    await db_session.refresh(income)
    assert income.status == "cancelled"
    assert result["cancelled_count"] == 1
    assert result["warning_count"] == 0
