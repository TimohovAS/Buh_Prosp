from backend.bank_account_utils import (
    extract_serbian_bank_accounts,
    format_serbian_bank_account,
    normalize_serbian_bank_account,
)


def test_normalize_serbian_bank_account_accepts_compact_and_formatted_values():
    assert normalize_serbian_bank_account("205000000021600921") == "205000000021600921"
    assert normalize_serbian_bank_account("205-0000000216009-21") == "205000000021600921"


def test_normalize_serbian_bank_account_rejects_bad_length_and_checksum():
    assert normalize_serbian_bank_account("20500000002160092") is None
    assert normalize_serbian_bank_account("205000000021600922") is None


def test_extract_serbian_bank_accounts_ignores_unrelated_numbers():
    assert extract_serbian_bank_accounts(
        "S.B.H.-SO TRADE DOO 205000000021600921",
        "Ref: 87000119820431 PIB 123456789",
    ) == {"205000000021600921"}


def test_format_serbian_bank_account_uses_domestic_display_format():
    assert format_serbian_bank_account("205000000021600921") == "205-0000000216009-21"
