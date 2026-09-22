"""Lookup Serbian companies through the official APR and SEF public datasets.

APR publishes one large monthly snapshot keyed by registration number.  SEF
publishes the public list of its users and supplies the missing PIB -> MB link.
Both inputs are converted into a small, rebuildable SQLite sidecar so lookups do
not enlarge the accounting database or require downloading the datasets for
every request.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.request import Request, urlopen
from uuid import uuid4

from backend.config import get_settings


APR_OPEN_DATA_URL = "https://openapi.apr.gov.rs/api/opendata/companies"
APR_DATASET_PAGE_URL = "https://data.gov.rs/sr/datasets/68000c424d29e8a004f93e04/"
SEF_COMPANIES_URL = "https://efaktura.mfin.gov.rs/api/publicApi/getAllCompanies?includeAllStatuses=false"
SEF_DOCUMENTATION_URL = "https://www.efaktura.gov.rs/tekst/907/lista-korisnika-sistema-elektronskih-faktura.php"
CACHE_SCHEMA_VERSION = "1"
PARTIAL_CACHE_RETRY_HOURS = 1
ATOMIC_REPLACE_ATTEMPTS = 5
BACKGROUND_REFRESH_RETRY_SECONDS = 5 * 60

IdentifierType = Literal["pib", "maticni_broj"]


class CompanyRegistryUnavailableError(RuntimeError):
    """Raised when neither a fresh nor a stale registry cache is available."""


_refresh_lock = asyncio.Lock()
_background_refresh_tasks: dict[Path, asyncio.Task[None]] = {}
_background_refresh_last_attempt: dict[Path, float] = {}
logger = logging.getLogger(__name__)


def normalize_registry_identifier(value: str | None, identifier_type: IdentifierType) -> str:
    raw = str(value or "").strip()
    if identifier_type == "pib" and raw.upper().startswith("RS"):
        raw = raw[2:]
    normalized = re.sub(r"\D", "", raw)
    required_length = 9 if identifier_type == "pib" else 8
    label = "PIB" if identifier_type == "pib" else "matični broj"
    if len(normalized) != required_length:
        raise ValueError(f"{label} must contain exactly {required_length} digits")
    return normalized


def _clean_identifier(value: Any, length: int) -> str | None:
    normalized = re.sub(r"\D", "", str(value or ""))
    return normalized if len(normalized) == length else None


def _clean_text(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _download_json(url: str, timeout_seconds: int) -> Any:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "ProspEl/3.0 company-registry-cache",
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - fixed official HTTPS URLs
        return json.load(response)


def _create_cache_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            maticni_broj TEXT,
            pib TEXT,
            sef_name TEXT,
            jbkjs TEXT,
            sef_deleted_on TEXT,
            apr_name TEXT,
            municipality TEXT,
            status TEXT,
            founded_on TEXT,
            legal_form TEXT,
            activity_code TEXT
        );

        CREATE INDEX ix_registry_companies_maticni_broj ON companies (maticni_broj);
        CREATE INDEX ix_registry_companies_pib ON companies (pib);
        """
    )


def _insert_sef_companies(connection: sqlite3.Connection, payload: Any) -> None:
    if not isinstance(payload, list):
        raise ValueError("Unexpected SEF company registry response")

    rows: list[tuple[str | None, ...]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        maticni_broj = _clean_identifier(item.get("RegistrationCode"), 8)
        pib = _clean_identifier(item.get("VatRegistrationCode"), 9)
        name = _clean_text(item.get("Name"))
        if not name or (not maticni_broj and not pib):
            continue
        rows.append(
            (
                maticni_broj,
                pib,
                name,
                _clean_text(item.get("BugetCompanyNumber")),
                _clean_text(item.get("DeletionDate")),
            )
        )

    connection.executemany(
        """
        INSERT INTO companies (maticni_broj, pib, sef_name, jbkjs, sef_deleted_on)
        VALUES (?, ?, ?, ?, ?)
        """,
        rows,
    )


def _merge_apr_companies(connection: sqlite3.Connection, payload: Any) -> str | None:
    if not isinstance(payload, dict) or not isinstance(payload.get("Podaci"), dict):
        raise ValueError("Unexpected APR company registry response")

    for raw_maticni_broj, item in payload["Podaci"].items():
        if not isinstance(item, dict):
            continue
        maticni_broj = _clean_identifier(raw_maticni_broj, 8)
        if not maticni_broj:
            continue
        values = (
            _clean_text(item.get("PoslovnoIme")),
            _clean_text(item.get("NazivOpstine")),
            _clean_text(item.get("NazivStatus") or item.get("NazivStatusa")),
            _clean_text(item.get("DatumOsnivanja")),
            _clean_text(item.get("NazivPravneForme")),
            _clean_text(item.get("SifraDelatnosti")),
            maticni_broj,
        )
        cursor = connection.execute(
            """
            UPDATE companies
            SET apr_name = ?, municipality = ?, status = ?, founded_on = ?,
                legal_form = ?, activity_code = ?
            WHERE maticni_broj = ?
            """,
            values,
        )
        if cursor.rowcount == 0:
            connection.execute(
                """
                INSERT INTO companies (
                    maticni_broj, apr_name, municipality, status,
                    founded_on, legal_form, activity_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (maticni_broj, *values[:-1]),
            )

    return _clean_text(payload.get("DatumPreseka"))


def _temporary_cache_path(cache_path: Path) -> Path:
    return cache_path.with_name(f"{cache_path.name}.{os.getpid()}.{uuid4().hex}.tmp")


def _replace_cache_file(temporary_path: Path, cache_path: Path) -> None:
    """Replace a cache atomically, retrying short-lived Windows file locks."""

    for attempt in range(ATOMIC_REPLACE_ATTEMPTS):
        try:
            os.replace(temporary_path, cache_path)
            return
        except OSError:
            if attempt + 1 >= ATOMIC_REPLACE_ATTEMPTS:
                raise
            time.sleep(0.05 * (attempt + 1))


def _write_company_registry_cache(
    cache_path: Path,
    *,
    sef_payload: Any | None,
    apr_payload: Any | None,
    refreshed_at: datetime | None = None,
    refresh_warning: str | None = None,
) -> None:
    if sef_payload is None and apr_payload is None:
        raise ValueError("At least one company registry payload is required")

    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = _temporary_cache_path(cache_path)

    try:
        connection = sqlite3.connect(temporary_path)
        try:
            _create_cache_schema(connection)
            if sef_payload is not None:
                _insert_sef_companies(connection, sef_payload)
            snapshot_date = _merge_apr_companies(connection, apr_payload) if apr_payload is not None else None
            metadata = {
                "schema_version": CACHE_SCHEMA_VERSION,
                "refreshed_at": (refreshed_at or datetime.now(timezone.utc)).isoformat(),
                "apr_snapshot_date": snapshot_date or "",
                "apr_source_url": APR_DATASET_PAGE_URL,
                "sef_source_url": SEF_DOCUMENTATION_URL,
                "sources_complete": "1" if sef_payload is not None and apr_payload is not None else "0",
                "refresh_warning": refresh_warning or "",
            }
            connection.executemany("INSERT INTO metadata (key, value) VALUES (?, ?)", metadata.items())
            connection.commit()
        finally:
            connection.close()
        _replace_cache_file(temporary_path, cache_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def build_company_registry_cache(
    cache_path: Path,
    *,
    sef_payload: Any,
    apr_payload: Any,
    refreshed_at: datetime | None = None,
) -> None:
    """Build an atomic cache from already decoded payloads (also used by tests)."""

    _write_company_registry_cache(
        cache_path,
        sef_payload=sef_payload,
        apr_payload=apr_payload,
        refreshed_at=refreshed_at,
    )


def refresh_company_registry_cache(cache_path: Path, timeout_seconds: int) -> None:
    """Download official datasets and atomically replace the local cache.

    A first run may use one available source. Once a valid cache exists, a
    partial refresh never replaces it, so a temporary source outage cannot
    discard previously downloaded registry data.
    """

    cache_path = Path(cache_path)
    sef_payload: Any | None = None
    apr_payload: Any | None = None
    errors: list[str] = []

    try:
        candidate = _download_json(SEF_COMPANIES_URL, timeout_seconds)
        if not isinstance(candidate, list):
            raise ValueError("Unexpected SEF company registry response")
        sef_payload = candidate
    except Exception:
        logger.warning("Could not download the SEF public company list", exc_info=True)
        errors.append("SEF is temporarily unavailable")

    try:
        candidate = _download_json(APR_OPEN_DATA_URL, timeout_seconds)
        if not isinstance(candidate, dict) or not isinstance(candidate.get("Podaci"), dict):
            raise ValueError("Unexpected APR company registry response")
        apr_payload = candidate
    except Exception:
        logger.warning("Could not download APR Open Data", exc_info=True)
        errors.append("APR is temporarily unavailable")

    if sef_payload is None and apr_payload is None:
        raise CompanyRegistryUnavailableError("Neither official company registry could be downloaded")

    if errors and _cache_is_usable(cache_path):
        raise CompanyRegistryUnavailableError("; ".join(errors))

    warning = "; ".join(errors) if errors else None
    _write_company_registry_cache(
        cache_path,
        sef_payload=sef_payload,
        apr_payload=apr_payload,
        refresh_warning=warning,
    )


def _read_metadata(cache_path: Path) -> dict[str, str]:
    connection = sqlite3.connect(cache_path)
    try:
        return dict(connection.execute("SELECT key, value FROM metadata").fetchall())
    finally:
        connection.close()


def _cache_is_usable(cache_path: Path) -> bool:
    if not cache_path.exists():
        return False
    try:
        metadata = _read_metadata(cache_path)
        if metadata.get("schema_version") != CACHE_SCHEMA_VERSION:
            return False
        connection = sqlite3.connect(cache_path)
        try:
            connection.execute("SELECT 1 FROM companies LIMIT 1").fetchone()
        finally:
            connection.close()
        return True
    except (OSError, sqlite3.DatabaseError):
        return False


def _cache_is_current(cache_path: Path, ttl_hours: int) -> bool:
    if not _cache_is_usable(cache_path):
        return False
    try:
        metadata = _read_metadata(cache_path)
        refreshed_at = datetime.fromisoformat(metadata["refreshed_at"])
        if refreshed_at.tzinfo is None:
            refreshed_at = refreshed_at.replace(tzinfo=timezone.utc)
        effective_ttl = max(ttl_hours, 1)
        if metadata.get("sources_complete", "1") != "1":
            effective_ttl = min(effective_ttl, PARTIAL_CACHE_RETRY_HOURS)
        return datetime.now(timezone.utc) - refreshed_at <= timedelta(hours=effective_ttl)
    except (KeyError, OSError, sqlite3.DatabaseError, ValueError):
        return False


def _lookup_cached(
    cache_path: Path,
    identifier_type: IdentifierType,
    identifier: str,
    *,
    stale: bool,
) -> dict[str, Any]:
    connection = sqlite3.connect(cache_path)
    connection.row_factory = sqlite3.Row
    try:
        metadata = dict(connection.execute("SELECT key, value FROM metadata").fetchall())
        column = "pib" if identifier_type == "pib" else "maticni_broj"
        rows = connection.execute(
            f"""
            SELECT * FROM companies
            WHERE {column} = ?
            ORDER BY CASE WHEN jbkjs IS NULL THEN 0 ELSE 1 END,
                     COALESCE(apr_name, sef_name), sef_name
            LIMIT 20
            """,
            (identifier,),
        ).fetchall()
    finally:
        connection.close()

    matches: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        # A budget unit may legitimately share PIB and MB with its parent.  Keep
        # those rows separate by JBKJS, but remove exact duplicate SEF records.
        name = row["sef_name"] if row["jbkjs"] else (row["apr_name"] or row["sef_name"])
        identity = (row["maticni_broj"], row["pib"], name, row["jbkjs"])
        if identity in seen:
            continue
        seen.add(identity)
        sources: list[dict[str, str]] = []
        if row["apr_name"]:
            sources.append(
                {
                    "code": "apr_open_data",
                    "label": "Агенција за привредне регистре — APR Open Data",
                    "url": metadata.get("apr_source_url", APR_DATASET_PAGE_URL),
                }
            )
        if row["sef_name"]:
            sources.append(
                {
                    "code": "sef_company_list",
                    "label": "Систем еФактура — јавна листа",
                    "url": metadata.get("sef_source_url", SEF_DOCUMENTATION_URL),
                }
            )
        matches.append(
            {
                "name": name,
                "registered_name": row["apr_name"],
                "sef_name": row["sef_name"],
                "pib": row["pib"],
                "maticni_broj": row["maticni_broj"],
                "jbkjs": row["jbkjs"],
                "municipality": row["municipality"],
                "status": row["status"],
                "founded_on": row["founded_on"],
                "legal_form": row["legal_form"],
                "activity_code": row["activity_code"],
                "sef_deleted_on": row["sef_deleted_on"],
                "sources": sources,
            }
        )

    return {
        "query_type": identifier_type,
        "query_value": identifier,
        "matches": matches,
        "refreshed_at": metadata.get("refreshed_at"),
        "apr_snapshot_date": metadata.get("apr_snapshot_date") or None,
        "stale": stale,
        "warning": metadata.get("refresh_warning") or None,
    }


async def _refresh_cache_in_background(cache_path: Path, timeout_seconds: int, ttl_hours: int) -> None:
    try:
        async with _refresh_lock:
            if _cache_is_current(cache_path, ttl_hours):
                return
            await asyncio.to_thread(refresh_company_registry_cache, cache_path, timeout_seconds)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning("Could not refresh company registry cache in the background", exc_info=True)


def _schedule_background_refresh(cache_path: Path, timeout_seconds: int, ttl_hours: int) -> None:
    current_task = _background_refresh_tasks.get(cache_path)
    if current_task and not current_task.done():
        return

    now = time.monotonic()
    last_attempt = _background_refresh_last_attempt.get(cache_path)
    if last_attempt is not None and now - last_attempt < BACKGROUND_REFRESH_RETRY_SECONDS:
        return

    task = asyncio.create_task(_refresh_cache_in_background(cache_path, timeout_seconds, ttl_hours))
    _background_refresh_tasks[cache_path] = task
    _background_refresh_last_attempt[cache_path] = now

    def forget(completed_task: asyncio.Task[None]) -> None:
        if _background_refresh_tasks.get(cache_path) is completed_task:
            _background_refresh_tasks.pop(cache_path, None)

    task.add_done_callback(forget)


async def lookup_company_registry(identifier_type: IdentifierType, value: str) -> dict[str, Any]:
    """Return registry suggestions, refreshing the sidecar cache when needed."""

    identifier = normalize_registry_identifier(value, identifier_type)
    settings = get_settings()
    cache_path = Path(settings.company_registry_cache_path).expanduser()
    cache_usable = _cache_is_usable(cache_path)
    stale = not _cache_is_current(cache_path, settings.company_registry_cache_ttl_hours)
    warning: str | None = None

    if stale and cache_usable:
        _schedule_background_refresh(
            cache_path,
            settings.company_registry_request_timeout_seconds,
            settings.company_registry_cache_ttl_hours,
        )
        warning = "Cached registry data is shown while the official sources are refreshed"
    elif stale:
        async with _refresh_lock:
            cache_usable = _cache_is_usable(cache_path)
            if not cache_usable:
                try:
                    await asyncio.to_thread(
                        refresh_company_registry_cache,
                        cache_path,
                        settings.company_registry_request_timeout_seconds,
                    )
                except Exception as exc:
                    raise CompanyRegistryUnavailableError(
                        "Company registry is temporarily unavailable and no local cache exists"
                    ) from exc
            cache_usable = _cache_is_usable(cache_path)
            stale = not _cache_is_current(cache_path, settings.company_registry_cache_ttl_hours)

    if not cache_usable:
        raise CompanyRegistryUnavailableError("The local company registry cache is unavailable")

    try:
        result = await asyncio.to_thread(
            _lookup_cached,
            cache_path,
            identifier_type,
            identifier,
            stale=stale,
        )
    except (OSError, sqlite3.DatabaseError) as exc:
        raise CompanyRegistryUnavailableError("The local company registry cache is unavailable") from exc
    result["warning"] = result.get("warning") or warning
    return result
