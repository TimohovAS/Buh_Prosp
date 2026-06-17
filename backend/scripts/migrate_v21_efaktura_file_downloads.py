import argparse
import os
import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))


def read_env_value(key: str) -> str | None:
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return None
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == key:
            return value.strip().strip('"').strip("'")
    return None


def get_db_path() -> Path:
    url = os.environ.get("DATABASE_URL") or read_env_value("DATABASE_URL") or "sqlite+aiosqlite:///./prospel.db"
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if url.startswith(prefix):
            path = Path(url[len(prefix):])
            return path.resolve() if path.is_absolute() else (ROOT_DIR / path).resolve()
    return (ROOT_DIR / "prospel.db").resolve()


def column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info('{table}')")
    return any(str(row[1]).lower() == column.lower() for row in cursor.fetchall())


def ensure_column(cursor: sqlite3.Cursor, table: str, column: str, ddl: str) -> bool:
    if column_exists(cursor, table, column):
        print(f"[v21] Column {table}.{column} already exists.")
        return False
    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    print(f"[v21] Added {table}.{column}")
    return True


def run_migration(conn: sqlite3.Connection) -> bool:
    cursor = conn.cursor()
    changed = False

    changed |= ensure_column(cursor, "enterprise", "efaktura_save_pdf", "BOOLEAN DEFAULT 0")
    changed |= ensure_column(cursor, "enterprise", "efaktura_incoming_pdf_path", "VARCHAR(500)")
    changed |= ensure_column(cursor, "enterprise", "efaktura_outgoing_pdf_path", "VARCHAR(500)")

    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description="Migration v21: add eFaktura PDF download settings.")
    parser.add_argument("--dry-run", action="store_true", help="Run migration in a transaction and roll it back.")
    args = parser.parse_args()

    db_path = get_db_path()
    print(f"[v21] Using DB: {db_path}")
    if args.dry_run:
        print("[v21] Dry-run mode: changes will be rolled back.")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("BEGIN")
        changed = run_migration(conn)
        if args.dry_run:
            conn.rollback()
            print("[v21] Dry-run completed, no changes committed.")
            return
        conn.commit()
        if changed:
            print("[v21] Migration completed successfully.")
        else:
            print("[v21] No database changes were needed.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
