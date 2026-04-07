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
            raw = url[len(prefix):]
            path = Path(raw)
            if not path.is_absolute():
                return (ROOT_DIR / path).resolve()
            return path.resolve()
    return (ROOT_DIR / "prospel.db").resolve()


DB_PATH = get_db_path()


def main() -> None:
    print(f"[v13] Using DB: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS purchase_receipts (
                id INTEGER PRIMARY KEY,
                verification_url TEXT NOT NULL,
                qr_hash VARCHAR(64) NOT NULL,
                invoice_number VARCHAR(100),
                token VARCHAR(100),
                seller_name VARCHAR(200),
                seller_tax_id VARCHAR(20),
                seller_address VARCHAR(500),
                seller_city VARCHAR(100),
                receipt_datetime DATETIME,
                payment_type VARCHAR(100),
                payment_kind VARCHAR(20) DEFAULT 'unknown',
                total_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
                currency VARCHAR(5) DEFAULT 'RSD',
                is_valid BOOLEAN DEFAULT 1,
                status VARCHAR(30) NOT NULL DEFAULT 'new',
                project_id INTEGER,
                category_id INTEGER,
                expense_id INTEGER UNIQUE,
                bank_transaction_id INTEGER,
                cash_entry_id INTEGER,
                raw_html TEXT,
                raw_specifications_json TEXT,
                raw_recapitulation_json TEXT,
                created_at DATETIME,
                updated_at DATETIME,
                created_by INTEGER,
                FOREIGN KEY(project_id) REFERENCES projects(id),
                FOREIGN KEY(category_id) REFERENCES transaction_categories(id),
                FOREIGN KEY(expense_id) REFERENCES expenses(id),
                FOREIGN KEY(bank_transaction_id) REFERENCES bank_transactions(id),
                FOREIGN KEY(cash_entry_id) REFERENCES cash_entries(id),
                FOREIGN KEY(created_by) REFERENCES users(id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS purchase_receipt_items (
                id INTEGER PRIMARY KEY,
                receipt_id INTEGER NOT NULL,
                line_no INTEGER NOT NULL DEFAULT 1,
                gtin VARCHAR(100),
                name VARCHAR(500) NOT NULL,
                quantity NUMERIC(14, 3) NOT NULL DEFAULT 0,
                unit_price NUMERIC(14, 2) NOT NULL DEFAULT 0,
                total_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
                label VARCHAR(20),
                label_rate FLOAT,
                tax_base_amount NUMERIC(14, 2),
                vat_amount NUMERIC(14, 2),
                raw_json TEXT,
                FOREIGN KEY(receipt_id) REFERENCES purchase_receipts(id)
            )
            """
        )
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_purchase_receipts_qr_hash ON purchase_receipts(qr_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_purchase_receipts_invoice_number ON purchase_receipts(invoice_number)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_purchase_receipts_receipt_datetime ON purchase_receipts(receipt_datetime)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_purchase_receipt_items_receipt_id ON purchase_receipt_items(receipt_id)")
        conn.commit()
        print("[v13] Receipt tables migration complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
