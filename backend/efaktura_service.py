from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.decimal_utils import ZERO_DECIMAL
from backend.income_service import (
    has_invoice_duplicate,
    normalize_name,
    normalize_pib,
    parse_efaktura_invoice,
    to_number_year_format,
)
from backend.models import Client, EfakturaImportRecord, Enterprise, Expense, Income, Project
from backend.state_machine import initialize_expense_status, initialize_income_status

EFAKTURA_IMPORT_SOURCE = "efaktura_import"
DEFAULT_EFAKTURA_API_BASE_URL = "https://efaktura.mfin.gov.rs"
DEFAULT_EFAKTURA_INCOMING_LIST_PATH = "/api/publicApi/purchase-invoice/ids?dateFrom={from}&dateTo={to}"
DEFAULT_EFAKTURA_INCOMING_DOCUMENT_PATH = "/api/publicApi/purchase-invoice/xml?invoiceId={id}"
DEFAULT_EFAKTURA_OUTGOING_LIST_PATH = "/api/publicApi/sales-invoice/ids?dateFrom={from}&dateTo={to}"
DEFAULT_EFAKTURA_OUTGOING_DOCUMENT_PATH = "/api/publicApi/sales-invoice/xml?invoiceId={id}"


async def get_efaktura_enterprise(db: AsyncSession) -> Enterprise | None:
    result = await db.execute(select(Enterprise).order_by(Enterprise.id.asc()).limit(1))
    return result.scalar_one_or_none()


async def get_unassigned_project_id(db: AsyncSession) -> int | None:
    result = await db.execute(select(Project).where(Project.code == "INT-UNASSIGNED"))
    project = result.scalar_one_or_none()
    return project.id if project else None


def get_effective_efaktura_setting(value: str | None, default: str) -> str:
    normalized = (value or "").strip()
    return normalized or default


def enterprise_matches_party(enterprise: Enterprise | None, party_name: str | None, party_pib: str | None) -> bool:
    if enterprise is None:
        return False
    enterprise_pib = normalize_pib(enterprise.pib)
    enterprise_name = normalize_name(enterprise.name)
    party_pib_normalized = normalize_pib(party_pib)
    party_name_normalized = normalize_name(party_name)
    if enterprise_pib and party_pib_normalized and enterprise_pib == party_pib_normalized:
        return True
    if enterprise_name and party_name_normalized and enterprise_name == party_name_normalized:
        return True
    return False


def build_efaktura_expense_identity(
    invoice_number: str,
    invoice_year: int,
    supplier_pib: str | None,
    supplier_name: str | None,
) -> str:
    supplier_key = normalize_pib(supplier_pib) or normalize_name(supplier_name) or "unknown"
    normalized_invoice_number = to_number_year_format(invoice_number, invoice_year)
    return f"eFaktura-in|{normalized_invoice_number}|{supplier_key}"


def build_efaktura_expense_note(
    invoice_number: str,
    invoice_year: int,
    supplier_name: str | None,
    supplier_pib: str | None,
    file_name: str,
) -> str:
    identity = build_efaktura_expense_identity(invoice_number, invoice_year, supplier_pib, supplier_name)
    display_supplier = supplier_name or "Unknown supplier"
    display_pib = normalize_pib(supplier_pib) or "n/a"
    return f"[{identity}] Import eFaktura: {display_supplier}; PIB {display_pib}; file {file_name}"


async def has_efaktura_expense_duplicate(
    db: AsyncSession,
    invoice_number: str,
    invoice_year: int,
    supplier_pib: str | None,
    supplier_name: str | None,
    issued_date: date,
    amount: Decimal,
) -> bool:
    identity = build_efaktura_expense_identity(invoice_number, invoice_year, supplier_pib, supplier_name)
    result = await db.execute(
        select(Expense.note).where(
            Expense.source == EFAKTURA_IMPORT_SOURCE,
            Expense.date == issued_date,
            Expense.amount == amount,
        )
    )
    for (note,) in result.fetchall():
        if isinstance(note, str) and note.startswith(f"[{identity}]"):
            return True
    return False


def build_document_key(parsed: dict[str, Any], direction: str) -> str:
    invoice_year = parsed["issued_date"].year
    invoice_number = to_number_year_format(parsed["invoice_number"], invoice_year)
    amount = Decimal(str(parsed["amount_rsd"]))
    if direction == "incoming":
        counterparty_key = normalize_pib(parsed.get("supplier_pib")) or normalize_name(parsed.get("supplier_name")) or "unknown"
    else:
        counterparty_key = normalize_pib(parsed.get("customer_pib")) or normalize_name(parsed.get("customer_name")) or "unknown"
    return f"{direction}|{invoice_number}|{parsed['issued_date'].isoformat()}|{amount}|{counterparty_key}"


async def has_import_record(db: AsyncSession, document_key: str) -> bool:
    result = await db.execute(
        select(EfakturaImportRecord.id).where(EfakturaImportRecord.document_key == document_key).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def register_import_record(
    db: AsyncSession,
    *,
    document_key: str,
    external_id: str | None,
    direction: str,
    parsed: dict[str, Any],
    imported_as: str,
    imported_record_id: int,
    source: str,
    file_name: str | None,
) -> None:
    record = EfakturaImportRecord(
        document_key=document_key,
        external_id=external_id,
        direction=direction,
        invoice_number=to_number_year_format(parsed["invoice_number"], parsed["issued_date"].year),
        issued_date=parsed["issued_date"],
        amount_rsd=parsed["amount_rsd"],
        supplier_name=parsed.get("supplier_name"),
        supplier_pib=parsed.get("supplier_pib"),
        customer_name=parsed.get("customer_name"),
        customer_pib=parsed.get("customer_pib"),
        imported_as=imported_as,
        imported_record_id=imported_record_id,
        source=source,
        file_name=file_name,
    )
    db.add(record)


async def import_efaktura_documents(
    db: AsyncSession,
    *,
    user_id: int,
    documents: list[dict[str, Any]],
    source: str,
) -> dict[str, Any]:
    clients_result = await db.execute(select(Client))
    clients = clients_result.scalars().all()
    clients_by_pib: dict[str, Client] = {}
    clients_by_name: dict[str, Client] = {}
    for client in clients:
        pib_key = normalize_pib(client.pib)
        if pib_key and pib_key not in clients_by_pib:
            clients_by_pib[pib_key] = client
        name_key = normalize_name(client.name)
        if name_key and name_key not in clients_by_name:
            clients_by_name[name_key] = client

    enterprise = await get_efaktura_enterprise(db)
    has_enterprise_identity = bool(
        enterprise and (normalize_pib(enterprise.pib) or normalize_name(enterprise.name))
    )
    unassigned_project_id = await get_unassigned_project_id(db)

    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    created_income_count = 0
    created_expense_count = 0

    for document in documents:
        file_name = document.get("file_name") or "unknown.xml"
        external_id = document.get("external_id")
        direction_hint = document.get("direction_hint")
        content = document.get("content")

        if not content:
            errors.append({"file_name": file_name, "error": "Empty XML content"})
            continue

        try:
            parsed = parse_efaktura_invoice(content, file_name)
        except ValueError as exc:
            errors.append({"file_name": file_name, "error": str(exc)})
            continue

        invoice_year = parsed["issued_date"].year
        normalized_invoice_number = to_number_year_format(parsed["invoice_number"], invoice_year)
        if direction_hint in {"incoming", "outgoing"}:
            direction = direction_hint
        else:
            supplier_is_enterprise = enterprise_matches_party(enterprise, parsed.get("supplier_name"), parsed.get("supplier_pib"))
            customer_is_enterprise = enterprise_matches_party(enterprise, parsed.get("customer_name"), parsed.get("customer_pib"))
            if customer_is_enterprise and not supplier_is_enterprise:
                direction = "incoming"
            elif supplier_is_enterprise and not customer_is_enterprise:
                direction = "outgoing"
            elif has_enterprise_identity:
                errors.append({
                    "file_name": file_name,
                    "error": "Could not determine whether this eFaktura is incoming or outgoing for configured enterprise",
                })
                continue
            else:
                direction = "outgoing"

        document_key = build_document_key(parsed, direction)
        if await has_import_record(db, document_key):
            skipped.append({
                "file_name": file_name,
                "invoice_number": normalized_invoice_number,
                "reason": "Document already imported",
            })
            continue

        matched_client = None
        if parsed.get("customer_pib"):
            matched_client = clients_by_pib.get(parsed["customer_pib"])
        if matched_client is None and parsed.get("client_name"):
            matched_client = clients_by_name.get(normalize_name(parsed["client_name"]))

        try:
            async with db.begin_nested():
                if direction == "incoming":
                    if await has_efaktura_expense_duplicate(
                        db,
                        normalized_invoice_number,
                        invoice_year,
                        parsed.get("supplier_pib"),
                        parsed.get("supplier_name"),
                        parsed["issued_date"],
                        parsed["amount_rsd"],
                    ):
                        skipped.append({
                            "file_name": file_name,
                            "invoice_number": normalized_invoice_number,
                            "reason": "Incoming eFaktura already exists in expenses",
                        })
                        continue

                    expense = Expense(
                        date=parsed["issued_date"],
                        description=parsed["description"],
                        amount=parsed["amount_rsd"],
                        currency=parsed["currency"],
                        category=None,
                        paid_date=None,
                        is_tax_related=False,
                        source=EFAKTURA_IMPORT_SOURCE,
                        project_id=unassigned_project_id,
                        note=build_efaktura_expense_note(
                            normalized_invoice_number,
                            invoice_year,
                            parsed.get("supplier_name"),
                            parsed.get("supplier_pib"),
                            file_name,
                        ),
                        created_by=user_id,
                    )
                    initialize_expense_status(expense, "planned")
                    db.add(expense)
                    await db.flush()
                    await register_import_record(
                        db,
                        document_key=document_key,
                        external_id=external_id,
                        direction=direction,
                        parsed=parsed,
                        imported_as="expense",
                        imported_record_id=expense.id,
                        source=source,
                        file_name=file_name,
                    )
                    created.append({
                        "file_name": file_name,
                        "document_type": "expense",
                        "expense_id": expense.id,
                        "invoice_number": normalized_invoice_number,
                        "counterparty_name": parsed.get("supplier_name"),
                    })
                    created_expense_count += 1
                    continue

                if await has_invoice_duplicate(db, normalized_invoice_number, invoice_year):
                    skipped.append({
                        "file_name": file_name,
                        "invoice_number": normalized_invoice_number,
                        "reason": "Invoice already exists in income",
                    })
                    continue

                income = Income(
                    issued_date=parsed["issued_date"],
                    invoice_number=normalized_invoice_number,
                    invoice_year=invoice_year,
                    client_id=matched_client.id if matched_client else None,
                    client_name=matched_client.name if matched_client else parsed["client_name"],
                    description=parsed["description"],
                    amount_rsd=parsed["amount_rsd"],
                    currency=parsed["currency"],
                    exchange_rate=1.0,
                    due_date=parsed["due_date"],
                    project_id=unassigned_project_id,
                    note=f"Import eFaktura: {file_name}",
                    created_by=user_id,
                )
                initialize_income_status(income, "issued", paid_amount=ZERO_DECIMAL)
                db.add(income)
                await db.flush()
                await register_import_record(
                    db,
                    document_key=document_key,
                    external_id=external_id,
                    direction=direction,
                    parsed=parsed,
                    imported_as="income",
                    imported_record_id=income.id,
                    source=source,
                    file_name=file_name,
                )
                created.append({
                    "file_name": file_name,
                    "document_type": "income",
                    "income_id": income.id,
                    "invoice_number": income.invoice_number,
                    "counterparty_name": income.client_name,
                })
                created_income_count += 1
        except Exception as exc:
            errors.append({
                "file_name": file_name,
                "invoice_number": normalized_invoice_number,
                "error": str(exc),
            })

    await db.commit()

    return {
        "created_count": len(created),
        "created_income_count": created_income_count,
        "created_expense_count": created_expense_count,
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "created": created,
        "skipped": skipped,
        "errors": errors,
    }


def _format_url(base_url: str | None, template: str | None, **values: Any) -> str | None:
    if not template:
        return None
    replacements = {key: quote(str(value), safe="") for key, value in values.items()}
    formatted = template.format(**replacements)
    if formatted.startswith("http://") or formatted.startswith("https://"):
        return formatted
    base = (base_url or "").strip()
    if not base:
        return None
    return urljoin(base.rstrip("/") + "/", formatted.lstrip("/"))


def _http_request(url: str, *, method: str, header_name: str, header_value: str) -> tuple[bytes, str]:
    request = Request(url, method=method, headers={
        "Accept": "application/json, application/xml, text/xml;q=0.9, */*;q=0.8",
        header_name: header_value,
    })
    with urlopen(request, timeout=60) as response:
        return response.read(), response.headers.get("Content-Type", "")


def _extract_ids(payload: Any) -> list[str]:
    if payload is None:
        return []
    if isinstance(payload, list):
        output: list[str] = []
        for item in payload:
            if isinstance(item, (str, int)):
                output.append(str(item))
            elif isinstance(item, dict):
                for key in ("id", "documentId", "invoiceId", "invoice_id", "uid"):
                    if item.get(key) not in (None, ""):
                        output.append(str(item[key]))
                        break
        return output
    if isinstance(payload, dict):
        lowered_keys = {str(key).lower(): key for key in payload.keys()}
        for key in ("salesinvoiceids", "purchaseinvoiceids", "invoiceids"):
            actual_key = lowered_keys.get(key)
            if actual_key is not None:
                return _extract_ids(payload[actual_key])
        for key in ("items", "data", "result", "documents", "invoices"):
            actual_key = lowered_keys.get(key)
            if actual_key is not None:
                return _extract_ids(payload[actual_key])
    return []


def _extract_xml_bytes(raw: bytes, content_type: str) -> bytes:
    if "xml" in content_type.lower():
        return raw
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return raw
    if isinstance(payload, dict):
        for key in ("xml", "content", "documentXml", "document"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.encode("utf-8")
    return raw


async def sync_efaktura_documents(db: AsyncSession, *, user_id: int) -> dict[str, Any]:
    enterprise = await get_efaktura_enterprise(db)
    if not enterprise or not enterprise.efaktura_enabled:
        raise ValueError("eFaktura sync is disabled in settings")
    if not enterprise.efaktura_api_key:
        raise ValueError("eFaktura API key is not configured")

    base_url = get_effective_efaktura_setting(enterprise.efaktura_api_base_url, DEFAULT_EFAKTURA_API_BASE_URL)
    incoming_list_path = get_effective_efaktura_setting(enterprise.efaktura_incoming_list_path, DEFAULT_EFAKTURA_INCOMING_LIST_PATH)
    incoming_document_path = get_effective_efaktura_setting(enterprise.efaktura_incoming_document_path, DEFAULT_EFAKTURA_INCOMING_DOCUMENT_PATH)
    outgoing_list_path = get_effective_efaktura_setting(enterprise.efaktura_outgoing_list_path, DEFAULT_EFAKTURA_OUTGOING_LIST_PATH)
    outgoing_document_path = get_effective_efaktura_setting(enterprise.efaktura_outgoing_document_path, DEFAULT_EFAKTURA_OUTGOING_DOCUMENT_PATH)

    header_name = (enterprise.efaktura_api_key_header or "ApiKey").strip() or "ApiKey"
    header_prefix = enterprise.efaktura_api_key_prefix or ""
    header_value = f"{header_prefix}{enterprise.efaktura_api_key}"
    lookback_days = max(1, int(enterprise.efaktura_sync_lookback_days or 30))
    date_to = date.today()
    date_from = date_to - timedelta(days=lookback_days)

    documents: list[dict[str, Any]] = []

    async def fetch_direction(direction: str, list_path: str, document_path: str) -> None:
        list_url = _format_url(
            base_url,
            list_path,
            from_=date_from.isoformat(),
            to=date_to.isoformat(),
            **{"from": date_from.isoformat()},
        )
        if not list_url:
            return
        raw_ids, _ = await asyncio.to_thread(
            _http_request,
            list_url,
            method="POST",
            header_name=header_name,
            header_value=header_value,
        )
        try:
            ids_payload = json.loads(raw_ids.decode("utf-8"))
        except Exception:
            ids_payload = None
        ids = _extract_ids(ids_payload)
        for external_id in ids:
            xml_url = _format_url(
                base_url,
                document_path,
                id=external_id,
                external_id=external_id,
            )
            if not xml_url:
                continue
            raw_xml, content_type = await asyncio.to_thread(
                _http_request,
                xml_url,
                method="GET",
                header_name=header_name,
                header_value=header_value,
            )
            documents.append({
                "file_name": f"{direction}-{external_id}.xml",
                "content": _extract_xml_bytes(raw_xml, content_type),
                "external_id": external_id,
                "direction_hint": direction,
            })

    if enterprise.efaktura_sync_incoming:
        await fetch_direction("incoming", incoming_list_path, incoming_document_path)
    if enterprise.efaktura_sync_outgoing:
        await fetch_direction("outgoing", outgoing_list_path, outgoing_document_path)

    result = await import_efaktura_documents(db, user_id=user_id, documents=documents, source="api")
    result["fetched_count"] = len(documents)
    return result
