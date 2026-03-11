"""Сервис резервного копирования и восстановления SQLite."""
from __future__ import annotations

import asyncio
import json
import traceback
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend.config import get_settings
from backend.database import engine, get_db_path

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKUP_DB_FILENAME = "prospel.db"
BACKUP_META_FILENAME = "meta.json"
BACKUP_KINDS = {"auto", "manual", "pre-restore"}

_backup_lock = asyncio.Lock()


def _settings():
    return get_settings()


def _resolve_repo_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (ROOT_DIR / path).resolve()


def get_backup_dir() -> Path:
    return _resolve_repo_path(_settings().backup_dir)


def is_backup_supported() -> bool:
    return get_db_path() is not None


def _require_db_path() -> Path:
    db_path = get_db_path()
    if db_path is None:
        raise ValueError("Автоматический backup доступен только для SQLite")
    return db_path


def _retention_for_kind(kind: str) -> int:
    settings = _settings()
    if kind == "auto":
        return max(1, settings.backup_auto_retention_count)
    if kind == "manual":
        return max(1, settings.backup_manual_retention_count)
    if kind == "pre-restore":
        return max(1, settings.backup_pre_restore_retention_count)
    return 0


def _build_backup_filename(kind: str, created_at: datetime) -> str:
    stamp = created_at.astimezone(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    return f"{kind}_{stamp}.zip"


def _parse_backup_datetime(value: str | None, fallback_ts: float) -> datetime:
    if value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return datetime.fromtimestamp(fallback_ts, tz=timezone.utc)


def _fallback_kind_from_name(name: str) -> str:
    for kind in BACKUP_KINDS:
        if name.startswith(f"{kind}_"):
            return kind
    return "manual"


def _read_backup_info(path: Path) -> dict[str, Any]:
    stat = path.stat()
    payload: dict[str, Any] = {}
    try:
        with zipfile.ZipFile(path, "r") as archive:
            with archive.open(BACKUP_META_FILENAME) as handle:
                payload = json.loads(handle.read().decode("utf-8"))
    except Exception:
        payload = {}

    created_at = _parse_backup_datetime(payload.get("created_at"), stat.st_mtime)
    db_size_bytes = int(payload.get("db_size_bytes") or 0)
    return {
        "name": path.name,
        "kind": payload.get("kind") or _fallback_kind_from_name(path.name),
        "created_at": created_at,
        "db_size_bytes": db_size_bytes,
        "archive_size_bytes": stat.st_size,
    }


def _list_backups_sync() -> list[dict[str, Any]]:
    backup_dir = get_backup_dir()
    if not backup_dir.exists():
        return []

    items = [_read_backup_info(path) for path in backup_dir.glob("*.zip") if path.is_file()]
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return items


def _resolve_backup_path(backup_name: str) -> Path:
    backup_dir = get_backup_dir()
    candidate = (backup_dir / backup_name).resolve()
    if candidate.parent != backup_dir.resolve() or not candidate.exists() or not candidate.is_file():
        raise FileNotFoundError("Backup не найден")
    return candidate


def _create_backup_sync(kind: str) -> dict[str, Any]:
    if kind not in BACKUP_KINDS:
        raise ValueError("Неподдерживаемый тип backup")

    db_path = _require_db_path()
    if not db_path.exists():
        raise FileNotFoundError("Файл базы данных не найден")

    backup_dir = get_backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)

    created_at = datetime.now(timezone.utc)
    filename = _build_backup_filename(kind, created_at)
    archive_path = backup_dir / filename

    with tempfile.TemporaryDirectory(prefix="prospel-backup-") as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)
        snapshot_path = temp_dir / BACKUP_DB_FILENAME
        with sqlite3.connect(str(db_path)) as source_conn, sqlite3.connect(str(snapshot_path)) as snapshot_conn:
            source_conn.backup(snapshot_conn)

        db_size_bytes = snapshot_path.stat().st_size
        meta = {
            "kind": kind,
            "created_at": created_at.isoformat(),
            "db_size_bytes": db_size_bytes,
        }
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot_path, arcname=BACKUP_DB_FILENAME)
            archive.writestr(BACKUP_META_FILENAME, json.dumps(meta, ensure_ascii=False, indent=2))

    return _read_backup_info(archive_path)


def _delete_file_if_exists(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def _cleanup_auxiliary_sqlite_files(db_path: Path) -> None:
    _delete_file_if_exists(Path(f"{db_path}-wal"))
    _delete_file_if_exists(Path(f"{db_path}-shm"))


def _restore_backup_sync(backup_path: Path, db_path: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="prospel-restore-") as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)
        snapshot_path = temp_dir / BACKUP_DB_FILENAME

        with zipfile.ZipFile(backup_path, "r") as archive:
            names = set(archive.namelist())
            if BACKUP_DB_FILENAME not in names:
                raise ValueError("В архиве нет файла базы данных")
            archive.extract(BACKUP_DB_FILENAME, temp_dir)

        db_path.parent.mkdir(parents=True, exist_ok=True)
        _cleanup_auxiliary_sqlite_files(db_path)
        with sqlite3.connect(str(snapshot_path)) as source_conn, sqlite3.connect(str(db_path)) as target_conn:
            source_conn.backup(target_conn)
        _cleanup_auxiliary_sqlite_files(db_path)


def _cleanup_old_backups_sync() -> None:
    backups = _list_backups_sync()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in backups:
        grouped.setdefault(item["kind"], []).append(item)

    for kind, items in grouped.items():
        retention = _retention_for_kind(kind)
        if retention <= 0:
            continue
        for item in items[retention:]:
            _delete_file_if_exists(get_backup_dir() / item["name"])


async def list_backups() -> list[dict[str, Any]]:
    return await asyncio.to_thread(_list_backups_sync)


async def get_backup_status() -> dict[str, Any]:
    db_path = get_db_path()
    backups = await list_backups()
    settings = _settings()
    return {
        "settings": {
            "supported": db_path is not None,
            "backup_dir": str(get_backup_dir()),
            "database_path": str(db_path) if db_path else None,
            "current_db_size_bytes": db_path.stat().st_size if db_path and db_path.exists() else 0,
            "auto_enabled": settings.backup_auto_enabled and db_path is not None,
            "auto_interval_hours": settings.backup_auto_interval_hours,
            "auto_retention_count": settings.backup_auto_retention_count,
            "manual_retention_count": settings.backup_manual_retention_count,
            "pre_restore_retention_count": settings.backup_pre_restore_retention_count,
        },
        "backups": backups,
    }


async def create_backup(kind: str = "manual") -> dict[str, Any]:
    async with _backup_lock:
        backup = await asyncio.to_thread(_create_backup_sync, kind)
        await asyncio.to_thread(_cleanup_old_backups_sync)
        return backup


async def restore_backup(backup_name: str) -> dict[str, Any]:
    async with _backup_lock:
        db_path = _require_db_path()
        backup_path = _resolve_backup_path(backup_name)
        pre_restore_backup = None
        if db_path.exists():
            pre_restore_backup = await asyncio.to_thread(_create_backup_sync, "pre-restore")
        await asyncio.to_thread(_cleanup_old_backups_sync)
        await engine.dispose()
        await asyncio.to_thread(_restore_backup_sync, backup_path, db_path)
        await engine.dispose()
        return {
            "restored_backup": _read_backup_info(backup_path),
            "pre_restore_backup": pre_restore_backup,
        }


async def ensure_auto_backup_due() -> dict[str, Any] | None:
    settings = _settings()
    if not settings.backup_auto_enabled or not is_backup_supported():
        return None

    backups = await list_backups()
    latest_auto = next((item for item in backups if item["kind"] == "auto"), None)
    now = datetime.now(timezone.utc)
    if latest_auto is not None:
        latest_time = latest_auto["created_at"]
        if latest_time.tzinfo is None:
            latest_time = latest_time.replace(tzinfo=timezone.utc)
        if now - latest_time < timedelta(hours=settings.backup_auto_interval_hours):
            return None
    return await create_backup("auto")


async def backup_scheduler_loop() -> None:
    settings = _settings()
    delay_seconds = max(60, settings.backup_scheduler_check_minutes * 60)
    while True:
        try:
            await ensure_auto_backup_due()
        except asyncio.CancelledError:
            raise
        except Exception:
            traceback.print_exc()
        await asyncio.sleep(delay_seconds)
