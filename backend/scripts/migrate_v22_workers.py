import argparse
import os
import sqlite3
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]


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


def run_migration(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS workers (
            id INTEGER PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            worker_type VARCHAR(20) NOT NULL DEFAULT 'temporary',
            pay_scheme VARCHAR(20) NOT NULL DEFAULT 'per_day',
            phone VARCHAR(50),
            note TEXT,
            regular_day_rate NUMERIC(14, 2) DEFAULT 0,
            monthly_rate NUMERIC(14, 2) DEFAULT 0,
            trip_work_day_rate NUMERIC(14, 2) DEFAULT 0,
            trip_per_diem_rate NUMERIC(14, 2) DEFAULT 2500,
            trip_food_rate NUMERIC(14, 2) DEFAULT 3000,
            trip_advance_day_rate NUMERIC(14, 2) DEFAULT 3000,
            lodging_night_rate NUMERIC(14, 2) DEFAULT 0,
            lodging_nights_offset INTEGER DEFAULT -1,
            default_project_id INTEGER,
            default_category_id INTEGER,
            is_active BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(default_project_id) REFERENCES projects(id),
            FOREIGN KEY(default_category_id) REFERENCES transaction_categories(id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS worker_payouts (
            id INTEGER PRIMARY KEY,
            worker_id INTEGER NOT NULL,
            cash_entry_id INTEGER UNIQUE,
            expense_id INTEGER UNIQUE,
            payout_type VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            period_start DATE,
            period_end DATE,
            work_days NUMERIC(8, 2) DEFAULT 0,
            trip_days NUMERIC(8, 2) DEFAULT 0,
            lodging_nights NUMERIC(8, 2) DEFAULT 0,
            regular_day_rate NUMERIC(14, 2) DEFAULT 0,
            monthly_rate NUMERIC(14, 2) DEFAULT 0,
            trip_work_day_rate NUMERIC(14, 2) DEFAULT 0,
            trip_per_diem_rate NUMERIC(14, 2) DEFAULT 0,
            trip_food_rate NUMERIC(14, 2) DEFAULT 0,
            trip_advance_day_rate NUMERIC(14, 2) DEFAULT 0,
            lodging_amount NUMERIC(14, 2) DEFAULT 0,
            advance_paid NUMERIC(14, 2) DEFAULT 0,
            gross_amount NUMERIC(14, 2) NOT NULL,
            cash_paid_amount NUMERIC(14, 2) NOT NULL,
            remaining_amount NUMERIC(14, 2) DEFAULT 0,
            description VARCHAR(500) NOT NULL,
            note TEXT,
            project_id INTEGER,
            contract_id INTEGER,
            category_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER,
            FOREIGN KEY(worker_id) REFERENCES workers(id),
            FOREIGN KEY(cash_entry_id) REFERENCES cash_entries(id),
            FOREIGN KEY(expense_id) REFERENCES expenses(id),
            FOREIGN KEY(project_id) REFERENCES projects(id),
            FOREIGN KEY(contract_id) REFERENCES contracts(id),
            FOREIGN KEY(category_id) REFERENCES transaction_categories(id),
            FOREIGN KEY(created_by) REFERENCES users(id)
        )
        """
    )
    for statement in (
        "CREATE INDEX IF NOT EXISTS ix_workers_id ON workers(id)",
        "CREATE INDEX IF NOT EXISTS ix_workers_name ON workers(name)",
        "CREATE INDEX IF NOT EXISTS ix_workers_is_active ON workers(is_active)",
        "CREATE INDEX IF NOT EXISTS ix_worker_payouts_id ON worker_payouts(id)",
        "CREATE INDEX IF NOT EXISTS ix_worker_payouts_worker_id ON worker_payouts(worker_id)",
        "CREATE INDEX IF NOT EXISTS ix_worker_payouts_payout_type ON worker_payouts(payout_type)",
        "CREATE INDEX IF NOT EXISTS ix_worker_payouts_date ON worker_payouts(date)",
    ):
        cursor.execute(statement)


def main() -> None:
    parser = argparse.ArgumentParser(description="Migration v22: workers and worker cash payouts.")
    parser.add_argument("--dry-run", action="store_true", help="Run migration in a transaction and roll it back.")
    args = parser.parse_args()

    db_path = get_db_path()
    print(f"[v22] Using DB: {db_path}")
    if args.dry_run:
        print("[v22] Dry-run mode: changes will be rolled back.")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("BEGIN")
        run_migration(conn)
        if args.dry_run:
            conn.rollback()
            print("[v22] Dry-run completed, no changes committed.")
            return
        conn.commit()
        print("[v22] Migration completed successfully.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
