import argparse
import os
import sqlite3
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent


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
            path = Path(url[len(prefix) :])
            return path.resolve() if path.is_absolute() else (ROOT_DIR / path).resolve()
    return (ROOT_DIR / "prospel.db").resolve()


def column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info('{table}')")
    return any(str(row[1]).lower() == column.lower() for row in cursor.fetchall())


def table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (table,))
    return cursor.fetchone() is not None


def run_migration(conn: sqlite3.Connection) -> bool:
    cursor = conn.cursor()
    if not table_exists(cursor, "worker_payouts"):
        import sys

        if str(SCRIPT_DIR) not in sys.path:
            sys.path.append(str(SCRIPT_DIR))
        from migrate_v23_worker_weekly_and_trip_mode import run_migration as run_v23_migration

        print("[v24] Worker payouts table is missing; applying v23 workers schema first.")
        run_v23_migration(conn)

    if column_exists(cursor, "worker_payouts", "lodging_night_rate"):
        print("[v24] Column worker_payouts.lodging_night_rate already exists.")
        return False

    cursor.execute("ALTER TABLE worker_payouts ADD COLUMN lodging_night_rate NUMERIC(14, 2) DEFAULT 0")
    cursor.execute("UPDATE worker_payouts SET lodging_night_rate = COALESCE(lodging_amount, 0)")
    print("[v24] Added worker_payouts.lodging_night_rate")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Migration v24: worker payout lodging night rate.")
    parser.add_argument("--dry-run", action="store_true", help="Run migration in a transaction and roll it back.")
    args = parser.parse_args()

    db_path = get_db_path()
    print(f"[v24] Using DB: {db_path}")
    if args.dry_run:
        print("[v24] Dry-run mode: changes will be rolled back.")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("BEGIN")
        changed = run_migration(conn)
        if args.dry_run:
            conn.rollback()
            print("[v24] Dry-run completed, no changes committed.")
            return
        conn.commit()
        if changed:
            print("[v24] Migration completed successfully.")
        else:
            print("[v24] No database changes were needed.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
