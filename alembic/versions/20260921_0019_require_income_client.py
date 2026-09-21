"""Require an income client and remove the duplicated client name.

Revision ID: 20260921_0019
Revises: 20260902_0018
Create Date: 2026-09-21 00:00:00.000000

"""

from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260921_0019"
down_revision: Union[str, Sequence[str], None] = "20260902_0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


clients = sa.table(
    "clients",
    sa.column("id", sa.Integer),
    sa.column("name", sa.String(200)),
    sa.column("pib", sa.String(20)),
    sa.column("client_type", sa.String(20)),
    sa.column("document_language", sa.String(5)),
    sa.column("is_archived", sa.Boolean),
    sa.column("created_at", sa.DateTime),
)

income = sa.table(
    "income",
    sa.column("id", sa.Integer),
    sa.column("invoice_number", sa.String(50)),
    sa.column("invoice_year", sa.Integer),
    sa.column("client_id", sa.Integer),
    sa.column("client_name", sa.String(200)),
)

efaktura_import_records = sa.table(
    "efaktura_import_records",
    sa.column("id", sa.Integer),
    sa.column("customer_name", sa.String(200)),
    sa.column("customer_pib", sa.String(20)),
    sa.column("imported_as", sa.String(20)),
    sa.column("imported_record_id", sa.Integer),
)


def _compact(value: object) -> str | None:
    if value is None:
        return None
    compact = " ".join(str(value).split()).strip()
    return compact or None


def _normalize_name(value: object) -> str | None:
    compact = _compact(value)
    return compact.casefold() if compact else None


def _normalize_pib(value: object) -> str | None:
    if value is None:
        return None
    digits = "".join(character for character in str(value) if character.isdigit())
    if not digits:
        return None
    return digits[-9:] if len(digits) > 9 else digits


def _income_label(row: sa.RowMapping) -> str:
    number = _compact(row["invoice_number"]) or str(row["id"])
    year = row["invoice_year"]
    return f"{number} ({year})" if year else number


def _fail(row: sa.RowMapping, reason: str) -> None:
    raise RuntimeError(f"Cannot assign a client to income {_income_label(row)}: {reason}")


def _load_import_identity(
    import_rows: list[sa.RowMapping], income_row: sa.RowMapping
) -> tuple[str | None, str | None]:
    pib_values: dict[str, str] = {}
    name_values: dict[str, str] = {}

    for row in import_rows:
        pib_key = _normalize_pib(row["customer_pib"])
        if pib_key:
            pib_values.setdefault(pib_key, pib_key)

        customer_name = _compact(row["customer_name"])
        name_key = _normalize_name(customer_name)
        if name_key and customer_name:
            name_values.setdefault(name_key, customer_name)

    if len(pib_values) > 1:
        _fail(income_row, "linked eFaktura records contain different customer PIB values")

    source_pib = next(iter(pib_values.values()), None)
    if len(name_values) == 1:
        source_name = next(iter(name_values.values()))
    elif not name_values:
        source_name = _compact(income_row["client_name"])
    elif source_pib:
        source_name = next(
            (
                _compact(row["customer_name"])
                for row in reversed(import_rows)
                if _compact(row["customer_name"])
            ),
            None,
        )
    else:
        source_name = None

    return source_name, source_pib


def _find_client(
    client_rows: list[dict[str, object]],
    income_row: sa.RowMapping,
    source_name: str | None,
    source_pib: str | None,
) -> dict[str, object] | None:
    name_key = _normalize_name(source_name)
    pib_matches = [row for row in client_rows if source_pib and _normalize_pib(row["pib"]) == source_pib]

    if len(pib_matches) == 1:
        return pib_matches[0]
    if len(pib_matches) > 1:
        combined_matches = [row for row in pib_matches if name_key and _normalize_name(row["name"]) == name_key]
        if len(combined_matches) == 1:
            return combined_matches[0]
        _fail(income_row, "customer PIB matches more than one client")

    name_matches = [row for row in client_rows if name_key and _normalize_name(row["name"]) == name_key]
    if len(name_matches) > 1:
        _fail(income_row, "customer name matches more than one client")
    if len(name_matches) == 1:
        matched_pib = _normalize_pib(name_matches[0]["pib"])
        if source_pib and matched_pib and matched_pib != source_pib:
            return None
        return name_matches[0]

    return None


def _backfill_clients(connection: sa.Connection) -> None:
    null_incomes = list(
        connection.execute(
            sa.select(
                income.c.id,
                income.c.invoice_number,
                income.c.invoice_year,
                income.c.client_name,
            )
            .where(income.c.client_id.is_(None))
            .order_by(income.c.id)
        ).mappings()
    )
    if not null_incomes:
        return

    income_ids = [row["id"] for row in null_incomes]
    imports_by_income: dict[int, list[sa.RowMapping]] = {income_id: [] for income_id in income_ids}
    import_rows = connection.execute(
        sa.select(
            efaktura_import_records.c.id,
            efaktura_import_records.c.customer_name,
            efaktura_import_records.c.customer_pib,
            efaktura_import_records.c.imported_record_id,
        )
        .where(
            efaktura_import_records.c.imported_as == "income",
            efaktura_import_records.c.imported_record_id.in_(income_ids),
        )
        .order_by(efaktura_import_records.c.id)
    ).mappings()
    for row in import_rows:
        imports_by_income[row["imported_record_id"]].append(row)

    client_rows = [
        dict(row)
        for row in connection.execute(sa.select(clients.c.id, clients.c.name, clients.c.pib)).mappings()
    ]

    for income_row in null_incomes:
        source_name, source_pib = _load_import_identity(imports_by_income[income_row["id"]], income_row)
        matched_client = _find_client(client_rows, income_row, source_name, source_pib)

        if matched_client is None:
            if not source_name:
                _fail(income_row, "no customer name is available to create a client")
            client_id = connection.scalar(
                clients.insert()
                .values(
                    name=source_name,
                    pib=source_pib,
                    client_type="legal",
                    document_language="sr",
                    is_archived=False,
                    created_at=datetime.utcnow(),
                )
                .returning(clients.c.id)
            )
            if client_id is None:
                _fail(income_row, "the new client ID was not returned by the database")
            matched_client = {"id": client_id, "name": source_name, "pib": source_pib}
            client_rows.append(matched_client)
        elif source_pib and not _normalize_pib(matched_client["pib"]):
            connection.execute(
                clients.update().where(clients.c.id == matched_client["id"]).values(pib=source_pib)
            )
            matched_client["pib"] = source_pib

        connection.execute(
            income.update().where(income.c.id == income_row["id"]).values(client_id=matched_client["id"])
        )

    remaining = connection.scalar(sa.select(sa.func.count()).select_from(income).where(income.c.client_id.is_(None)))
    if remaining:
        raise RuntimeError(f"Cannot require income.client_id: {remaining} income rows still have no client")


def upgrade() -> None:
    connection = op.get_bind()
    _backfill_clients(connection)

    with op.batch_alter_table("income") as batch_op:
        batch_op.alter_column("client_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("client_name")


def downgrade() -> None:
    with op.batch_alter_table("income") as batch_op:
        batch_op.add_column(sa.Column("client_name", sa.String(length=200), nullable=True))
        batch_op.alter_column("client_id", existing_type=sa.Integer(), nullable=True)

    connection = op.get_bind()
    client_name = sa.select(clients.c.name).where(clients.c.id == income.c.client_id).scalar_subquery()
    connection.execute(income.update().values(client_name=client_name))
