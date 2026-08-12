"""Normalization and extraction helpers for Serbian domestic bank accounts."""

from __future__ import annotations

import re


_COMPACT_ACCOUNT_RE = re.compile(r"(?<!\d)\d{18}(?!\d)")
_FORMATTED_ACCOUNT_RE = re.compile(r"(?<!\d)\d{3}-\d{1,13}-\d{2}(?!\d)")


def normalize_serbian_bank_account(value: str | None) -> str | None:
    """Return an 18-digit domestic account only when its MOD-97 checksum is valid."""

    digits = re.sub(r"\D+", "", value or "")
    if len(digits) != 18:
        return None
    if int(digits) % 97 != 1:
        return None
    return digits


def extract_serbian_bank_accounts(*values: str | None) -> set[str]:
    accounts: set[str] = set()
    for value in values:
        text = str(value or "")
        for pattern in (_FORMATTED_ACCOUNT_RE, _COMPACT_ACCOUNT_RE):
            for candidate in pattern.findall(text):
                normalized = normalize_serbian_bank_account(candidate)
                if normalized:
                    accounts.add(normalized)
    return accounts


def format_serbian_bank_account(value: str | None) -> str:
    normalized = normalize_serbian_bank_account(value)
    if not normalized:
        return str(value or "")
    return f"{normalized[:3]}-{normalized[3:16]}-{normalized[16:]}"
