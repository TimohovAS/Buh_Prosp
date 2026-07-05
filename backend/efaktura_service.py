from __future__ import annotations

import asyncio
import base64
import json
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db_utils import get_unassigned_project_id
from backend.decimal_utils import ZERO_DECIMAL, to_decimal
from backend.income_service import (
    has_invoice_duplicate,
    invoice_identity,
    normalize_name,
    normalize_pib,
    parse_efaktura_invoice,
    to_number_year_format,
)
from backend.incoming_invoice_service import INCOMING_INVOICE_SOURCE, create_incoming_invoice
from backend.models import Client, EfakturaImportRecord, Enterprise, Expense, Income, IncomeItem, IncomingInvoice
from backend.state_machine import (
    cancel_income,
    cancel_incoming_invoice,
    initialize_income_status,
    initialize_incoming_invoice_status,
    reconcile_incoming_invoice_status,
)

EFAKTURA_IMPORT_SOURCE = "efaktura_import"
DEFAULT_EFAKTURA_API_BASE_URL = "https://efaktura.mfin.gov.rs"
DEFAULT_EFAKTURA_INCOMING_LIST_PATH = "/api/publicApi/purchase-invoice/ids?dateFrom={from}&dateTo={to}"
DEFAULT_EFAKTURA_INCOMING_DOCUMENT_PATH = "/api/publicApi/purchase-invoice/xml?invoiceId={id}"
DEFAULT_EFAKTURA_OUTGOING_LIST_PATH = "/api/publicApi/sales-invoice/ids?dateFrom={from}&dateTo={to}"
DEFAULT_EFAKTURA_OUTGOING_DOCUMENT_PATH = "/api/publicApi/sales-invoice/xml?invoiceId={id}"
DEFAULT_EFAKTURA_OUTGOING_DETAILS_PATH = "/api/publicApi/sales-invoice?invoiceId={id}"
DEFAULT_EFAKTURA_OUTGOING_CHANGES_PATH = "/api/publicApi/sales-invoice/changes?date={date}"

EFAKTURA_CANCELLED_STATUS_MARKERS = (
    "storn",
    "cancel",
    "annul",
    "mistake",
    "void",
    "reversed",
    "gres",
    "greš",
    "отмен",
    "ошиб",
    "сторн",
)


async def get_efaktura_enterprise(db: AsyncSession) -> Enterprise | None:
    result = await db.execute(select(Enterprise).order_by(Enterprise.id.asc()).limit(1))
    return result.scalar_one_or_none()


def build_client_lookup(clients: list[Client]) -> tuple[dict[str, Client], dict[str, Client]]:
    clients_by_pib: dict[str, Client] = {}
    clients_by_name: dict[str, Client] = {}
    for client in clients:
        pib_key = normalize_pib(client.pib)
        if pib_key and pib_key not in clients_by_pib:
            clients_by_pib[pib_key] = client
        name_key = normalize_name(client.name)
        if name_key and name_key not in clients_by_name:
            clients_by_name[name_key] = client
    return clients_by_pib, clients_by_name


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
    """Дубликат по стабильному префиксу в Expense.note (identity eFaktura).

    Основная защита от повторного импорта того же XML — ``has_import_record(document_key)``
    (см. вызов до ветки incoming); она авторитетна для сценария «документ уже в журнале импорта».

    Дополнительно проверяем расходы с source ``efaktura_import`` (legacy) и связанные с
    входящей фактурой расходы ``incoming_invoice``, у которых note начинается с ``[{identity}]``
    (как при create_incoming_invoice + build_efaktura_expense_note).
    """
    identity = build_efaktura_expense_identity(invoice_number, invoice_year, supplier_pib, supplier_name)
    prefix = f"[{identity}]"
    result = await db.execute(
        select(Expense.note).where(
            Expense.date == issued_date,
            Expense.amount == amount,
            Expense.source.in_([EFAKTURA_IMPORT_SOURCE, INCOMING_INVOICE_SOURCE]),
        )
    )
    for (note,) in result.fetchall():
        if isinstance(note, str) and note.startswith(prefix):
            return True
    return False


def build_document_key(parsed: dict[str, Any], direction: str) -> str:
    invoice_year = parsed["issued_date"].year
    invoice_number = to_number_year_format(parsed["invoice_number"], invoice_year)
    amount = Decimal(str(parsed["amount_rsd"]))
    if direction == "incoming":
        counterparty_key = (
            normalize_pib(parsed.get("supplier_pib")) or normalize_name(parsed.get("supplier_name")) or "unknown"
        )
    else:
        counterparty_key = (
            normalize_pib(parsed.get("customer_pib")) or normalize_name(parsed.get("customer_name")) or "unknown"
        )
    return f"{direction}|{invoice_number}|{parsed['issued_date'].isoformat()}|{amount}|{counterparty_key}"


async def get_import_record_by_key(db: AsyncSession, document_key: str) -> EfakturaImportRecord | None:
    result = await db.execute(
        select(EfakturaImportRecord).where(EfakturaImportRecord.document_key == document_key).limit(1)
    )
    return result.scalar_one_or_none()


async def get_income_by_invoice_identity(db: AsyncSession, invoice_number: str, invoice_year: int) -> Income | None:
    target_year, target_key = invoice_identity(invoice_number, invoice_year)
    result = await db.execute(
        select(Income.id, Income.invoice_number, Income.invoice_year, Income.issued_date).where(
            or_(
                Income.invoice_year == invoice_year,
                Income.issued_date.between(date(invoice_year, 1, 1), date(invoice_year, 12, 31)),
            )
        )
    )
    for income_id, existing_number, existing_year, issued_date in result.fetchall():
        year_val = int(existing_year) if existing_year is not None else (issued_date.year if issued_date else None)
        existing_year_key, existing_key = invoice_identity(existing_number, year_val)
        if existing_year_key == target_year and existing_key == target_key:
            return await db.get(Income, income_id)
    return None


def _document_status_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        parts: list[str] = []
        for key, item in value.items():
            key_text = str(key).lower()
            if "status" in key_text or key_text in {"state", "documentstate"}:
                parts.append(_document_status_text(item))
        return " ".join(part for part in parts if part)
    if isinstance(value, list):
        return " ".join(_document_status_text(item) for item in value)
    return str(value)


def is_efaktura_cancelled_status(value: Any) -> bool:
    text = _document_status_text(value).casefold()
    return bool(text) and any(marker in text for marker in EFAKTURA_CANCELLED_STATUS_MARKERS)


async def handle_cancelled_outgoing_invoice(
    db: AsyncSession,
    *,
    invoice_number: str,
    invoice_year: int,
    status_text: str,
) -> dict[str, Any]:
    income = await get_income_by_invoice_identity(db, invoice_number, invoice_year)
    if income is None:
        return {"reason": f"Outgoing eFaktura is cancelled/storned in API ({status_text or 'unknown status'})"}
    if income.status == "cancelled":
        return {"reason": f"Outgoing eFaktura is already cancelled ({status_text or 'unknown status'})"}
    if to_decimal(getattr(income, "paid_amount", None) or ZERO_DECIMAL) > ZERO_DECIMAL or income.status == "paid":
        return {
            "reason": (
                f"Outgoing eFaktura is cancelled/storned in API ({status_text or 'unknown status'}), "
                f"but income #{income.id} has payments and was not changed"
            )
        }

    cancel_income(income)
    income.bank_reference = None
    income.note = "\n".join(
        part
        for part in [
            income.note,
            f"eFaktura API status: {status_text or 'cancelled/storned'}; income cancelled during sync.",
        ]
        if part
    )
    await db.flush()
    return {"reason": f"Outgoing eFaktura is cancelled/storned in API; income #{income.id} cancelled"}


async def handle_cancelled_outgoing_import_record(
    db: AsyncSession,
    *,
    external_id: str,
    status_text: str,
) -> dict[str, Any] | None:
    result = await db.execute(
        select(EfakturaImportRecord)
        .where(
            EfakturaImportRecord.external_id == str(external_id),
            EfakturaImportRecord.direction == "outgoing",
            EfakturaImportRecord.imported_as == "income",
        )
        .order_by(EfakturaImportRecord.id.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if record is None:
        return None

    income = await db.get(Income, record.imported_record_id)
    if income is None:
        return {
            "external_id": str(external_id),
            "invoice_number": record.invoice_number,
            "reason": f"Outgoing eFaktura import record has no linked income ({status_text or 'unknown status'})",
        }
    if income.status == "cancelled":
        return {
            "external_id": str(external_id),
            "invoice_number": income.invoice_number,
            "reason": f"Outgoing eFaktura is already cancelled ({status_text or 'unknown status'})",
        }
    if to_decimal(getattr(income, "paid_amount", None) or ZERO_DECIMAL) > ZERO_DECIMAL or income.status == "paid":
        return {
            "external_id": str(external_id),
            "invoice_number": income.invoice_number,
            "reason": (
                f"Outgoing eFaktura is cancelled/storned in API ({status_text or 'unknown status'}), "
                f"but income #{income.id} has payments and was not changed"
            ),
        }

    cancel_income(income)
    income.bank_reference = None
    status_note = f"eFaktura API status: {status_text or 'cancelled/storned'}; income cancelled during sync."
    if status_note not in (income.note or ""):
        income.note = "\n".join(part for part in [income.note, status_note] if part)
    await db.flush()
    return {
        "external_id": str(external_id),
        "invoice_number": income.invoice_number,
        "reason": f"Outgoing eFaktura is cancelled/storned in API; income #{income.id} cancelled",
    }


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
) -> EfakturaImportRecord:
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
    await db.flush()
    return record


async def migrate_legacy_efaktura_incoming_records(
    db: AsyncSession,
    *,
    user_id: int | None,
) -> dict[str, Any]:
    clients_result = await db.execute(select(Client))
    clients = clients_result.scalars().all()
    clients_by_pib, clients_by_name = build_client_lookup(clients)
    unassigned_project_id = await get_unassigned_project_id(db)

    result = await db.execute(
        select(EfakturaImportRecord)
        .where(
            EfakturaImportRecord.direction == "incoming",
            EfakturaImportRecord.imported_as == "expense",
        )
        .order_by(EfakturaImportRecord.created_at.asc(), EfakturaImportRecord.id.asc())
    )
    records = list(result.scalars().all())

    summary = {
        "found_count": 0,
        "migrated_count": 0,
        "skipped_existing_invoice_count": 0,
        "skipped_missing_expense_count": 0,
        "skipped_nonlegacy_expense_count": 0,
    }

    for record in records:
        summary["found_count"] += 1

        existing_invoice_result = await db.execute(
            select(IncomingInvoice.id)
            .where(
                or_(
                    IncomingInvoice.efaktura_record_id == record.id,
                    IncomingInvoice.expense_id == record.imported_record_id,
                )
            )
            .limit(1)
        )
        if existing_invoice_result.scalar_one_or_none() is not None:
            summary["skipped_existing_invoice_count"] += 1
            continue

        expense = await db.get(Expense, record.imported_record_id)
        if expense is None:
            summary["skipped_missing_expense_count"] += 1
            continue
        if getattr(expense, "source", None) != EFAKTURA_IMPORT_SOURCE:
            summary["skipped_nonlegacy_expense_count"] += 1
            continue

        supplier_client = None
        supplier_pib = normalize_pib(record.supplier_pib)
        if supplier_pib:
            supplier_client = clients_by_pib.get(supplier_pib)
        if supplier_client is None and record.supplier_name:
            supplier_client = clients_by_name.get(normalize_name(record.supplier_name))

        resolved_project_id = expense.project_id or unassigned_project_id
        invoice = IncomingInvoice(
            invoice_number=record.invoice_number,
            date=record.issued_date,
            client_id=supplier_client.id if supplier_client else None,
            counterparty_name=record.supplier_name or expense.description or "Unknown",
            project_id=resolved_project_id,
            amount=expense.amount,
            currency=expense.currency or "RSD",
            description=expense.description,
            note=expense.note,
            source="efaktura",
            efaktura_record_id=record.id,
            expense_id=expense.id,
            created_by=expense.created_by or user_id,
        )
        initialize_incoming_invoice_status(invoice, "unpaid")

        expense.source = INCOMING_INVOICE_SOURCE
        expense.project_id = resolved_project_id

        if getattr(expense, "status", None) == "paid":
            invoice.settled_amount = to_decimal(invoice.amount or ZERO_DECIMAL)
            reconcile_incoming_invoice_status(invoice)
        elif getattr(expense, "status", None) == "reversed":
            cancel_incoming_invoice(invoice)

        db.add(invoice)
        await db.flush()
        summary["migrated_count"] += 1

    return summary


def _safe_path_part(value: Any, fallback: str = "unknown") -> str:
    text = str(value or "").strip()
    if not text:
        text = fallback
    text = re.sub(r"[<>:\"|?*\x00-\x1f]", "_", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text[:140] or fallback


def _build_pdf_download_name(
    parsed: dict[str, Any],
    *,
    direction: str,
    external_id: str | None,
) -> str:
    issued_date = parsed["issued_date"]
    invoice_number = to_number_year_format(parsed["invoice_number"], issued_date.year)
    external_part = external_id or "no-id"
    return f"{_safe_path_part(direction)}_{issued_date.year}_{_safe_path_part(invoice_number)}_{_safe_path_part(external_part)}.pdf"


def _maybe_pdf_bytes(raw: bytes | None, content_type: str | None) -> bytes | None:
    if not raw:
        return None
    lowered = (content_type or "").lower()
    if "pdf" in lowered or raw.startswith(b"%PDF"):
        return raw
    return None


async def import_efaktura_documents(
    db: AsyncSession,
    *,
    user_id: int,
    documents: list[dict[str, Any]],
    source: str,
) -> dict[str, Any]:
    clients_result = await db.execute(select(Client))
    clients = clients_result.scalars().all()
    clients_by_pib, clients_by_name = build_client_lookup(clients)

    enterprise = await get_efaktura_enterprise(db)
    has_enterprise_identity = bool(enterprise and (normalize_pib(enterprise.pib) or normalize_name(enterprise.name)))
    unassigned_project_id = await get_unassigned_project_id(db)

    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    created_income_count = 0
    created_expense_count = 0
    download_errors: list[dict[str, Any]] = []
    pdf_downloads: list[dict[str, Any]] = []

    for document in documents:
        file_name = document.get("file_name") or "unknown.xml"
        external_id = document.get("external_id")
        direction_hint = document.get("direction_hint")
        content = document.get("content")
        pdf_content = document.get("pdf_content")
        source_status = document.get("source_status")
        source_status_text = _document_status_text(source_status)
        document_download_errors = document.get("download_errors") or []
        if document_download_errors:
            download_errors.extend(document_download_errors)

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
            supplier_is_enterprise = enterprise_matches_party(
                enterprise, parsed.get("supplier_name"), parsed.get("supplier_pib")
            )
            customer_is_enterprise = enterprise_matches_party(
                enterprise, parsed.get("customer_name"), parsed.get("customer_pib")
            )
            if customer_is_enterprise and not supplier_is_enterprise:
                direction = "incoming"
            elif supplier_is_enterprise and not customer_is_enterprise:
                direction = "outgoing"
            elif has_enterprise_identity:
                errors.append(
                    {
                        "file_name": file_name,
                        "error": "Could not determine whether this eFaktura is incoming or outgoing for configured enterprise",
                    }
                )
                continue
            else:
                direction = "outgoing"

        # Первичная дедупликация: тот же документ (ключ) уже импортирован — не создаём вторую запись.
        document_key = build_document_key(parsed, direction)
        if source == "api" and direction == "outgoing" and is_efaktura_cancelled_status(source_status):
            try:
                async with db.begin_nested():
                    cancel_result = await handle_cancelled_outgoing_invoice(
                        db,
                        invoice_number=normalized_invoice_number,
                        invoice_year=invoice_year,
                        status_text=source_status_text,
                    )
                skipped.append(
                    {
                        "file_name": file_name,
                        "invoice_number": normalized_invoice_number,
                        "reason": cancel_result["reason"],
                    }
                )
            except Exception as exc:
                errors.append(
                    {
                        "file_name": file_name,
                        "invoice_number": normalized_invoice_number,
                        "error": str(exc),
                    }
                )
            continue

        if source == "api" and pdf_content:
            pdf_downloads.append(
                {
                    "file_name": _build_pdf_download_name(parsed, direction=direction, external_id=external_id),
                    "content_type": "application/pdf",
                    "content_base64": base64.b64encode(pdf_content).decode("ascii"),
                }
            )

        existing_record = await get_import_record_by_key(db, document_key)
        if existing_record:
            skipped.append(
                {
                    "file_name": file_name,
                    "invoice_number": normalized_invoice_number,
                    "reason": "Document already imported",
                }
            )
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
                        skipped.append(
                            {
                                "file_name": file_name,
                                "invoice_number": normalized_invoice_number,
                                "reason": "Incoming eFaktura already exists in expenses",
                            }
                        )
                        continue

                    supplier_client = None
                    if parsed.get("supplier_pib"):
                        supplier_client = clients_by_pib.get(parsed["supplier_pib"])
                    if supplier_client is None and parsed.get("supplier_name"):
                        supplier_client = clients_by_name.get(normalize_name(parsed["supplier_name"]))

                    efaktura_rec = await register_import_record(
                        db,
                        document_key=document_key,
                        external_id=external_id,
                        direction=direction,
                        parsed=parsed,
                        imported_as="expense",
                        imported_record_id=0,
                        source=source,
                        file_name=file_name,
                    )

                    invoice = await create_incoming_invoice(
                        db,
                        invoice_number=normalized_invoice_number,
                        invoice_date=parsed["issued_date"],
                        client_id=supplier_client.id if supplier_client else None,
                        counterparty_name=parsed.get("supplier_name") or parsed.get("customer_name") or "Unknown",
                        project_id=unassigned_project_id,
                        amount=parsed["amount_rsd"],
                        currency=parsed["currency"],
                        description=parsed["description"],
                        note=build_efaktura_expense_note(
                            normalized_invoice_number,
                            invoice_year,
                            parsed.get("supplier_name"),
                            parsed.get("supplier_pib"),
                            file_name,
                        ),
                        source="efaktura",
                        efaktura_record_id=efaktura_rec.id if efaktura_rec else None,
                        created_by=user_id,
                    )

                    if efaktura_rec:
                        efaktura_rec.imported_record_id = invoice.expense_id or invoice.id
                    await db.flush()

                    created.append(
                        {
                            "file_name": file_name,
                            "document_type": "expense",
                            "expense_id": invoice.expense_id,
                            "invoice_number": normalized_invoice_number,
                            "counterparty_name": parsed.get("supplier_name"),
                        }
                    )
                    created_expense_count += 1
                    continue

                if await has_invoice_duplicate(db, normalized_invoice_number, invoice_year):
                    skipped.append(
                        {
                            "file_name": file_name,
                            "invoice_number": normalized_invoice_number,
                            "reason": "Invoice already exists in income",
                        }
                    )
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
                income.items = [
                    IncomeItem(
                        line_no=item.get("line_no") or index,
                        name=item["name"],
                        quantity=item.get("quantity") or Decimal("1"),
                        unit=item.get("unit") or "kom",
                        unit_price=item.get("unit_price") or ZERO_DECIMAL,
                        total_amount=item.get("total_amount") or ZERO_DECIMAL,
                        tax_category=item.get("tax_category") or "O",
                        tax_rate=item.get("tax_rate") or ZERO_DECIMAL,
                    )
                    for index, item in enumerate(parsed.get("items") or [], start=1)
                    if item.get("name")
                ]
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
                created.append(
                    {
                        "file_name": file_name,
                        "document_type": "income",
                        "income_id": income.id,
                        "invoice_number": income.invoice_number,
                        "counterparty_name": income.client_name,
                    }
                )
                created_income_count += 1
        except Exception as exc:
            errors.append(
                {
                    "file_name": file_name,
                    "invoice_number": normalized_invoice_number,
                    "error": str(exc),
                }
            )

    await db.commit()

    return {
        "created_count": len(created),
        "created_income_count": created_income_count,
        "created_expense_count": created_expense_count,
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "pdf_download_count": len(pdf_downloads),
        "download_error_count": len(download_errors),
        "created": created,
        "skipped": skipped,
        "errors": errors,
        "download_errors": download_errors,
        "pdf_downloads": pdf_downloads,
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


def _format_sync_boundary(value: date, *, end_of_day: bool) -> str:
    moment = datetime.combine(
        value,
        time(23, 59, 59) if end_of_day else time(0, 0, 0),
    )
    return moment.isoformat()


def _http_request(
    url: str,
    *,
    method: str,
    header_name: str,
    header_value: str,
    accept: str = "application/json, application/xml, text/xml;q=0.9, */*;q=0.8",
) -> tuple[bytes, str]:
    request = Request(
        url,
        method=method,
        headers={
            "Accept": accept,
            header_name: header_value,
        },
    )
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


def _case_insensitive_get(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    lowered = {str(key).lower(): key for key in payload.keys()}
    for key in keys:
        actual_key = lowered.get(key.lower())
        if actual_key is not None:
            return payload[actual_key]
    return None


def _extract_document_refs(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        output: list[dict[str, Any]] = []
        for item in payload:
            if isinstance(item, (str, int)):
                output.append({"external_id": str(item), "source_status": None})
            elif isinstance(item, dict):
                external_id = _case_insensitive_get(
                    item,
                    (
                        "id",
                        "documentId",
                        "invoiceId",
                        "invoice_id",
                        "uid",
                        "salesInvoiceId",
                        "purchaseInvoiceId",
                    ),
                )
                if external_id in (None, ""):
                    nested_refs = _extract_document_refs(item)
                    if nested_refs:
                        output.extend(nested_refs)
                    continue
                source_status = _case_insensitive_get(
                    item,
                    (
                        "status",
                        "invoiceStatus",
                        "documentStatus",
                        "salesInvoiceStatus",
                        "purchaseInvoiceStatus",
                    ),
                )
                output.append(
                    {
                        "external_id": str(external_id),
                        "source_status": source_status,
                        "source_payload": item,
                    }
                )
        return output
    if isinstance(payload, dict):
        external_id = _case_insensitive_get(
            payload,
            (
                "id",
                "documentId",
                "invoiceId",
                "invoice_id",
                "uid",
                "salesInvoiceId",
                "purchaseInvoiceId",
            ),
        )
        if external_id not in (None, ""):
            source_status = _case_insensitive_get(
                payload,
                (
                    "status",
                    "invoiceStatus",
                    "documentStatus",
                    "salesInvoiceStatus",
                    "purchaseInvoiceStatus",
                ),
            )
            return [
                {
                    "external_id": str(external_id),
                    "source_status": source_status,
                    "source_payload": payload,
                }
            ]
        lowered_keys = {str(key).lower(): key for key in payload.keys()}
        for key in ("salesinvoiceids", "purchaseinvoiceids", "invoiceids"):
            actual_key = lowered_keys.get(key)
            if actual_key is not None:
                return _extract_document_refs(payload[actual_key])
        for key in ("items", "data", "result", "documents", "invoices"):
            actual_key = lowered_keys.get(key)
            if actual_key is not None:
                refs = _extract_document_refs(payload[actual_key])
                if refs:
                    return refs
    return [{"external_id": external_id, "source_status": None} for external_id in _extract_ids(payload)]


def _extract_status_change_refs(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        output: list[dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            external_id = _case_insensitive_get(
                item,
                (
                    "salesInvoiceId",
                    "purchaseInvoiceId",
                    "invoiceId",
                    "documentId",
                    "id",
                ),
            )
            if external_id in (None, ""):
                output.extend(_extract_status_change_refs(item))
                continue
            source_status = _case_insensitive_get(
                item,
                (
                    "newInvoiceStatus",
                    "invoiceStatus",
                    "documentStatus",
                    "status",
                ),
            )
            output.append(
                {
                    "external_id": str(external_id),
                    "source_status": source_status,
                    "source_payload": item,
                }
            )
        return output
    if isinstance(payload, dict):
        lowered_keys = {str(key).lower(): key for key in payload.keys()}
        for key in ("items", "data", "result", "documents", "invoices", "changes"):
            actual_key = lowered_keys.get(key)
            if actual_key is not None:
                refs = _extract_status_change_refs(payload[actual_key])
                if refs:
                    return refs
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
    incoming_list_path = get_effective_efaktura_setting(
        enterprise.efaktura_incoming_list_path, DEFAULT_EFAKTURA_INCOMING_LIST_PATH
    )
    incoming_document_path = get_effective_efaktura_setting(
        enterprise.efaktura_incoming_document_path, DEFAULT_EFAKTURA_INCOMING_DOCUMENT_PATH
    )
    outgoing_list_path = get_effective_efaktura_setting(
        enterprise.efaktura_outgoing_list_path, DEFAULT_EFAKTURA_OUTGOING_LIST_PATH
    )
    outgoing_document_path = get_effective_efaktura_setting(
        enterprise.efaktura_outgoing_document_path, DEFAULT_EFAKTURA_OUTGOING_DOCUMENT_PATH
    )
    incoming_pdf_path = (getattr(enterprise, "efaktura_incoming_pdf_path", None) or "").strip()
    outgoing_pdf_path = (getattr(enterprise, "efaktura_outgoing_pdf_path", None) or "").strip()

    header_name = (enterprise.efaktura_api_key_header or "ApiKey").strip() or "ApiKey"
    header_prefix = enterprise.efaktura_api_key_prefix or ""
    header_value = f"{header_prefix}{enterprise.efaktura_api_key}"
    lookback_days = max(1, int(enterprise.efaktura_sync_lookback_days or 30))
    date_to = date.today()
    date_from = date_to - timedelta(days=lookback_days)
    date_from_value = _format_sync_boundary(date_from, end_of_day=False)
    date_to_value = _format_sync_boundary(date_to, end_of_day=True)

    documents: list[dict[str, Any]] = []
    outgoing_status_by_id: dict[str, Any] = {}

    async def fetch_outgoing_current_statuses(document_refs: list[dict[str, Any]]) -> dict[str, Any]:
        statuses: dict[str, Any] = {}
        for document_ref in document_refs:
            external_id = document_ref["external_id"]
            details_url = _format_url(
                base_url,
                DEFAULT_EFAKTURA_OUTGOING_DETAILS_PATH,
                id=external_id,
                external_id=external_id,
            )
            if not details_url:
                continue
            try:
                raw_details, _ = await asyncio.to_thread(
                    _http_request,
                    details_url,
                    method="GET",
                    header_name=header_name,
                    header_value=header_value,
                )
                details_payload = json.loads(raw_details.decode("utf-8"))
            except Exception:
                continue
            for details_ref in _extract_document_refs(details_payload):
                statuses[details_ref["external_id"]] = details_ref.get("source_status")
        return statuses

    async def fetch_outgoing_status_changes() -> None:
        for day_offset in range((date_to - date_from).days + 1):
            day = date_from + timedelta(days=day_offset)
            changes_url = _format_url(
                base_url,
                DEFAULT_EFAKTURA_OUTGOING_CHANGES_PATH,
                date=_format_sync_boundary(day, end_of_day=False),
            )
            if not changes_url:
                continue
            try:
                raw_changes, _ = await asyncio.to_thread(
                    _http_request,
                    changes_url,
                    method="POST",
                    header_name=header_name,
                    header_value=header_value,
                )
                changes_payload = json.loads(raw_changes.decode("utf-8"))
            except Exception:
                continue
            for change_ref in _extract_status_change_refs(changes_payload):
                outgoing_status_by_id[change_ref["external_id"]] = change_ref.get("source_status")

    async def fetch_direction(direction: str, list_path: str, document_path: str, pdf_path: str | None) -> None:
        list_url = _format_url(
            base_url,
            list_path,
            from_=date_from_value,
            to=date_to_value,
            **{"from": date_from_value},
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
        document_refs = _extract_document_refs(ids_payload)
        current_status_by_id = {}
        if direction == "outgoing":
            current_status_by_id = await fetch_outgoing_current_statuses(document_refs)
            for current_external_id, current_status in current_status_by_id.items():
                if current_status not in (None, ""):
                    outgoing_status_by_id[current_external_id] = current_status
        for document_ref in document_refs:
            external_id = document_ref["external_id"]
            source_status = document_ref.get("source_status")
            if direction == "outgoing":
                source_status = (
                    current_status_by_id.get(external_id) or outgoing_status_by_id.get(external_id) or source_status
                )
                if is_efaktura_cancelled_status(source_status):
                    continue
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
            pdf_content = None
            download_errors = []
            if bool(getattr(enterprise, "efaktura_save_pdf", False)) and pdf_path:
                pdf_url = _format_url(
                    base_url,
                    pdf_path,
                    id=external_id,
                    external_id=external_id,
                )
                if pdf_url:
                    try:
                        raw_pdf, pdf_content_type = await asyncio.to_thread(
                            _http_request,
                            pdf_url,
                            method="GET",
                            header_name=header_name,
                            header_value=header_value,
                            accept="application/pdf,*/*",
                        )
                        pdf_content = _maybe_pdf_bytes(raw_pdf, pdf_content_type)
                        if not pdf_content:
                            download_errors.append(
                                {
                                    "file_name": f"{direction}-{external_id}.pdf",
                                    "error": f"PDF endpoint did not return a PDF ({pdf_content_type or 'unknown content type'})",
                                }
                            )
                    except Exception as exc:
                        download_errors.append(
                            {
                                "file_name": f"{direction}-{external_id}.pdf",
                                "error": str(exc),
                            }
                        )
            documents.append(
                {
                    "file_name": f"{direction}-{external_id}.xml",
                    "content": _extract_xml_bytes(raw_xml, content_type),
                    "pdf_content": pdf_content,
                    "download_errors": download_errors,
                    "external_id": external_id,
                    "source_status": source_status,
                    "source_payload": document_ref.get("source_payload"),
                    "direction_hint": direction,
                }
            )

    async def apply_cancelled_outgoing_status_changes() -> list[dict[str, Any]]:
        applied: list[dict[str, Any]] = []
        for external_id, source_status in outgoing_status_by_id.items():
            if not is_efaktura_cancelled_status(source_status):
                continue
            status_text = _document_status_text(source_status)
            async with db.begin_nested():
                result_item = await handle_cancelled_outgoing_import_record(
                    db,
                    external_id=external_id,
                    status_text=status_text,
                )
            if result_item:
                applied.append(result_item)
        if applied:
            await db.commit()
        return applied

    if enterprise.efaktura_sync_incoming:
        await fetch_direction("incoming", incoming_list_path, incoming_document_path, incoming_pdf_path)
    if enterprise.efaktura_sync_outgoing:
        await fetch_outgoing_status_changes()
        await fetch_direction("outgoing", outgoing_list_path, outgoing_document_path, outgoing_pdf_path)

    result = await import_efaktura_documents(db, user_id=user_id, documents=documents, source="api")
    status_change_results = await apply_cancelled_outgoing_status_changes()
    if status_change_results:
        result["skipped"].extend(status_change_results)
        result["skipped_count"] = len(result["skipped"])
    result["fetched_count"] = len(documents)
    return result
