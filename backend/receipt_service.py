import asyncio
import hashlib
import html
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from http.cookiejar import CookieJar
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.decimal_utils import MONEY_PLACES, ZERO_DECIMAL, money_eq, to_decimal
from backend.models import (
    BankTransaction,
    CashEntry,
    Contract,
    Expense,
    IncomingInvoice,
    MonthlyObligation,
    PlannedExpensePayment,
    Project,
    PurchaseReceipt,
    PurchaseReceiptItem,
    TransactionCategory,
)
from backend.state_machine import initialize_expense_status

RECEIPT_STATUS_NEW = "new"
RECEIPT_STATUS_LINKED = "linked_expense"
RECEIPT_STATUS_WAITING_BANK = "waiting_bank"
RECEIPT_STATUS_MATCHED_BANK = "matched_bank"
RECEIPT_STATUS_CASH_EXPENSE = "cash_expense"

PAYMENT_KIND_CASH = "cash"
PAYMENT_KIND_CASHLESS = "cashless"
PAYMENT_KIND_UNKNOWN = "unknown"


class ReceiptImportError(ValueError):
    pass


@dataclass
class ImportedReceiptPayload:
    verification_url: str
    qr_hash: str
    invoice_number: str | None
    token: str | None
    seller_name: str | None
    seller_tax_id: str | None
    seller_address: str | None
    seller_city: str | None
    receipt_datetime: datetime | None
    payment_type: str | None
    payment_kind: str
    total_amount: Decimal
    currency: str
    is_valid: bool
    raw_html: str
    raw_specifications_json: str
    raw_recapitulation_json: str | None
    items: list[dict]


def _normalize_receipt_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise ReceiptImportError("Receipt QR URL is required")
    parsed = urlsplit(raw)
    if (parsed.netloc or "").lower() != "suf.purs.gov.rs":
        raise ReceiptImportError("Only official SUF receipt URLs are supported")
    if not parsed.path.startswith("/v"):
        raise ReceiptImportError("Unsupported receipt URL")
    return urlunsplit((parsed.scheme or "https", parsed.netloc, parsed.path, parsed.query, ""))


def _hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _strip_tags(value: str | None) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_view_model_value(page_html: str, field_name: str) -> str | None:
    patterns = [
        rf"viewModel\.{re.escape(field_name)}\('([^']*)'\)",
        rf'viewModel\.{re.escape(field_name)}\("([^"]*)"\)',
    ]
    for pattern in patterns:
        match = re.search(pattern, page_html, re.IGNORECASE)
        if match:
            return html.unescape(match.group(1).strip())
    return None


def _extract_label_value(page_html: str, element_id: str) -> str | None:
    match = re.search(
        rf'id="{re.escape(element_id)}"[^>]*>(.*?)</',
        page_html,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    value = _strip_tags(match.group(1))
    return value or None


def _parse_decimal(value: object) -> Decimal:
    if value is None:
        return ZERO_DECIMAL
    if isinstance(value, Decimal):
        return value.quantize(MONEY_PLACES)
    if isinstance(value, (int, float)):
        return to_decimal(value).quantize(MONEY_PLACES)
    text = str(value).strip()
    if not text:
        return ZERO_DECIMAL
    normalized = text.replace("\u00A0", " ").replace(" ", "").replace(".", "").replace(",", ".")
    normalized = re.sub(r"[^0-9.\-]", "", normalized)
    if normalized in {"", "-", ".", "-."}:
        return ZERO_DECIMAL
    return to_decimal(normalized).quantize(MONEY_PLACES)


def _parse_receipt_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    for fmt in ("%d.%m.%Y. %H:%M:%S", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y. %H:%M", "%d.%m.%Y %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _extract_payment_type(page_html: str) -> str | None:
    for element_id in ("transactionTypeLabel", "transactionTypeId", "paymentTypeLabel"):
        value = _extract_label_value(page_html, element_id)
        if value:
            return value
    return _extract_view_model_value(page_html, "TransactionType")


def _detect_payment_kind(payment_type: str | None) -> str:
    normalized = (payment_type or "").strip().lower()
    if not normalized:
        return PAYMENT_KIND_UNKNOWN
    if any(token in normalized for token in ("gotovina", "cash", "готов")):
        return PAYMENT_KIND_CASH
    if any(token in normalized for token in ("kartic", "card", "bezgot", "račun", "racun", "prenos")):
        return PAYMENT_KIND_CASHLESS
    return PAYMENT_KIND_UNKNOWN


def _load_json_from_response(opener, request: Request) -> dict:
    with opener.open(request, timeout=20) as response:
        payload = response.read().decode("utf-8", "ignore")
    return json.loads(payload)


def _download_receipt_payload_sync(verification_url: str) -> ImportedReceiptPayload:
    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))
    page_request = Request(
        verification_url,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": "ProspEl/2.1",
        },
    )
    with opener.open(page_request, timeout=20) as response:
        page_html = response.read().decode("utf-8", "ignore")

    invoice_number = _extract_view_model_value(page_html, "InvoiceNumber")
    token = _extract_view_model_value(page_html, "Token")
    if not invoice_number or not token:
        raise ReceiptImportError("Could not extract receipt verification token")

    form_payload = urlencode({"invoiceNumber": invoice_number, "token": token}).encode("utf-8")
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "User-Agent": "ProspEl/2.1",
        "X-Requested-With": "XMLHttpRequest",
    }
    specs_request = Request("https://suf.purs.gov.rs/specifications", data=form_payload, headers=headers, method="POST")
    specs_payload = _load_json_from_response(opener, specs_request)
    if not specs_payload.get("success"):
        raise ReceiptImportError("SUF did not return receipt specification")

    recapitulation_payload = None
    recap_request = Request("https://suf.purs.gov.rs/recapitulation", data=form_payload, headers=headers, method="POST")
    try:
        recapitulation_payload = _load_json_from_response(opener, recap_request)
    except Exception:
        recapitulation_payload = None

    items: list[dict] = []
    for index, item in enumerate(specs_payload.get("items") or [], start=1):
        items.append(
            {
                "line_no": index,
                "gtin": (item.get("gtin") or "").strip() or None,
                "name": (item.get("name") or "").strip() or f"Item #{index}",
                "quantity": _parse_decimal(item.get("quantity")),
                "unit_price": _parse_decimal(item.get("unitPrice")),
                "total_amount": _parse_decimal(item.get("total")),
                "label": (item.get("label") or "").strip() or None,
                "label_rate": float(item.get("labelRate")) if item.get("labelRate") is not None else None,
                "tax_base_amount": _parse_decimal(item.get("taxBaseAmount")),
                "vat_amount": _parse_decimal(item.get("vatAmount")),
                "raw_json": json.dumps(item, ensure_ascii=False),
            }
        )

    return ImportedReceiptPayload(
        verification_url=verification_url,
        qr_hash=_hash_value(verification_url),
        invoice_number=invoice_number,
        token=token,
        seller_name=_extract_label_value(page_html, "shopFullNameLabel"),
        seller_tax_id=_extract_label_value(page_html, "tinLabel"),
        seller_address=_extract_label_value(page_html, "addressLabel"),
        seller_city=_extract_label_value(page_html, "cityLabel"),
        receipt_datetime=_parse_receipt_datetime(_extract_label_value(page_html, "sdcDateTimeLabel")),
        payment_type=_extract_payment_type(page_html),
        payment_kind=_detect_payment_kind(_extract_payment_type(page_html)),
        total_amount=_parse_decimal(_extract_label_value(page_html, "totalAmountLabel")),
        currency="RSD",
        is_valid=True,
        raw_html=page_html,
        raw_specifications_json=json.dumps(specs_payload, ensure_ascii=False),
        raw_recapitulation_json=json.dumps(recapitulation_payload, ensure_ascii=False) if recapitulation_payload is not None else None,
        items=items,
    )


async def _get_unassigned_project_id(db: AsyncSession) -> int | None:
    result = await db.execute(select(Project).where(Project.code == "INT-UNASSIGNED"))
    project = result.scalar_one_or_none()
    return project.id if project else None


async def _get_project_or_error(db: AsyncSession, project_id: int | None) -> Project | None:
    if project_id is None:
        return None
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise ReceiptImportError("Project not found")
    if project.status == "archived":
        raise ReceiptImportError("Cannot use archived project")
    return project


async def _get_contract_or_error(db: AsyncSession, contract_id: int | None) -> Contract | None:
    if contract_id is None:
        return None
    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()
    if not contract:
        raise ReceiptImportError("Contract not found")
    return contract


async def _get_category_or_none(db: AsyncSession, category_id: int | None) -> TransactionCategory | None:
    if category_id is None:
        return None
    result = await db.execute(select(TransactionCategory).where(TransactionCategory.id == category_id))
    return result.scalar_one_or_none()


async def _resolve_category_links(
    db: AsyncSession,
    category_id: int | None,
    project_id: int | None,
    contract_id: int | None,
) -> tuple[int | None, int | None, bool]:
    category = await _get_category_or_none(db, category_id)
    if not category:
        return project_id, contract_id, False

    resolved_project_id = category.default_project_id or project_id
    resolved_contract_id = contract_id
    is_tax_related = category.category_group == "tax"

    if category.default_project_id and resolved_contract_id is not None:
        contract = await _get_contract_or_error(db, resolved_contract_id)
        if contract and contract.project_id is not None and contract.project_id != category.default_project_id:
            resolved_contract_id = None

    return resolved_project_id, resolved_contract_id, is_tax_related


async def _resolve_expense_links(
    db: AsyncSession,
    project_id: int | None,
    contract_id: int | None,
) -> tuple[int | None, int | None]:
    resolved_project_id = project_id or await _get_unassigned_project_id(db)
    resolved_contract_id = contract_id

    if resolved_contract_id is not None:
        contract = await _get_contract_or_error(db, resolved_contract_id)
        if contract and contract.project_id is None:
            if resolved_project_id is None:
                raise ReceiptImportError("Select a project before linking this contract")
            await _get_project_or_error(db, resolved_project_id)
            contract.project_id = resolved_project_id
            await db.flush()
        if contract:
            resolved_project_id = contract.project_id

    if resolved_project_id is not None:
        await _get_project_or_error(db, resolved_project_id)

    return resolved_project_id, resolved_contract_id


def _build_receipt_expense_description(receipt: PurchaseReceipt) -> str:
    item_names = [item.name for item in (receipt.items or [])[:3] if getattr(item, "name", None)]
    head = "; ".join(item_names)
    parts = [part for part in [head, receipt.seller_name] if part]
    description = " | ".join(parts).strip()
    return (description or receipt.invoice_number or "Receipt expense")[:500]


async def _get_receipt_by_id(db: AsyncSession, receipt_id: int) -> PurchaseReceipt | None:
    result = await db.execute(
        select(PurchaseReceipt)
        .options(
            selectinload(PurchaseReceipt.project),
            selectinload(PurchaseReceipt.expense),
            selectinload(PurchaseReceipt.items),
        )
        .where(PurchaseReceipt.id == receipt_id)
    )
    return result.scalar_one_or_none()


async def get_receipt_or_error(db: AsyncSession, receipt_id: int) -> PurchaseReceipt:
    receipt = await _get_receipt_by_id(db, receipt_id)
    if not receipt:
        raise ReceiptImportError("Receipt not found")
    return receipt


async def _get_receipt_by_expense_id(db: AsyncSession, expense_id: int) -> PurchaseReceipt | None:
    result = await db.execute(
        select(PurchaseReceipt)
        .options(
            selectinload(PurchaseReceipt.project),
            selectinload(PurchaseReceipt.expense),
            selectinload(PurchaseReceipt.items),
        )
        .where(PurchaseReceipt.expense_id == expense_id)
    )
    return result.scalar_one_or_none()


async def _get_matched_bank_transaction_for_expense(db: AsyncSession, expense_id: int) -> BankTransaction | None:
    result = await db.execute(
        select(BankTransaction)
        .where(
            BankTransaction.matched_type == "expense",
            BankTransaction.matched_id == expense_id,
            BankTransaction.status == "matched",
        )
        .order_by(BankTransaction.id.desc())
    )
    return result.scalar_one_or_none()


async def _get_any_bank_transaction_for_expense(db: AsyncSession, expense_id: int) -> BankTransaction | None:
    result = await db.execute(
        select(BankTransaction)
        .where(
            BankTransaction.matched_type == "expense",
            BankTransaction.matched_id == expense_id,
        )
        .order_by(BankTransaction.id.desc())
    )
    return result.scalar_one_or_none()


async def _ensure_receipt_generated_expense_can_delete(db: AsyncSession, expense: Expense) -> None:
    if getattr(expense, "reversal_of_id", None) or getattr(expense, "reversed_expense_id", None):
        raise ReceiptImportError("Reversed expenses cannot be deleted together with the receipt")

    invoice_result = await db.execute(select(IncomingInvoice.id).where(IncomingInvoice.expense_id == expense.id).limit(1))
    if invoice_result.scalar_one_or_none():
        raise ReceiptImportError("This receipt expense is linked to an incoming invoice")

    obligation_result = await db.execute(select(MonthlyObligation.id).where(MonthlyObligation.expense_id == expense.id).limit(1))
    if obligation_result.scalar_one_or_none():
        raise ReceiptImportError("This receipt expense is linked to a tax or obligation payment")

    planned_payment_result = await db.execute(
        select(func.count()).select_from(PlannedExpensePayment).where(PlannedExpensePayment.expense_id == expense.id)
    )
    if int(planned_payment_result.scalar() or 0) > 0:
        raise ReceiptImportError("This receipt expense is linked to recurring expense payments")

    bank_tx = await _get_any_bank_transaction_for_expense(db, expense.id)
    if bank_tx:
        raise ReceiptImportError("Unmatch the bank transaction first")


async def _get_cash_entry_by_id(db: AsyncSession, cash_entry_id: int) -> CashEntry | None:
    result = await db.execute(select(CashEntry).where(CashEntry.id == cash_entry_id))
    return result.scalar_one_or_none()


async def _sync_receipt_status_for_expense(db: AsyncSession, receipt: PurchaseReceipt, expense: Expense | None = None) -> None:
    linked_expense = expense
    if linked_expense is None and receipt.expense_id:
        expense_result = await db.execute(select(Expense).where(Expense.id == receipt.expense_id))
        linked_expense = expense_result.scalar_one_or_none()

    if linked_expense is None:
        receipt.expense_id = None
        receipt.bank_transaction_id = None
        receipt.cash_entry_id = None
        receipt.status = RECEIPT_STATUS_NEW
        return

    if receipt.project_id is None and linked_expense.project_id is not None:
        receipt.project_id = linked_expense.project_id

    if linked_expense.source == "cash":
        if receipt.cash_entry_id is None:
            cash_result = await db.execute(select(CashEntry).where(CashEntry.expense_id == linked_expense.id))
            cash_entry = cash_result.scalar_one_or_none()
            receipt.cash_entry_id = cash_entry.id if cash_entry else None
        receipt.bank_transaction_id = None
        receipt.status = RECEIPT_STATUS_CASH_EXPENSE
        return

    bank_tx = await _get_matched_bank_transaction_for_expense(db, linked_expense.id)
    if bank_tx:
        receipt.bank_transaction_id = bank_tx.id
        receipt.status = RECEIPT_STATUS_MATCHED_BANK
        return

    receipt.bank_transaction_id = None
    receipt.cash_entry_id = None
    receipt.status = RECEIPT_STATUS_WAITING_BANK if linked_expense.status == "planned" else RECEIPT_STATUS_LINKED


async def sync_receipt_for_expense_match(db: AsyncSession, expense: Expense, tx: BankTransaction) -> None:
    receipt = await _get_receipt_by_expense_id(db, expense.id)
    if not receipt:
        return
    receipt.bank_transaction_id = tx.id
    receipt.status = RECEIPT_STATUS_MATCHED_BANK
    if receipt.project_id is None and expense.project_id is not None:
        receipt.project_id = expense.project_id
    await db.flush()


async def sync_receipt_for_expense_unmatch(db: AsyncSession, expense: Expense) -> None:
    receipt = await _get_receipt_by_expense_id(db, expense.id)
    if not receipt:
        return
    await _sync_receipt_status_for_expense(db, receipt, expense)
    await db.flush()


async def import_receipt_from_qr(
    db: AsyncSession,
    verification_url: str,
    *,
    current_user_id: int | None = None,
) -> tuple[PurchaseReceipt, bool]:
    normalized_url = _normalize_receipt_url(verification_url)
    qr_hash = _hash_value(normalized_url)
    existing_result = await db.execute(
        select(PurchaseReceipt)
        .options(selectinload(PurchaseReceipt.project), selectinload(PurchaseReceipt.expense), selectinload(PurchaseReceipt.items))
        .where(PurchaseReceipt.qr_hash == qr_hash)
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        return existing, False

    payload = await asyncio.to_thread(_download_receipt_payload_sync, normalized_url)
    receipt = PurchaseReceipt(
        verification_url=payload.verification_url,
        qr_hash=payload.qr_hash,
        invoice_number=payload.invoice_number,
        token=payload.token,
        seller_name=payload.seller_name,
        seller_tax_id=payload.seller_tax_id,
        seller_address=payload.seller_address,
        seller_city=payload.seller_city,
        receipt_datetime=payload.receipt_datetime,
        payment_type=payload.payment_type,
        payment_kind=payload.payment_kind,
        total_amount=payload.total_amount,
        currency=payload.currency,
        is_valid=payload.is_valid,
        status=RECEIPT_STATUS_NEW,
        raw_html=payload.raw_html,
        raw_specifications_json=payload.raw_specifications_json,
        raw_recapitulation_json=payload.raw_recapitulation_json,
        created_by=current_user_id,
    )
    db.add(receipt)
    await db.flush()

    for item in payload.items:
        db.add(
            PurchaseReceiptItem(
                receipt_id=receipt.id,
                line_no=item["line_no"],
                gtin=item["gtin"],
                name=item["name"],
                quantity=item["quantity"],
                unit_price=item["unit_price"],
                total_amount=item["total_amount"],
                label=item["label"],
                label_rate=item["label_rate"],
                tax_base_amount=item["tax_base_amount"],
                vat_amount=item["vat_amount"],
                raw_json=item["raw_json"],
            )
        )

    await db.flush()
    return await get_receipt_or_error(db, receipt.id), True


def _match_text_score(receipt: PurchaseReceipt, expense: Expense) -> int:
    seller = (receipt.seller_name or "").lower()
    description = (expense.description or "").lower()
    if not seller or not description:
        return 0
    words = [word for word in re.split(r"\W+", seller) if len(word) >= 3][:4]
    hits = sum(1 for word in words if word in description)
    if hits >= 2:
        return 25
    if hits == 1:
        return 10
    return 0


async def get_receipt_expense_candidates(
    db: AsyncSession,
    receipt_id: int,
) -> list[dict]:
    receipt = await get_receipt_or_error(db, receipt_id)
    other_linked_result = await db.execute(
        select(PurchaseReceipt.expense_id).where(
            PurchaseReceipt.id != receipt.id,
            PurchaseReceipt.expense_id.is_not(None),
        )
    )
    occupied_expense_ids = {int(expense_id) for (expense_id,) in other_linked_result.fetchall() if expense_id is not None}
    receipt_date = receipt.receipt_datetime.date() if receipt.receipt_datetime else None

    query = (
        select(Expense)
        .options(selectinload(Expense.project), selectinload(Expense.contract))
        .where(
            Expense.reversal_of_id.is_(None),
            Expense.source != "cash_transfer",
            Expense.status.in_(["planned", "paid"]),
        )
        .order_by(Expense.date.desc(), Expense.id.desc())
    )
    result = await db.execute(query)
    items = list(result.scalars().all())
    candidates: list[tuple[tuple[int, int, int], dict]] = []
    for expense in items:
        if not receipt.expense_id and expense.id in occupied_expense_ids:
            continue
        if receipt.expense_id and expense.id != receipt.expense_id and expense.id in occupied_expense_ids:
            continue
        if not money_eq(expense.amount or ZERO_DECIMAL, receipt.total_amount or ZERO_DECIMAL):
            continue
        date_diff = abs((expense.date - receipt_date).days) if receipt_date else 9999
        if receipt_date and date_diff > 31:
            continue
        score = 60
        if date_diff <= 1:
            score += 25
        elif date_diff <= 7:
            score += 15
        elif date_diff <= 14:
            score += 10
        score += _match_text_score(receipt, expense)
        candidates.append(
            (
                (100 - score, date_diff, expense.id),
                {
                    "id": expense.id,
                    "date": expense.date,
                    "description": expense.description,
                    "amount": to_decimal(expense.amount or ZERO_DECIMAL),
                    "currency": expense.currency or "RSD",
                    "status": expense.status,
                    "source": expense.source,
                    "category_id": expense.category_id,
                    "project_id": expense.project_id,
                    "project_name": getattr(expense.project, "name", None),
                    "project_code": getattr(expense.project, "code", None),
                    "contract_id": expense.contract_id,
                    "contract_number": getattr(expense.contract, "number", None),
                    "bank_reference": expense.bank_reference,
                    "score": score,
                },
            )
        )
    candidates.sort(key=lambda item: item[0])
    return [item for _, item in candidates]


async def assign_receipt_project(
    db: AsyncSession,
    receipt_id: int,
    project_id: int | None,
) -> PurchaseReceipt:
    receipt = await get_receipt_or_error(db, receipt_id)
    resolved_project_id = project_id if project_id is not None else await _get_unassigned_project_id(db)
    if resolved_project_id is not None:
        await _get_project_or_error(db, resolved_project_id)
    receipt.project_id = resolved_project_id
    if receipt.expense_id:
        expense_result = await db.execute(select(Expense).where(Expense.id == receipt.expense_id))
        expense = expense_result.scalar_one_or_none()
        if expense and expense.source in {"receipt", "cash"}:
            expense.project_id = resolved_project_id
    await db.flush()
    return receipt


async def link_receipt_to_expense(
    db: AsyncSession,
    receipt_id: int,
    expense_id: int,
) -> PurchaseReceipt:
    receipt = await get_receipt_or_error(db, receipt_id)
    expense_result = await db.execute(select(Expense).where(Expense.id == expense_id))
    expense = expense_result.scalar_one_or_none()
    if not expense:
        raise ReceiptImportError("Expense not found")

    other_result = await db.execute(
        select(PurchaseReceipt).where(
            PurchaseReceipt.expense_id == expense.id,
            PurchaseReceipt.id != receipt.id,
        )
    )
    if other_result.scalar_one_or_none():
        raise ReceiptImportError("This expense is already linked to another receipt")

    receipt.expense_id = expense.id
    if receipt.project_id is None and expense.project_id is not None:
        receipt.project_id = expense.project_id
    if receipt.category_id is None and expense.category_id is not None:
        receipt.category_id = expense.category_id
    await _sync_receipt_status_for_expense(db, receipt, expense)
    await db.flush()
    return receipt


async def unlink_receipt_expense(
    db: AsyncSession,
    receipt_id: int,
) -> PurchaseReceipt:
    receipt = await get_receipt_or_error(db, receipt_id)
    if not receipt.expense_id:
        return receipt

    expense_result = await db.execute(select(Expense).where(Expense.id == receipt.expense_id))
    expense = expense_result.scalar_one_or_none()
    if expense and expense.source == "receipt" and expense.status == "planned":
        if await _get_matched_bank_transaction_for_expense(db, expense.id):
            raise ReceiptImportError("Unmatch the bank transaction first")
        await db.delete(expense)
    elif expense and expense.source == "cash":
        raise ReceiptImportError("Cash receipt expenses must be managed from the cash register")

    receipt.expense_id = None
    receipt.bank_transaction_id = None
    receipt.cash_entry_id = None
    receipt.status = RECEIPT_STATUS_NEW
    await db.flush()
    return receipt


async def delete_receipt(
    db: AsyncSession,
    receipt_id: int,
) -> None:
    receipt = await get_receipt_or_error(db, receipt_id)

    expense = None
    if receipt.expense_id:
        expense_result = await db.execute(select(Expense).where(Expense.id == receipt.expense_id))
        expense = expense_result.scalar_one_or_none()

    if receipt.bank_transaction_id:
        raise ReceiptImportError("Unmatch the bank transaction first")

    cash_entry = None
    if receipt.cash_entry_id:
        cash_entry = await _get_cash_entry_by_id(db, receipt.cash_entry_id)

    delete_expense = None
    delete_cash_entry = None

    if expense:
        if expense.source == "receipt":
            await _ensure_receipt_generated_expense_can_delete(db, expense)
            delete_expense = expense
        elif expense.source == "cash":
            await _ensure_receipt_generated_expense_can_delete(db, expense)
            if not cash_entry:
                raise ReceiptImportError("This receipt is linked to a cash expense; remove the cash entry first")
            delete_cash_entry = cash_entry
            delete_expense = expense

    if expense is not None and delete_expense is None:
        receipt.expense_id = None
    receipt.bank_transaction_id = None
    receipt.cash_entry_id = None
    await db.flush()

    await db.delete(receipt)
    if delete_cash_entry is not None:
        await db.delete(delete_cash_entry)
    if delete_expense is not None:
        await db.delete(delete_expense)
    await db.flush()


async def create_expense_from_receipt(
    db: AsyncSession,
    receipt_id: int,
    *,
    category_id: int | None = None,
    project_id: int | None = None,
    contract_id: int | None = None,
    description: str | None = None,
    note: str | None = None,
    payment_mode: str = "auto",
    current_user_id: int | None = None,
) -> PurchaseReceipt:
    receipt = await get_receipt_or_error(db, receipt_id)
    if receipt.expense_id:
        raise ReceiptImportError("Receipt is already linked to an expense")
    if payment_mode not in {"auto", "bank", "cash"}:
        raise ReceiptImportError("Unsupported payment mode")

    resolved_payment_mode = payment_mode
    if resolved_payment_mode == "auto":
        resolved_payment_mode = "cash" if receipt.payment_kind == PAYMENT_KIND_CASH else "bank"

    resolved_project_id = project_id if project_id is not None else receipt.project_id
    resolved_category_id = category_id if category_id is not None else receipt.category_id
    resolved_project_id, resolved_contract_id, is_tax_related = await _resolve_category_links(
        db,
        resolved_category_id,
        resolved_project_id,
        contract_id,
    )
    resolved_project_id, resolved_contract_id = await _resolve_expense_links(
        db,
        resolved_project_id,
        resolved_contract_id,
    )

    category_name = None
    if resolved_category_id is not None:
        category = await _get_category_or_none(db, resolved_category_id)
        category_name = category.name_ru if category else None

    expense_date = receipt.receipt_datetime.date() if receipt.receipt_datetime else date.today()
    expense = Expense(
        date=expense_date,
        description=(description or _build_receipt_expense_description(receipt)).strip()[:500],
        amount=to_decimal(receipt.total_amount or ZERO_DECIMAL),
        currency=receipt.currency or "RSD",
        category=category_name,
        category_id=resolved_category_id,
        contract_id=resolved_contract_id,
        is_tax_related=is_tax_related,
        note=note or None,
        project_id=resolved_project_id,
        source="cash" if resolved_payment_mode == "cash" else "receipt",
        created_by=current_user_id,
    )
    if resolved_payment_mode == "cash":
        initialize_expense_status(expense, "paid", paid_date=expense_date)
    else:
        initialize_expense_status(expense, "planned")
    db.add(expense)
    await db.flush()

    if resolved_payment_mode == "cash":
        cash_entry = CashEntry(
            date=expense_date,
            direction="out",
            amount=expense.amount,
            currency=expense.currency,
            description=expense.description[:500],
            entry_type="expense",
            note=expense.note,
            expense_id=expense.id,
            created_by=current_user_id,
        )
        db.add(cash_entry)
        await db.flush()
        receipt.cash_entry_id = cash_entry.id

    receipt.expense_id = expense.id
    receipt.project_id = resolved_project_id
    receipt.category_id = resolved_category_id
    await _sync_receipt_status_for_expense(db, receipt, expense)
    await db.flush()
    return receipt


async def list_receipts(
    db: AsyncSession,
    *,
    status: str | None = None,
    project_id: int | None = None,
    search: str | None = None,
) -> list[PurchaseReceipt]:
    query = (
        select(PurchaseReceipt)
        .options(
            selectinload(PurchaseReceipt.project),
            selectinload(PurchaseReceipt.expense),
            selectinload(PurchaseReceipt.items),
        )
        .order_by(PurchaseReceipt.receipt_datetime.desc(), PurchaseReceipt.id.desc())
    )
    if status:
        query = query.where(PurchaseReceipt.status == status)
    if project_id is not None:
        query = query.where(PurchaseReceipt.project_id == project_id)
    if search:
        needle = f"%{search.strip()}%"
        query = query.where(
            or_(
                PurchaseReceipt.seller_name.ilike(needle),
                PurchaseReceipt.invoice_number.ilike(needle),
                PurchaseReceipt.seller_tax_id.ilike(needle),
            )
        )
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_project_receipt_purchases(
    db: AsyncSession,
    *,
    project_id: int,
    from_date: date,
    to_date: date,
) -> dict:
    project = await _get_project_or_error(db, project_id)
    query = (
        select(PurchaseReceiptItem, PurchaseReceipt, Expense)
        .join(PurchaseReceipt, PurchaseReceipt.id == PurchaseReceiptItem.receipt_id)
        .outerjoin(Expense, Expense.id == PurchaseReceipt.expense_id)
        .where(
            PurchaseReceipt.project_id == project_id,
            PurchaseReceipt.receipt_datetime.is_not(None),
            PurchaseReceipt.receipt_datetime >= datetime.combine(from_date, datetime.min.time()),
            PurchaseReceipt.receipt_datetime <= datetime.combine(to_date, datetime.max.time()),
        )
        .order_by(PurchaseReceipt.receipt_datetime.desc(), PurchaseReceipt.id.desc(), PurchaseReceiptItem.line_no.asc())
    )
    result = await db.execute(query)
    items: list[dict] = []
    for item, receipt, expense in result.fetchall():
        items.append(
            {
                "receipt_id": receipt.id,
                "receipt_datetime": receipt.receipt_datetime,
                "seller_name": receipt.seller_name,
                "invoice_number": receipt.invoice_number,
                "payment_kind": receipt.payment_kind or PAYMENT_KIND_UNKNOWN,
                "expense_id": receipt.expense_id,
                "expense_status": getattr(expense, "status", None),
                "item_id": item.id,
                "item_name": item.name,
                "quantity": to_decimal(item.quantity or ZERO_DECIMAL),
                "unit_price": to_decimal(item.unit_price or ZERO_DECIMAL),
                "total_amount": to_decimal(item.total_amount or ZERO_DECIMAL),
            }
        )
    return {
        "project_id": project_id,
        "project_name": project.name if project else None,
        "from_date": from_date,
        "to_date": to_date,
        "items": items,
    }
