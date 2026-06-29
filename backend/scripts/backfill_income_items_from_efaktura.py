"""Backfill old Income.items from outgoing eFaktura XML documents."""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import selectinload

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from backend.database import AsyncSessionLocal, get_db_path
from backend.decimal_utils import ZERO_DECIMAL, decimal_sum, to_decimal
from backend.efaktura_service import (
    DEFAULT_EFAKTURA_API_BASE_URL,
    DEFAULT_EFAKTURA_OUTGOING_DOCUMENT_PATH,
    DEFAULT_EFAKTURA_OUTGOING_LIST_PATH,
    _extract_document_refs,
    _extract_xml_bytes,
    _format_url,
    _http_request,
    get_effective_efaktura_setting,
    get_efaktura_enterprise,
)
from backend.income_service import parse_efaktura_invoice, to_number_year_format
from backend.models import EfakturaImportRecord, Income, IncomeItem


@dataclass(frozen=True)
class EfakturaApiConfig:
    base_url: str
    list_path: str
    document_path: str
    header_name: str
    header_value: str


@dataclass
class Candidate:
    income: Income
    external_id: str | None = None
    source: str = "record"


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def sync_boundary(value: date, *, end_of_day: bool) -> str:
    moment = datetime.combine(value, time(23, 59, 59) if end_of_day else time(0, 0, 0))
    return moment.isoformat()


def normalize_income_number(income: Income) -> str:
    fallback_year = income.invoice_year or (income.issued_date.year if income.issued_date else None)
    return canonical_invoice_number(income.invoice_number, fallback_year)


def canonical_invoice_number(value: str | None, fallback_year: int | None = None) -> str:
    """Normalize invoice numbers for matching, including suffixes like 0012-2026-A."""
    raw = (value or "").strip().upper()
    raw = " ".join(raw.split())
    if not raw:
        return ""

    match = re.fullmatch(r"0*(\d+)-(20\d{2})(.*)", raw)
    if match:
        serial, year, suffix = match.groups()
        return f"{int(serial)}-{year}{suffix}"

    match = re.fullmatch(r"(20\d{2})-0*(\d+)(.*)", raw)
    if match:
        year, serial, suffix = match.groups()
        return f"{int(serial)}-{year}{suffix}"

    normalized = to_number_year_format(raw, fallback_year)
    if normalized != raw:
        return canonical_invoice_number(normalized, fallback_year)
    return raw


def is_amount_close(left: Decimal, right: Decimal) -> bool:
    return abs(to_decimal(left) - to_decimal(right)) <= Decimal("0.01")


def is_legacy_full_invoice_item(item: IncomeItem, income: Income) -> bool:
    name = (item.name or "").strip()
    description = (income.description or "").strip()
    if not name or not description or name != description or ";" not in name:
        return False
    invoice_amount = to_decimal(income.amount_rsd or ZERO_DECIMAL)
    return (
        to_decimal(item.quantity or ZERO_DECIMAL) == Decimal("1")
        and to_decimal(item.unit_price or ZERO_DECIMAL) == invoice_amount
        and to_decimal(item.total_amount or ZERO_DECIMAL) == invoice_amount
    )


def should_process_income(income: Income, *, replace_existing: bool, replace_legacy: bool) -> tuple[bool, str]:
    items = list(income.items or [])
    if not items:
        return True, "empty"
    if replace_existing:
        return True, "replace-existing"
    if replace_legacy and len(items) == 1 and is_legacy_full_invoice_item(items[0], income):
        return True, "replace-legacy"
    return False, "has-items"


def items_from_parsed(parsed: dict[str, Any]) -> list[IncomeItem]:
    output: list[IncomeItem] = []
    for index, item in enumerate(parsed.get("items") or [], start=1):
        name = (item.get("name") or "").strip()
        if not name:
            continue
        output.append(
            IncomeItem(
                line_no=item.get("line_no") or index,
                name=name,
                quantity=item.get("quantity") or Decimal("1"),
                unit=item.get("unit") or "kom",
                unit_price=item.get("unit_price") or ZERO_DECIMAL,
                total_amount=item.get("total_amount") or ZERO_DECIMAL,
                tax_category=item.get("tax_category") or "O",
                tax_rate=item.get("tax_rate") or ZERO_DECIMAL,
            )
        )
    return output


def safe_file_part(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(value))[:120]


async def load_api_config(db) -> EfakturaApiConfig:
    enterprise = await get_efaktura_enterprise(db)
    if not enterprise:
        raise RuntimeError("Enterprise settings not found")
    if not enterprise.efaktura_api_key:
        raise RuntimeError("eFaktura API key is not configured")

    header_name = (enterprise.efaktura_api_key_header or "ApiKey").strip() or "ApiKey"
    header_prefix = enterprise.efaktura_api_key_prefix or ""
    return EfakturaApiConfig(
        base_url=get_effective_efaktura_setting(enterprise.efaktura_api_base_url, DEFAULT_EFAKTURA_API_BASE_URL),
        list_path=get_effective_efaktura_setting(enterprise.efaktura_outgoing_list_path, DEFAULT_EFAKTURA_OUTGOING_LIST_PATH),
        document_path=get_effective_efaktura_setting(enterprise.efaktura_outgoing_document_path, DEFAULT_EFAKTURA_OUTGOING_DOCUMENT_PATH),
        header_name=header_name,
        header_value=f"{header_prefix}{enterprise.efaktura_api_key}",
    )


async def download_outgoing_xml(config: EfakturaApiConfig, external_id: str) -> bytes:
    url = _format_url(
        config.base_url,
        config.document_path,
        id=external_id,
        external_id=external_id,
    )
    if not url:
        raise RuntimeError(f"Could not build eFaktura XML URL for external_id={external_id}")
    raw, content_type = await asyncio.to_thread(
        _http_request,
        url,
        method="GET",
        header_name=config.header_name,
        header_value=config.header_value,
    )
    return _extract_xml_bytes(raw, content_type)


async def list_outgoing_refs(config: EfakturaApiConfig, date_from: date, date_to: date) -> list[dict[str, Any]]:
    url = _format_url(
        config.base_url,
        config.list_path,
        from_=sync_boundary(date_from, end_of_day=False),
        to=sync_boundary(date_to, end_of_day=True),
        **{"from": sync_boundary(date_from, end_of_day=False)},
    )
    if not url:
        raise RuntimeError("Could not build eFaktura outgoing list URL")
    raw, _ = await asyncio.to_thread(
        _http_request,
        url,
        method="POST",
        header_name=config.header_name,
        header_value=config.header_value,
    )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError("eFaktura outgoing list response is not JSON") from exc
    return [ref for ref in _extract_document_refs(payload) if ref.get("external_id") not in (None, "")]


async def load_record_candidates(db, args) -> list[Candidate]:
    stmt = (
        select(Income, EfakturaImportRecord)
        .join(
            EfakturaImportRecord,
            and_(
                EfakturaImportRecord.imported_as == "income",
                EfakturaImportRecord.direction == "outgoing",
                EfakturaImportRecord.imported_record_id == Income.id,
            ),
        )
        .options(selectinload(Income.items))
        .where(EfakturaImportRecord.external_id.is_not(None))
        .order_by(Income.issued_date.asc(), Income.id.asc(), EfakturaImportRecord.id.desc())
    )
    if args.from_date:
        stmt = stmt.where(Income.issued_date >= args.from_date)
    if args.to_date:
        stmt = stmt.where(Income.issued_date <= args.to_date)
    if args.income_id:
        stmt = stmt.where(Income.id.in_(args.income_id))

    rows = (await db.execute(stmt)).all()
    candidates: list[Candidate] = []
    seen_income_ids: set[int] = set()
    for income, record in rows:
        if income.id in seen_income_ids:
            continue
        seen_income_ids.add(income.id)
        allowed, _ = should_process_income(
            income,
            replace_existing=args.replace_existing,
            replace_legacy=args.replace_legacy,
        )
        if not allowed:
            continue
        candidates.append(Candidate(income=income, external_id=str(record.external_id), source="record"))
        if args.limit and len(candidates) >= args.limit:
            break
    return candidates


async def load_scan_candidates(db, args, exclude_income_ids: set[int]) -> list[Income]:
    stmt = select(Income).options(selectinload(Income.items)).order_by(Income.issued_date.asc(), Income.id.asc())
    if args.from_date:
        stmt = stmt.where(Income.issued_date >= args.from_date)
    if args.to_date:
        stmt = stmt.where(Income.issued_date <= args.to_date)
    if args.income_id:
        stmt = stmt.where(Income.id.in_(args.income_id))
    if exclude_income_ids:
        stmt = stmt.where(~Income.id.in_(exclude_income_ids))

    rows = list((await db.execute(stmt)).scalars().all())
    output: list[Income] = []
    for income in rows:
        allowed, _ = should_process_income(
            income,
            replace_existing=args.replace_existing,
            replace_legacy=args.replace_legacy,
        )
        if allowed:
            output.append(income)
    return output


def match_scanned_income(parsed: dict[str, Any], candidates: list[Income]) -> tuple[Income | None, str]:
    parsed_number = canonical_invoice_number(parsed["invoice_number"], parsed["issued_date"].year)
    parsed_date = parsed["issued_date"]
    parsed_amount = to_decimal(parsed["amount_rsd"])

    by_number_date = [
        income
        for income in candidates
        if normalize_income_number(income) == parsed_number and income.issued_date == parsed_date
    ]
    if not by_number_date:
        return None, "no matching income"

    exact_amount = [
        income
        for income in by_number_date
        if is_amount_close(to_decimal(income.amount_rsd or ZERO_DECIMAL), parsed_amount)
    ]
    if len(exact_amount) == 1:
        return exact_amount[0], "matched by number/date/amount"
    if len(by_number_date) == 1:
        return by_number_date[0], "matched by number/date with amount warning"
    return None, "ambiguous matching income"


def validate_parsed_for_income(parsed: dict[str, Any], income: Income) -> list[str]:
    warnings: list[str] = []
    parsed_number = canonical_invoice_number(parsed["invoice_number"], parsed["issued_date"].year)
    expected_number = canonical_invoice_number(income.invoice_number, income.invoice_year or income.issued_date.year)
    if parsed_number != expected_number:
        warnings.append(f"invoice number mismatch: income={expected_number}, xml={parsed_number}")
    if parsed["issued_date"] != income.issued_date:
        warnings.append(f"date mismatch: income={income.issued_date}, xml={parsed['issued_date']}")
    if not is_amount_close(to_decimal(income.amount_rsd or ZERO_DECIMAL), to_decimal(parsed["amount_rsd"])):
        warnings.append(f"amount mismatch: income={income.amount_rsd}, xml={parsed['amount_rsd']}")
    return warnings


async def backfill_from_xml(db, *, candidate: Candidate, xml_bytes: bytes, args, external_id: str | None) -> dict[str, Any]:
    income = candidate.income
    parsed = parse_efaktura_invoice(xml_bytes, f"outgoing-{external_id or income.id}.xml")
    items = items_from_parsed(parsed)
    if not items:
        return {"status": "skipped", "reason": "XML has no invoice lines"}

    warnings = validate_parsed_for_income(parsed, income)
    blocking_warnings = [warning for warning in warnings if "invoice number mismatch" in warning or "date mismatch" in warning]
    if blocking_warnings and not args.allow_mismatch:
        return {"status": "skipped", "reason": "; ".join(blocking_warnings), "warnings": warnings}

    line_total = decimal_sum([item.total_amount or ZERO_DECIMAL for item in items])
    if not is_amount_close(line_total, to_decimal(income.amount_rsd or ZERO_DECIMAL)):
        warning = f"line total mismatch: income={income.amount_rsd}, lines={line_total}"
        warnings.append(warning)
        if not args.allow_line_total_mismatch:
            return {"status": "skipped", "reason": warning, "warnings": warnings}

    if args.save_xml_dir:
        args.save_xml_dir.mkdir(parents=True, exist_ok=True)
        file_name = f"income-{income.id}_{safe_file_part(income.invoice_number)}_{safe_file_part(external_id or 'no-id')}.xml"
        (args.save_xml_dir / file_name).write_bytes(xml_bytes)

    if not args.dry_run:
        income.items = items
        await db.flush()

    return {
        "status": "updated" if not args.dry_run else "would-update",
        "line_count": len(items),
        "line_total": line_total,
        "warnings": warnings,
    }


async def run_backfill(args) -> dict[str, Any]:
    summary = {
        "record_candidates": 0,
        "scan_candidates": 0,
        "downloaded": 0,
        "updated": 0,
        "would_update": 0,
        "cleared": 0,
        "would_clear": 0,
        "skipped": 0,
        "errors": 0,
    }

    db_path = get_db_path()
    if db_path:
        print(f"[backfill-income-items] Using DB: {db_path}")
    if args.dry_run:
        print("[backfill-income-items] Dry-run mode: database changes will not be committed.")

    async with AsyncSessionLocal() as db:
        if args.clear_line_total_mismatches:
            clear_summary = await clear_existing_line_total_mismatches(db, args)
            summary.update(clear_summary)
            if args.dry_run:
                await db.rollback()
            else:
                await db.commit()
            return summary

        config = await load_api_config(db)
        processed_income_ids: set[int] = set()

        record_candidates = await load_record_candidates(db, args)
        summary["record_candidates"] = len(record_candidates)
        print(f"[backfill-income-items] Candidates from import records: {len(record_candidates)}")

        for candidate in record_candidates:
            income = candidate.income
            try:
                xml_bytes = await download_outgoing_xml(config, candidate.external_id or "")
                summary["downloaded"] += 1
                result = await backfill_from_xml(
                    db,
                    candidate=candidate,
                    xml_bytes=xml_bytes,
                    args=args,
                    external_id=candidate.external_id,
                )
                processed_income_ids.add(income.id)
                status = result["status"]
                if status == "updated":
                    summary["updated"] += 1
                elif status == "would-update":
                    summary["would_update"] += 1
                else:
                    summary["skipped"] += 1
                print_result(income, candidate.external_id, result)
            except Exception as exc:
                summary["errors"] += 1
                print(f"[ERROR] income #{income.id} {income.invoice_number}: {exc}")

        if args.scan_api:
            scan_candidates = await load_scan_candidates(db, args, processed_income_ids)
            summary["scan_candidates"] = len(scan_candidates)
            print(f"[backfill-income-items] Scan candidates without matched records: {len(scan_candidates)}")
            if scan_candidates:
                dates = [income.issued_date for income in scan_candidates if income.issued_date]
                date_from = args.from_date or min(dates)
                date_to = args.to_date or max(dates)
                refs = await list_outgoing_refs(config, date_from, date_to)
                print(f"[backfill-income-items] eFaktura outgoing refs in range: {len(refs)}")
                remaining = list(scan_candidates)
                for ref in refs:
                    external_id = str(ref["external_id"])
                    if args.limit and (summary["updated"] + summary["would_update"]) >= args.limit:
                        break
                    try:
                        xml_bytes = await download_outgoing_xml(config, external_id)
                        summary["downloaded"] += 1
                        parsed = parse_efaktura_invoice(xml_bytes, f"outgoing-{external_id}.xml")
                        income, reason = match_scanned_income(parsed, remaining)
                        if not income:
                            summary["skipped"] += 1
                            print(f"[SKIP] external_id={external_id}: {reason}")
                            continue
                        candidate = Candidate(income=income, external_id=external_id, source="scan-api")
                        result = await backfill_from_xml(
                            db,
                            candidate=candidate,
                            xml_bytes=xml_bytes,
                            args=args,
                            external_id=external_id,
                        )
                        remaining = [item for item in remaining if item.id != income.id]
                        status = result["status"]
                        if status == "updated":
                            summary["updated"] += 1
                        elif status == "would-update":
                            summary["would_update"] += 1
                        else:
                            summary["skipped"] += 1
                        print_result(income, external_id, result, prefix=reason)
                    except Exception as exc:
                        summary["errors"] += 1
                        print(f"[ERROR] external_id={external_id}: {exc}")

        if args.dry_run:
            await db.rollback()
        else:
            await db.commit()
    return summary


def print_result(income: Income, external_id: str | None, result: dict[str, Any], *, prefix: str | None = None) -> None:
    status = str(result.get("status", "")).upper()
    parts = [
        f"[{status}]",
        f"income #{income.id}",
        str(income.invoice_number),
        f"external_id={external_id or '-'}",
    ]
    if prefix:
        parts.append(f"match={prefix}")
    if result.get("line_count") is not None:
        parts.append(f"lines={result['line_count']}")
        parts.append(f"line_total={result.get('line_total')}")
    if result.get("reason"):
        parts.append(f"reason={result['reason']}")
    print(" ".join(parts))
    for warning in result.get("warnings") or []:
        print(f"  [WARN] {warning}")


async def clear_existing_line_total_mismatches(db, args) -> dict[str, int]:
    summary = {
        "record_candidates": 0,
        "scan_candidates": 0,
        "downloaded": 0,
        "updated": 0,
        "would_update": 0,
        "cleared": 0,
        "would_clear": 0,
        "skipped": 0,
        "errors": 0,
    }
    stmt = select(Income).options(selectinload(Income.items)).order_by(Income.issued_date.asc(), Income.id.asc())
    if args.from_date:
        stmt = stmt.where(Income.issued_date >= args.from_date)
    if args.to_date:
        stmt = stmt.where(Income.issued_date <= args.to_date)
    if args.income_id:
        stmt = stmt.where(Income.id.in_(args.income_id))

    rows = list((await db.execute(stmt)).scalars().all())
    for income in rows:
        items = list(income.items or [])
        if not items:
            continue
        line_total = decimal_sum([item.total_amount or ZERO_DECIMAL for item in items])
        amount = to_decimal(income.amount_rsd or ZERO_DECIMAL)
        if is_amount_close(line_total, amount):
            summary["skipped"] += 1
            continue
        if args.dry_run:
            summary["would_clear"] += 1
            status = "WOULD-CLEAR"
        else:
            income.items = []
            summary["cleared"] += 1
            status = "CLEARED"
        print(f"[{status}] income #{income.id} {income.invoice_number} amount={amount} lines={line_total}")
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download outgoing eFaktura XML documents and backfill income_items for old Income records.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Download and parse XML, but do not write income_items.")
    parser.add_argument("--scan-api", action="store_true", help="Also scan outgoing sales invoices by date range and match Income without import records.")
    parser.add_argument("--from-date", type=parse_date, help="Only process Income issued on or after YYYY-MM-DD.")
    parser.add_argument("--to-date", type=parse_date, help="Only process Income issued on or before YYYY-MM-DD.")
    parser.add_argument("--income-id", type=int, action="append", help="Process only this Income id. Can be passed multiple times.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum records to update/check. 0 means no limit for record mode.")
    parser.add_argument("--replace-legacy", action="store_true", help="Replace a single legacy full-invoice item if it is detected.")
    parser.add_argument("--replace-existing", action="store_true", help="Replace existing income_items. Use only after manual review.")
    parser.add_argument("--allow-mismatch", action="store_true", help="Allow XML number/date mismatch when an import record points to the Income.")
    parser.add_argument("--allow-line-total-mismatch", action="store_true", help="Write XML lines even when their total differs from the Income amount.")
    parser.add_argument("--clear-line-total-mismatches", action="store_true", help="Clear existing income_items whose line total differs from Income.amount_rsd. Use with --income-id for targeted repair.")
    parser.add_argument("--save-xml-dir", type=Path, help="Optional directory to save downloaded XML files for audit.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.from_date and args.to_date and args.from_date > args.to_date:
        parser.error("--from-date must be before or equal to --to-date")
    if args.limit < 0:
        parser.error("--limit must be >= 0")
    summary = asyncio.run(run_backfill(args))
    print("[backfill-income-items] Summary:")
    for key, value in summary.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
