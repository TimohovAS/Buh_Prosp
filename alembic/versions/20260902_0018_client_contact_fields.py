"""Split client contact into person, phone, email and website.

Revision ID: 20260902_0018
Revises: 20260902_0017
Create Date: 2026-09-02 16:10:00.000000

"""

import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260902_0018"
down_revision: Union[str, Sequence[str], None] = "20260902_0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Копия разбора из backend/client_contact_utils.py: миграция должна остаться
# воспроизводимой, даже если правила разбора в приложении потом изменятся.
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]*[a-z]{2,}", re.IGNORECASE)
WEBSITE_RE = re.compile(r"(?:https?://|www\.)[^\s,;]+", re.IGNORECASE)
PHONE_MARKER_RE = re.compile(r"\b(?:tel|тел|phone|mob|моб)\b\.?\s*:?", re.IGNORECASE)
PHONE_RE = re.compile(r"\+?\d[\d\s\-/().]{4,}\d")

clients_table = sa.table(
    "clients",
    sa.column("id", sa.Integer),
    sa.column("contact", sa.String),
    sa.column("phone", sa.String),
    sa.column("email", sa.String),
    sa.column("website", sa.String),
)


def _extract(pattern: re.Pattern[str], text: str, predicate=None) -> tuple[list[str], str]:
    found: list[str] = []

    def replace(match: re.Match[str]) -> str:
        value = match.group(0).strip()
        if predicate is not None and not predicate(value):
            return match.group(0)
        found.append(value)
        return " "

    return found, pattern.sub(replace, text)


def _split_contact_line(raw: str | None) -> dict[str, str]:
    persons: list[str] = []
    phones: list[str] = []
    emails: list[str] = []
    websites: list[str] = []

    for part in re.split(r"[;\n]+", raw or ""):
        if not part.strip():
            continue
        found_emails, rest = _extract(EMAIL_RE, part)
        emails.extend(found_emails)
        found_websites, rest = _extract(WEBSITE_RE, rest)
        websites.extend(found_websites)
        rest = PHONE_MARKER_RE.sub(" ", rest)
        found_phones, rest = _extract(PHONE_RE, rest, lambda value: sum(char.isdigit() for char in value) >= 6)
        phones.extend(phone.strip() for phone in found_phones)
        person = re.sub(r"\s+", " ", rest).strip(" ,;:-–—.")
        if any(char.isalpha() for char in person):
            persons.append(person)

    return {
        "contact": "; ".join(persons),
        "phone": ", ".join(phones),
        "email": ", ".join(emails),
        "website": ", ".join(websites),
    }


def upgrade() -> None:
    with op.batch_alter_table("clients") as batch_op:
        batch_op.add_column(sa.Column("phone", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("email", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("website", sa.String(length=200), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(
        sa.select(clients_table.c.id, clients_table.c.contact).where(clients_table.c.contact.isnot(None))
    ).fetchall()
    for row in rows:
        parts = _split_contact_line(row.contact)
        bind.execute(
            clients_table.update()
            .where(clients_table.c.id == row.id)
            .values(
                contact=parts["contact"][:200] or None,
                phone=parts["phone"][:100] or None,
                email=parts["email"][:120] or None,
                website=parts["website"][:200] or None,
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(
            clients_table.c.id,
            clients_table.c.contact,
            clients_table.c.phone,
            clients_table.c.email,
            clients_table.c.website,
        )
    ).fetchall()
    for row in rows:
        if not (row.phone or row.email or row.website):
            continue
        phone = (row.phone or "").strip()
        pieces = [
            (row.contact or "").strip(),
            f"tel. {phone}" if phone else "",
            (row.email or "").strip(),
            (row.website or "").strip(),
        ]
        line = "; ".join(piece for piece in pieces if piece)[:200]
        bind.execute(clients_table.update().where(clients_table.c.id == row.id).values(contact=line or None))

    with op.batch_alter_table("clients") as batch_op:
        batch_op.drop_column("website")
        batch_op.drop_column("email")
        batch_op.drop_column("phone")
