"""Migration v10: add eFaktura settings and import registry."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from backend.config import get_settings


def get_db_path() -> Path:
    url = get_settings().database_url
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if url.startswith(prefix):
            raw = url[len(prefix) :]
            path = Path(raw)
            if not path.is_absolute():
                return (ROOT_DIR / path).resolve()
            return path.resolve()
    return (ROOT_DIR / "prospel.db").resolve()


DB_PATH = get_db_path()


def column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(str(row[1]).lower() == column.lower() for row in cursor.fetchall())


def ensure_column(cursor: sqlite3.Cursor, table: str, column: str, ddl: str) -> None:
    if not column_exists(cursor, table, column):
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        print(f"[v10] Added {table}.{column}")
    else:
        print(f"[v10] Column {table}.{column} already exists.")


def main() -> None:
    print(f"[v10] Using DB: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()

        ensure_column(cursor, "enterprise", "efaktura_enabled", "BOOLEAN DEFAULT 0")
        ensure_column(cursor, "enterprise", "efaktura_api_base_url", "VARCHAR(500)")
        ensure_column(cursor, "enterprise", "efaktura_api_key", "TEXT")
        ensure_column(cursor, "enterprise", "efaktura_api_key_header", "VARCHAR(100) DEFAULT 'ApiKey'")
        ensure_column(cursor, "enterprise", "efaktura_api_key_prefix", "VARCHAR(50) DEFAULT ''")
        ensure_column(cursor, "enterprise", "efaktura_sync_incoming", "BOOLEAN DEFAULT 1")
        ensure_column(cursor, "enterprise", "efaktura_sync_outgoing", "BOOLEAN DEFAULT 1")
        ensure_column(cursor, "enterprise", "efaktura_sync_lookback_days", "INTEGER DEFAULT 30")
        ensure_column(cursor, "enterprise", "efaktura_incoming_list_path", "VARCHAR(500)")
        ensure_column(cursor, "enterprise", "efaktura_incoming_document_path", "VARCHAR(500)")
        ensure_column(cursor, "enterprise", "efaktura_outgoing_list_path", "VARCHAR(500)")
        ensure_column(cursor, "enterprise", "efaktura_outgoing_document_path", "VARCHAR(500)")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS efaktura_import_records (
              id INTEGER PRIMARY KEY,
              document_key VARCHAR(500) NOT NULL,
              external_id VARCHAR(200),
              direction VARCHAR(20) NOT NULL,
              invoice_number VARCHAR(100) NOT NULL,
              issued_date DATE,
              amount_rsd NUMERIC(14,2) DEFAULT 0,
              supplier_name VARCHAR(255),
              supplier_pib VARCHAR(50),
              customer_name VARCHAR(255),
              customer_pib VARCHAR(50),
              imported_as VARCHAR(20) NOT NULL,
              imported_record_id INTEGER NOT NULL,
              source VARCHAR(50) NOT NULL,
              file_name VARCHAR(255),
              created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_efaktura_import_records_document_key ON efaktura_import_records(document_key)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_efaktura_import_records_external_id ON efaktura_import_records(external_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_efaktura_import_records_created_at ON efaktura_import_records(created_at)"
        )

        conn.commit()
        print("[v10] Migration completed successfully.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
