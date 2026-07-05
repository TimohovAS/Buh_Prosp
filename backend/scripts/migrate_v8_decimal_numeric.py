"""Migration v8: convert money columns from FLOAT to NUMERIC(14,2) for SQLite."""

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


def table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cursor.fetchone() is not None


def columns_are_numeric(cursor: sqlite3.Cursor, table: str, money_columns: list[str]) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    info = {str(row[1]).lower(): str(row[2]).upper() for row in cursor.fetchall()}
    return all("NUMERIC" in info.get(column.lower(), "") for column in money_columns)


def rebuild_table(
    cursor: sqlite3.Cursor, table: str, money_columns: list[str], create_sql: str, insert_sql: str
) -> None:
    if not table_exists(cursor, table):
        print(f"[v8] Table {table} not found, skipping.")
        return
    if columns_are_numeric(cursor, table, money_columns):
        print(f"[v8] Table {table} already migrated.")
        return

    backup_table = f"{table}__v8_old"
    cursor.execute(f"DROP TABLE IF EXISTS {backup_table}")
    cursor.execute(f"ALTER TABLE {table} RENAME TO {backup_table}")
    cursor.execute(create_sql)
    cursor.execute(insert_sql.format(src=backup_table))
    cursor.execute(f"DROP TABLE {backup_table}")
    print(f"[v8] Rebuilt {table}.")


def main() -> None:
    print(f"[v8] Using DB: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")

        rebuild_table(
            cursor,
            "enterprise",
            ["opening_cash_balance"],
            """
            CREATE TABLE enterprise (
                id INTEGER PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                address VARCHAR(500),
                pib VARCHAR(20),
                maticni_broj VARCHAR(20),
                bank_name VARCHAR(100),
                bank_account VARCHAR(50),
                bank_swift VARCHAR(20),
                main_activity_code VARCHAR(20),
                opening_cash_balance NUMERIC(14,2) DEFAULT 0,
                opening_cash_date DATE,
                created_at DATETIME,
                updated_at DATETIME,
                emblem_data_url TEXT
            )
            """,
            """
            INSERT INTO enterprise (
                id, name, address, pib, maticni_broj, bank_name, bank_account, bank_swift, main_activity_code,
                opening_cash_balance, opening_cash_date, created_at, updated_at, emblem_data_url
            )
            SELECT
                id, name, address, pib, maticni_broj, bank_name, bank_account, bank_swift, main_activity_code,
                ROUND(COALESCE(opening_cash_balance, 0), 2), opening_cash_date, created_at, updated_at, emblem_data_url
            FROM {src}
            """,
        )

        rebuild_table(
            cursor,
            "contribution_rates",
            ["tax_amount", "pio_amount", "health_amount", "unemployment_amount"],
            """
            CREATE TABLE contribution_rates (
                id INTEGER PRIMARY KEY,
                year INTEGER NOT NULL,
                tax_amount NUMERIC(14,2) DEFAULT 0,
                pio_amount NUMERIC(14,2) DEFAULT 0,
                health_amount NUMERIC(14,2) DEFAULT 0,
                unemployment_amount NUMERIC(14,2) DEFAULT 0,
                pay_order_number VARCHAR(50),
                start_date DATE,
                is_active BOOLEAN,
                created_at DATETIME
            )
            """,
            """
            INSERT INTO contribution_rates (
                id, year, tax_amount, pio_amount, health_amount, unemployment_amount,
                pay_order_number, start_date, is_active, created_at
            )
            SELECT
                id, year,
                ROUND(COALESCE(tax_amount, 0), 2),
                ROUND(COALESCE(pio_amount, 0), 2),
                ROUND(COALESCE(health_amount, 0), 2),
                ROUND(COALESCE(unemployment_amount, 0), 2),
                pay_order_number, start_date, is_active, created_at
            FROM {src}
            """,
        )

        rebuild_table(
            cursor,
            "year_decisions",
            ["monthly_amount", "base_amount"],
            """
            CREATE TABLE year_decisions (
                id INTEGER PRIMARY KEY,
                year INTEGER NOT NULL,
                payment_type_id INTEGER NOT NULL,
                period_start DATE NOT NULL,
                period_end DATE NOT NULL,
                monthly_amount NUMERIC(14,2) NOT NULL,
                base_amount NUMERIC(14,2),
                rate_percent FLOAT,
                recipient_name VARCHAR(200),
                recipient_account VARCHAR(30) NOT NULL,
                sifra_placanja VARCHAR(10),
                model VARCHAR(10),
                poziv_na_broj VARCHAR(50) NOT NULL,
                poziv_na_broj_next VARCHAR(50),
                payment_purpose VARCHAR(200) NOT NULL,
                currency VARCHAR(5),
                is_provisional BOOLEAN,
                is_active BOOLEAN,
                created_at DATETIME,
                updated_at DATETIME,
                FOREIGN KEY(payment_type_id) REFERENCES payment_types (id)
            )
            """,
            """
            INSERT INTO year_decisions (
                id, year, payment_type_id, period_start, period_end, monthly_amount, base_amount, rate_percent,
                recipient_name, recipient_account, sifra_placanja, model, poziv_na_broj, poziv_na_broj_next,
                payment_purpose, currency, is_provisional, is_active, created_at, updated_at
            )
            SELECT
                id, year, payment_type_id, period_start, period_end,
                ROUND(COALESCE(monthly_amount, 0), 2),
                CASE WHEN base_amount IS NULL THEN NULL ELSE ROUND(base_amount, 2) END,
                rate_percent, recipient_name, recipient_account, sifra_placanja, model, poziv_na_broj,
                poziv_na_broj_next, payment_purpose, currency, is_provisional, is_active, created_at, updated_at
            FROM {src}
            """,
        )

        rebuild_table(
            cursor,
            "monthly_obligations",
            ["amount"],
            """
            CREATE TABLE monthly_obligations (
                id INTEGER PRIMARY KEY,
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                payment_type_id INTEGER NOT NULL,
                decision_id INTEGER,
                amount NUMERIC(14,2) NOT NULL,
                deadline DATE NOT NULL,
                status VARCHAR(20),
                paid_date DATE,
                payment_reference VARCHAR(100),
                payment_method VARCHAR(20),
                expense_id INTEGER,
                note VARCHAR(200),
                created_at DATETIME,
                FOREIGN KEY(payment_type_id) REFERENCES payment_types (id),
                FOREIGN KEY(decision_id) REFERENCES year_decisions (id),
                FOREIGN KEY(expense_id) REFERENCES expenses (id)
            )
            """,
            """
            INSERT INTO monthly_obligations (
                id, year, month, payment_type_id, decision_id, amount, deadline, status, paid_date,
                payment_reference, payment_method, expense_id, note, created_at
            )
            SELECT
                id, year, month, payment_type_id, decision_id, ROUND(COALESCE(amount, 0), 2), deadline, status,
                paid_date, payment_reference, payment_method, expense_id, note, created_at
            FROM {src}
            """,
        )

        rebuild_table(
            cursor,
            "projects",
            ["planned_income", "planned_expense"],
            """
            CREATE TABLE projects (
                id INTEGER PRIMARY KEY,
                code VARCHAR(50),
                name VARCHAR(200) NOT NULL,
                client_id INTEGER,
                is_internal BOOLEAN,
                status VARCHAR(20) NOT NULL,
                start_date DATE,
                end_date DATE,
                planned_income NUMERIC(14,2),
                planned_expense NUMERIC(14,2),
                notes TEXT,
                created_at DATETIME,
                updated_at DATETIME,
                CONSTRAINT uq_projects_code UNIQUE (code),
                FOREIGN KEY(client_id) REFERENCES clients (id)
            )
            """,
            """
            INSERT INTO projects (
                id, code, name, client_id, is_internal, status, start_date, end_date,
                planned_income, planned_expense, notes, created_at, updated_at
            )
            SELECT
                id, code, name, client_id, is_internal, status, start_date, end_date,
                CASE WHEN planned_income IS NULL THEN NULL ELSE ROUND(planned_income, 2) END,
                CASE WHEN planned_expense IS NULL THEN NULL ELSE ROUND(planned_expense, 2) END,
                notes, created_at, updated_at
            FROM {src}
            """,
        )

        rebuild_table(
            cursor,
            "bank_transactions",
            ["amount"],
            """
            CREATE TABLE bank_transactions (
                id INTEGER PRIMARY KEY,
                date DATE NOT NULL,
                amount NUMERIC(14,2) NOT NULL,
                direction VARCHAR(10) NOT NULL,
                currency VARCHAR(5),
                counterparty_name VARCHAR(200),
                purpose TEXT,
                bank_reference VARCHAR(100) UNIQUE,
                status VARCHAR(20),
                matched_type VARCHAR(50),
                matched_id INTEGER,
                project_id INTEGER,
                raw_json TEXT,
                created_at DATETIME,
                FOREIGN KEY(project_id) REFERENCES projects (id)
            )
            """,
            """
            INSERT INTO bank_transactions (
                id, date, amount, direction, currency, counterparty_name, purpose, bank_reference,
                status, matched_type, matched_id, project_id, raw_json, created_at
            )
            SELECT
                id, date, ROUND(COALESCE(amount, 0), 2), direction, currency, counterparty_name, purpose,
                bank_reference, status, matched_type, matched_id, project_id, raw_json, created_at
            FROM {src}
            """,
        )

        rebuild_table(
            cursor,
            "cash_entries",
            ["amount"],
            """
            CREATE TABLE cash_entries (
                id INTEGER PRIMARY KEY,
                date DATE NOT NULL,
                direction VARCHAR(10) NOT NULL,
                amount NUMERIC(14,2) NOT NULL,
                currency VARCHAR(5),
                description VARCHAR(500) NOT NULL,
                entry_type VARCHAR(20) NOT NULL,
                note TEXT,
                bank_transaction_id INTEGER UNIQUE,
                expense_id INTEGER UNIQUE,
                created_at DATETIME,
                created_by INTEGER,
                FOREIGN KEY(bank_transaction_id) REFERENCES bank_transactions (id),
                FOREIGN KEY(expense_id) REFERENCES expenses (id),
                FOREIGN KEY(created_by) REFERENCES users (id)
            )
            """,
            """
            INSERT INTO cash_entries (
                id, date, direction, amount, currency, description, entry_type, note,
                bank_transaction_id, expense_id, created_at, created_by
            )
            SELECT
                id, date, direction, ROUND(COALESCE(amount, 0), 2), currency, description, entry_type, note,
                bank_transaction_id, expense_id, created_at, created_by
            FROM {src}
            """,
        )

        rebuild_table(
            cursor,
            "income",
            ["amount_rsd", "paid_amount"],
            """
            CREATE TABLE income (
                id INTEGER PRIMARY KEY,
                date DATE NOT NULL,
                invoice_number VARCHAR(50) NOT NULL,
                invoice_year INTEGER,
                client_id INTEGER,
                client_name VARCHAR(200),
                description VARCHAR(500),
                amount_rsd NUMERIC(14,2) NOT NULL,
                currency VARCHAR(5),
                exchange_rate FLOAT,
                is_paid BOOLEAN,
                paid_date DATE,
                due_date DATE,
                paid_amount NUMERIC(14,2) DEFAULT 0.0,
                status VARCHAR(20) NOT NULL,
                project_id INTEGER,
                income_type VARCHAR(20),
                note TEXT,
                created_at DATETIME,
                updated_at DATETIME,
                created_by INTEGER,
                contract_id INTEGER,
                contract_payment_type VARCHAR(20),
                bank_reference VARCHAR(100),
                CONSTRAINT uq_income_invoice_per_year UNIQUE (invoice_year, invoice_number),
                FOREIGN KEY(client_id) REFERENCES clients (id),
                FOREIGN KEY(project_id) REFERENCES projects (id),
                FOREIGN KEY(created_by) REFERENCES users (id),
                FOREIGN KEY(contract_id) REFERENCES contracts (id)
            )
            """,
            """
            INSERT INTO income (
                id, date, invoice_number, invoice_year, client_id, client_name, description, amount_rsd,
                currency, exchange_rate, is_paid, paid_date, due_date, paid_amount, status, project_id,
                income_type, note, created_at, updated_at, created_by, contract_id, contract_payment_type, bank_reference
            )
            SELECT
                id, date, invoice_number, invoice_year, client_id, client_name, description,
                ROUND(COALESCE(amount_rsd, 0), 2), currency, exchange_rate, is_paid, paid_date, due_date,
                ROUND(COALESCE(paid_amount, 0), 2), status, project_id, income_type, note,
                created_at, updated_at, created_by, contract_id, contract_payment_type, bank_reference
            FROM {src}
            """,
        )

        rebuild_table(
            cursor,
            "contracts",
            ["amount"],
            """
            CREATE TABLE contracts (
                id INTEGER PRIMARY KEY,
                number VARCHAR(50) NOT NULL,
                date DATE NOT NULL,
                client_id INTEGER NOT NULL,
                project_id INTEGER,
                contract_type VARCHAR(50),
                subject VARCHAR(500),
                amount NUMERIC(14,2) DEFAULT 0,
                currency VARCHAR(5),
                validity_start DATE,
                validity_end DATE,
                status VARCHAR(20),
                note TEXT,
                created_at DATETIME,
                updated_at DATETIME,
                created_by INTEGER,
                FOREIGN KEY(client_id) REFERENCES clients (id),
                FOREIGN KEY(project_id) REFERENCES projects (id),
                FOREIGN KEY(created_by) REFERENCES users (id)
            )
            """,
            """
            INSERT INTO contracts (
                id, number, date, client_id, project_id, contract_type, subject, amount, currency,
                validity_start, validity_end, status, note, created_at, updated_at, created_by
            )
            SELECT
                id, number, date, client_id, project_id, contract_type, subject, ROUND(COALESCE(amount, 0), 2),
                currency, validity_start, validity_end, status, note, created_at, updated_at, created_by
            FROM {src}
            """,
        )

        rebuild_table(
            cursor,
            "contract_items",
            ["price", "amount"],
            """
            CREATE TABLE contract_items (
                id INTEGER PRIMARY KEY,
                contract_id INTEGER NOT NULL,
                description VARCHAR(500) NOT NULL,
                quantity FLOAT DEFAULT 1,
                unit VARCHAR(20),
                price NUMERIC(14,2) DEFAULT 0,
                amount NUMERIC(14,2) DEFAULT 0,
                sort_order INTEGER,
                FOREIGN KEY(contract_id) REFERENCES contracts (id)
            )
            """,
            """
            INSERT INTO contract_items (
                id, contract_id, description, quantity, unit, price, amount, sort_order
            )
            SELECT
                id, contract_id, description, quantity, unit,
                ROUND(COALESCE(price, 0), 2),
                ROUND(COALESCE(amount, 0), 2),
                sort_order
            FROM {src}
            """,
        )

        rebuild_table(
            cursor,
            "payments",
            ["tax_amount", "pio_amount", "health_amount", "unemployment_amount", "total_amount"],
            """
            CREATE TABLE payments (
                id INTEGER PRIMARY KEY,
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                rates_id INTEGER,
                tax_amount NUMERIC(14,2) DEFAULT 0,
                pio_amount NUMERIC(14,2) DEFAULT 0,
                health_amount NUMERIC(14,2) DEFAULT 0,
                unemployment_amount NUMERIC(14,2) DEFAULT 0,
                total_amount NUMERIC(14,2) DEFAULT 0,
                is_paid BOOLEAN,
                paid_date DATE,
                payment_reference VARCHAR(100),
                created_at DATETIME,
                FOREIGN KEY(rates_id) REFERENCES contribution_rates (id)
            )
            """,
            """
            INSERT INTO payments (
                id, year, month, rates_id, tax_amount, pio_amount, health_amount,
                unemployment_amount, total_amount, is_paid, paid_date, payment_reference, created_at
            )
            SELECT
                id, year, month, rates_id,
                ROUND(COALESCE(tax_amount, 0), 2),
                ROUND(COALESCE(pio_amount, 0), 2),
                ROUND(COALESCE(health_amount, 0), 2),
                ROUND(COALESCE(unemployment_amount, 0), 2),
                ROUND(COALESCE(total_amount, 0), 2),
                is_paid, paid_date, payment_reference, created_at
            FROM {src}
            """,
        )

        rebuild_table(
            cursor,
            "expenses",
            ["amount"],
            """
            CREATE TABLE expenses (
                id INTEGER PRIMARY KEY,
                date DATE NOT NULL,
                description VARCHAR(500) NOT NULL,
                amount NUMERIC(14,2) NOT NULL,
                currency VARCHAR(5),
                category VARCHAR(50),
                category_id INTEGER,
                contract_id INTEGER,
                bank_reference VARCHAR(100),
                paid_date DATE,
                status VARCHAR(20) NOT NULL,
                is_tax_related BOOLEAN NOT NULL,
                source VARCHAR(20) NOT NULL,
                reversed_expense_id INTEGER,
                reversal_of_id INTEGER,
                note TEXT,
                project_id INTEGER,
                created_at DATETIME,
                created_by INTEGER,
                FOREIGN KEY(category_id) REFERENCES transaction_categories (id),
                FOREIGN KEY(contract_id) REFERENCES contracts (id),
                FOREIGN KEY(reversed_expense_id) REFERENCES expenses (id),
                FOREIGN KEY(reversal_of_id) REFERENCES expenses (id),
                FOREIGN KEY(project_id) REFERENCES projects (id),
                FOREIGN KEY(created_by) REFERENCES users (id)
            )
            """,
            """
            INSERT INTO expenses (
                id, date, description, amount, currency, category, category_id, contract_id, bank_reference,
                paid_date, status, is_tax_related, source, reversed_expense_id, reversal_of_id, note,
                project_id, created_at, created_by
            )
            SELECT
                id, date, description, ROUND(COALESCE(amount, 0), 2), currency, category, category_id, contract_id,
                bank_reference, paid_date, status, is_tax_related, source, reversed_expense_id, reversal_of_id,
                note, project_id, created_at, created_by
            FROM {src}
            """,
        )

        rebuild_table(
            cursor,
            "planned_expenses",
            ["amount"],
            """
            CREATE TABLE planned_expenses (
                id INTEGER PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                description VARCHAR(500),
                amount NUMERIC(14,2) NOT NULL,
                currency VARCHAR(5),
                category VARCHAR(50),
                category_id INTEGER,
                project_id INTEGER,
                period VARCHAR(20),
                payment_day INTEGER,
                payment_day_of_week INTEGER,
                start_date DATE NOT NULL,
                end_date DATE,
                reminder_days INTEGER,
                is_active BOOLEAN,
                note TEXT,
                created_at DATETIME,
                updated_at DATETIME,
                FOREIGN KEY(category_id) REFERENCES transaction_categories (id),
                FOREIGN KEY(project_id) REFERENCES projects (id)
            )
            """,
            """
            INSERT INTO planned_expenses (
                id, name, description, amount, currency, category, category_id, project_id, period,
                payment_day, payment_day_of_week, start_date, end_date, reminder_days, is_active,
                note, created_at, updated_at
            )
            SELECT
                id, name, description, ROUND(COALESCE(amount, 0), 2), currency, category, category_id,
                project_id, period, payment_day, payment_day_of_week, start_date, end_date, reminder_days,
                is_active, note, created_at, updated_at
            FROM {src}
            """,
        )

        rebuild_table(
            cursor,
            "eco_tax",
            ["amount"],
            """
            CREATE TABLE eco_tax (
                id INTEGER PRIMARY KEY,
                year INTEGER NOT NULL,
                category VARCHAR(50),
                amount NUMERIC(14,2) DEFAULT 0,
                is_paid BOOLEAN,
                paid_date DATE,
                reminder_sent BOOLEAN,
                created_at DATETIME
            )
            """,
            """
            INSERT INTO eco_tax (
                id, year, category, amount, is_paid, paid_date, reminder_sent, created_at
            )
            SELECT
                id, year, category, ROUND(COALESCE(amount, 0), 2), is_paid, paid_date, reminder_sent, created_at
            FROM {src}
            """,
        )

        cursor.execute("PRAGMA foreign_keys=ON")
        conn.commit()
        print("[v8] Done.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
