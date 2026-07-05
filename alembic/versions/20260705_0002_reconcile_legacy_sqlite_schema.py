"""reconcile_legacy_sqlite_schema

Revision ID: 20260705_0002
Revises: 20260705_0001
Create Date: 2026-07-05 16:17:07.244225

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260705_0002"
down_revision: Union[str, Sequence[str], None] = "20260705_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(conn, table_name: str) -> bool:
    return (
        conn.exec_driver_sql(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).scalar()
        is not None
    )


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    rows = conn.exec_driver_sql(f'PRAGMA table_info("{table_name}")').fetchall()
    return any(str(row[1]).lower() == column_name.lower() for row in rows)


def _index_exists(conn, index_name: str) -> bool:
    return (
        conn.exec_driver_sql(
            "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = ?",
            (index_name,),
        ).scalar()
        is not None
    )


def _create_index(conn, index_name: str, table_name: str, columns: Sequence[str], *, unique: bool = False) -> None:
    if _index_exists(conn, index_name):
        return
    unique_sql = "UNIQUE " if unique else ""
    column_sql = ", ".join(f'"{column}"' for column in columns)
    conn.exec_driver_sql(f'CREATE {unique_sql}INDEX "{index_name}" ON "{table_name}" ({column_sql})')


def _drop_index(conn, index_name: str) -> None:
    if _index_exists(conn, index_name):
        conn.exec_driver_sql(f'DROP INDEX "{index_name}"')


def _drop_column(conn, table_name: str, column_name: str) -> None:
    if _table_exists(conn, table_name) and _column_exists(conn, table_name, column_name):
        conn.exec_driver_sql(f'ALTER TABLE "{table_name}" DROP COLUMN "{column_name}"')


def _preserve_and_drop_legacy_cash_transactions(conn) -> None:
    if not _table_exists(conn, "cash_transactions"):
        return

    conn.exec_driver_sql(
        """
        INSERT INTO audit_logs (user_id, action, entity_type, entity_id, description, ip_address, created_at)
        SELECT
            NULL,
            'legacy_migration',
            'cash_transactions',
            id,
            'Preserved legacy cash_transactions row before Alembic cleanup: '
            || 'type=' || COALESCE(type, '')
            || '; source=' || COALESCE(source, '')
            || '; reference_id=' || COALESCE(CAST(reference_id AS TEXT), '')
            || '; amount=' || COALESCE(CAST(amount AS TEXT), '')
            || '; date=' || COALESCE(CAST(date AS TEXT), ''),
            NULL,
            CURRENT_TIMESTAMP
        FROM cash_transactions AS legacy
        WHERE NOT EXISTS (
            SELECT 1
            FROM audit_logs AS existing
            WHERE existing.action = 'legacy_migration'
              AND existing.entity_type = 'cash_transactions'
              AND existing.entity_id = legacy.id
        )
        """
    )
    _drop_index(conn, "ix_cash_transactions_id")
    conn.exec_driver_sql('DROP TABLE "cash_transactions"')


def _replace_legacy_fk_target(conn, table_name: str, old_target: str, new_target: str) -> None:
    if not _table_exists(conn, table_name):
        return
    row = conn.exec_driver_sql(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    if not row or old_target not in str(row[0]):
        return

    conn.exec_driver_sql("PRAGMA writable_schema = ON")
    conn.exec_driver_sql(
        "UPDATE sqlite_master SET sql = REPLACE(sql, ?, ?) WHERE type = 'table' AND name = ?",
        (old_target, new_target, table_name),
    )
    schema_version = int(conn.exec_driver_sql("PRAGMA schema_version").scalar() or 0)
    conn.exec_driver_sql(f"PRAGMA schema_version = {schema_version + 1}")
    conn.exec_driver_sql("PRAGMA writable_schema = OFF")


def upgrade() -> None:
    """Reconcile legacy SQLite databases with the Alembic baseline."""
    conn = op.get_bind()
    if conn.dialect.name != "sqlite":
        return

    _preserve_and_drop_legacy_cash_transactions(conn)

    _replace_legacy_fk_target(conn, "cash_entries", "expenses__v8_old", "expenses")
    _replace_legacy_fk_target(conn, "income", "contracts__v8_old", "contracts")
    _replace_legacy_fk_target(conn, "monthly_obligations", "expenses__v8_old", "expenses")

    _drop_index(conn, "ix_counterparty_loan_movements_bank_transaction_id")
    _drop_index(conn, "ix_efaktura_import_records_created_at")
    _drop_index(conn, "uq_efaktura_import_records_document_key")
    _drop_index(conn, "ix_planned_expense_payments_worker_payout_id")
    _drop_index(conn, "ix_planned_expenses_worker_id")

    _drop_column(conn, "efaktura_import_records", "local_pdf_path")
    _drop_column(conn, "efaktura_import_records", "local_xml_path")
    _drop_column(conn, "efaktura_import_records", "file_saved_at")
    _drop_column(conn, "enterprise", "efaktura_save_xml")
    _drop_column(conn, "enterprise", "efaktura_download_files_enabled")
    _drop_column(conn, "enterprise", "efaktura_file_name_template")
    _drop_column(conn, "enterprise", "efaktura_download_dir")

    _create_index(conn, "ix_bank_transactions_date", "bank_transactions", ("date",))
    _create_index(conn, "ix_bank_transactions_direction", "bank_transactions", ("direction",))
    _create_index(conn, "ix_bank_transactions_id", "bank_transactions", ("id",))
    _create_index(conn, "ix_bank_transactions_status", "bank_transactions", ("status",))
    _create_index(conn, "ix_cash_entries_date", "cash_entries", ("date",))
    _create_index(conn, "ix_cash_entries_direction", "cash_entries", ("direction",))
    _create_index(conn, "ix_cash_entries_entry_type", "cash_entries", ("entry_type",))
    _create_index(conn, "ix_cash_entries_id", "cash_entries", ("id",))
    _create_index(conn, "ix_contract_items_id", "contract_items", ("id",))
    _create_index(conn, "ix_contracts_id", "contracts", ("id",))
    _create_index(conn, "ix_contracts_project_id", "contracts", ("project_id",))
    _create_index(conn, "ix_contribution_rates_id", "contribution_rates", ("id",))
    _create_index(conn, "ix_eco_tax_id", "eco_tax", ("id",))
    _create_index(
        conn, "ix_efaktura_import_records_document_key", "efaktura_import_records", ("document_key",), unique=True
    )
    _create_index(conn, "ix_efaktura_import_records_id", "efaktura_import_records", ("id",))
    _create_index(conn, "ix_enterprise_id", "enterprise", ("id",))
    _create_index(conn, "ix_expenses_id", "expenses", ("id",))
    _create_index(conn, "ix_income_id", "income", ("id",))
    _create_index(conn, "ix_monthly_obligations_id", "monthly_obligations", ("id",))
    _create_index(conn, "ix_payments_id", "payments", ("id",))
    _create_index(conn, "ix_planned_expense_payments_id", "planned_expense_payments", ("id",))
    _create_index(conn, "ix_planned_expenses_id", "planned_expenses", ("id",))
    _create_index(conn, "ix_projects_id", "projects", ("id",))
    _create_index(conn, "ix_transaction_categories_id", "transaction_categories", ("id",))
    _create_index(conn, "ix_year_decisions_id", "year_decisions", ("id",))

    with op.batch_alter_table("efaktura_import_records", schema=None) as batch_op:
        batch_op.alter_column("issued_date", existing_type=sa.Date(), nullable=False)
        batch_op.alter_column("amount_rsd", existing_type=sa.Numeric(14, 2), nullable=False)

    with op.batch_alter_table("transaction_categories", schema=None) as batch_op:
        batch_op.alter_column("category_type", existing_type=sa.String(20), nullable=True)
        batch_op.alter_column("category_group", existing_type=sa.String(20), nullable=True)
        batch_op.alter_column("is_active", existing_type=sa.Boolean(), nullable=True)
        batch_op.alter_column("sort_order", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    """This reconciliation migration is intentionally not reversible."""
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        conn.exec_driver_sql(
            """
            INSERT INTO audit_logs (user_id, action, entity_type, entity_id, description, ip_address, created_at)
            VALUES (
                NULL,
                'legacy_migration_downgrade',
                'schema',
                NULL,
                '20260705_0002 downgrade requested; schema reconciliation is not reversible.',
                NULL,
                CURRENT_TIMESTAMP
            )
            """
        )
