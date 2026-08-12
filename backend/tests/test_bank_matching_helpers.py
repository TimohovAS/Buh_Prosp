from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from backend.bank_matching_service import (
    _get_income_available_amount,
    _matches_client_identifier,
    _matches_incoming_invoice_counterparty,
    _matches_counterparty_name,
    _matches_receipt_seller,
    _merge_income_payment_summary,
    _normalize_digits,
)
from backend.models import BankTransaction, Client, Income, IncomingInvoice, PurchaseReceipt


def test_matches_counterparty_name_accepts_exact_and_substring_matches():
    tx = BankTransaction(counterparty_name="ACME DOO BEOGRAD")

    assert _matches_counterparty_name(tx, Income(client_name="acme doo beograd")) is True
    assert _matches_counterparty_name(tx, Income(client_name="ACME DOO")) is True


def test_matches_counterparty_name_accepts_two_common_words_from_first_four():
    tx = BankTransaction(counterparty_name="ALFA BETA GAMMA DELTA EPSILON")
    income = Income(client_name="zz alfa beta yy")

    assert _matches_counterparty_name(tx, income) is True


def test_matches_counterparty_name_rejects_empty_or_weak_names():
    assert _matches_counterparty_name(BankTransaction(counterparty_name=None), Income(client_name="Client")) is False
    assert _matches_counterparty_name(BankTransaction(counterparty_name="Client"), Income(client_name=None)) is False
    assert (
        _matches_counterparty_name(BankTransaction(counterparty_name="Only One"), Income(client_name="Only Other"))
        is False
    )


def test_matches_counterparty_name_ignores_generic_legal_and_trade_words():
    tx = BankTransaction(counterparty_name="S.B.H.-SO TRADE DOO INDUSTRIJSKA ZONA")
    income = Income(client_name="JELA TRADE DOO")

    assert _matches_counterparty_name(tx, income) is False


def test_client_identifier_must_be_a_separate_number_not_part_of_bank_account():
    income = Income(client=Client(name="Client", pib="205000000"))
    tx = BankTransaction(counterparty_name="Client 205000000021600921")

    assert _matches_client_identifier(tx, income) is False


def test_matches_receipt_seller_uses_counterparty_purpose_and_reference():
    receipt = PurchaseReceipt(seller_name="Gomex doo")

    assert _matches_receipt_seller(BankTransaction(counterparty_name="GOMEX DOO"), receipt) is True
    assert _matches_receipt_seller(BankTransaction(purpose="Kartica GOMEX DOO racun"), receipt) is True
    assert _matches_receipt_seller(BankTransaction(bank_reference="GOMEX DOO 123"), receipt) is True


def test_matches_receipt_seller_ignores_short_words_for_common_word_match():
    tx = BankTransaction(purpose="AB XY payment")
    receipt = PurchaseReceipt(seller_name="AB XY Longname")

    assert _matches_receipt_seller(tx, receipt) is False


def test_matches_incoming_invoice_counterparty_uses_transaction_text():
    invoice = IncomingInvoice(counterparty_name="Alta banka")

    assert (
        _matches_incoming_invoice_counterparty(
            BankTransaction(counterparty_name="ALTA BANKA AD-racun provizije"),
            invoice,
        )
        is True
    )
    assert (
        _matches_incoming_invoice_counterparty(
            BankTransaction(purpose="Naknada za ALTA BANKA uslugu"),
            invoice,
        )
        is True
    )


def test_matches_incoming_invoice_counterparty_rejects_weak_match():
    assert (
        _matches_incoming_invoice_counterparty(
            BankTransaction(counterparty_name="Druga banka"),
            IncomingInvoice(counterparty_name="Alta banka"),
        )
        is False
    )


def test_normalize_digits_removes_non_digits_and_handles_none():
    assert _normalize_digits("265-0000001234-38") == "265000000123438"
    assert _normalize_digits(" RS 12 / 34 ") == "1234"
    assert _normalize_digits(None) == ""


def test_merge_income_payment_summary_accumulates_paid_amount_and_latest_reference():
    summary = {}

    _merge_income_payment_summary(
        summary,
        income_id=10,
        tx_id=1,
        tx_date=date(2026, 7, 1),
        amount=Decimal("40.00"),
        bank_reference="OLD",
    )
    _merge_income_payment_summary(
        summary,
        income_id=10,
        tx_id=2,
        tx_date=date(2026, 7, 3),
        amount=Decimal("15.50"),
        bank_reference="NEW",
    )
    _merge_income_payment_summary(
        summary,
        income_id=10,
        tx_id=3,
        tx_date=date(2026, 7, 2),
        amount=Decimal("4.50"),
        bank_reference="OLDER_THAN_NEW",
    )

    assert summary[10]["paid_amount"] == Decimal("60.00")
    assert summary[10]["latest_date"] == date(2026, 7, 3)
    assert summary[10]["latest_tx_id"] == 2
    assert summary[10]["bank_reference"] == "NEW"


def test_merge_income_payment_summary_uses_higher_tx_id_as_same_day_tiebreaker():
    summary = {}

    _merge_income_payment_summary(
        summary,
        income_id=10,
        tx_id=1,
        tx_date=date(2026, 7, 3),
        amount=Decimal("10.00"),
        bank_reference="LOW",
    )
    _merge_income_payment_summary(
        summary,
        income_id=10,
        tx_id=5,
        tx_date=date(2026, 7, 3),
        amount=Decimal("10.00"),
        bank_reference="HIGH",
    )

    assert summary[10]["paid_amount"] == Decimal("20.00")
    assert summary[10]["latest_tx_id"] == 5
    assert summary[10]["bank_reference"] == "HIGH"


def test_merge_income_payment_summary_ignores_none_income_id():
    summary = {}

    _merge_income_payment_summary(
        summary,
        income_id=None,
        tx_id=1,
        tx_date=date(2026, 7, 3),
        amount=Decimal("10.00"),
        bank_reference="REF",
    )

    assert summary == {}


def test_get_income_available_amount_uses_summary_and_clamps_to_zero():
    income = SimpleNamespace(id=10, amount_rsd=Decimal("100.00"))

    assert _get_income_available_amount(income, {}) == Decimal("100.00")
    assert _get_income_available_amount(income, {10: {"paid_amount": Decimal("35.25")}}) == Decimal("64.75")
    assert _get_income_available_amount(income, {10: {"paid_amount": Decimal("100.00")}}) == Decimal("0")
    assert _get_income_available_amount(income, {10: {"paid_amount": Decimal("125.00")}}) == Decimal("0")
