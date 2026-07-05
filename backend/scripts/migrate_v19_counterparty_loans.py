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
            path = Path(url[len(prefix) :])
            return path.resolve() if path.is_absolute() else (ROOT_DIR / path).resolve()
    return (ROOT_DIR / "prospel.db").resolve()


def run_migration(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS counterparty_loans (
            id INTEGER PRIMARY KEY,
            loan_type VARCHAR(20) NOT NULL,
            client_id INTEGER,
            counterparty_name VARCHAR(200) NOT NULL,
            agreement_number VARCHAR(100),
            agreement_date DATE,
            start_date DATE NOT NULL,
            due_date DATE,
            currency VARCHAR(5) NOT NULL DEFAULT 'RSD',
            note TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'open',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER,
            FOREIGN KEY(client_id) REFERENCES clients(id),
            FOREIGN KEY(created_by) REFERENCES users(id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS counterparty_loan_movements (
            id INTEGER PRIMARY KEY,
            loan_id INTEGER NOT NULL,
            movement_type VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            amount NUMERIC(14, 2) NOT NULL,
            currency VARCHAR(5) NOT NULL DEFAULT 'RSD',
            bank_transaction_id INTEGER,
            note TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER,
            FOREIGN KEY(loan_id) REFERENCES counterparty_loans(id) ON DELETE CASCADE,
            FOREIGN KEY(bank_transaction_id) REFERENCES bank_transactions(id),
            FOREIGN KEY(created_by) REFERENCES users(id)
        )
        """
    )
    for statement in (
        "CREATE INDEX IF NOT EXISTS ix_counterparty_loans_id ON counterparty_loans(id)",
        "CREATE INDEX IF NOT EXISTS ix_counterparty_loans_loan_type ON counterparty_loans(loan_type)",
        "CREATE INDEX IF NOT EXISTS ix_counterparty_loans_client_id ON counterparty_loans(client_id)",
        "CREATE INDEX IF NOT EXISTS ix_counterparty_loans_start_date ON counterparty_loans(start_date)",
        "CREATE INDEX IF NOT EXISTS ix_counterparty_loans_status ON counterparty_loans(status)",
        "CREATE INDEX IF NOT EXISTS ix_counterparty_loan_movements_id ON counterparty_loan_movements(id)",
        "CREATE INDEX IF NOT EXISTS ix_counterparty_loan_movements_loan_id ON counterparty_loan_movements(loan_id)",
        "CREATE INDEX IF NOT EXISTS ix_counterparty_loan_movements_movement_type ON counterparty_loan_movements(movement_type)",
        "CREATE INDEX IF NOT EXISTS ix_counterparty_loan_movements_date ON counterparty_loan_movements(date)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_counterparty_loan_movements_bank_transaction_id_not_null ON counterparty_loan_movements(bank_transaction_id) WHERE bank_transaction_id IS NOT NULL",
    ):
        cursor.execute(statement)


def main() -> None:
    parser = argparse.ArgumentParser(description="Migration v19: counterparty loans and movements.")
    parser.add_argument("--dry-run", action="store_true", help="Run migration in a transaction and roll it back.")
    args = parser.parse_args()

    db_path = get_db_path()
    print(f"[v19] Using DB: {db_path}")
    if args.dry_run:
        print("[v19] Dry-run mode: changes will be rolled back.")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("BEGIN")
        run_migration(conn)
        if args.dry_run:
            conn.rollback()
            print("[v19] Dry-run completed, no changes committed.")
            return
        conn.commit()
        print("[v19] Migration completed successfully.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
