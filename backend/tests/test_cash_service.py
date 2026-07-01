import unittest
from datetime import date
from decimal import Decimal

from backend.cash_service import (
    _pending_entry_matches_manual_cash_transfer,
    _pending_entry_matches_matched_cash_expense_transaction,
)
from backend.models import BankTransaction, CashEntry


class CashServiceTest(unittest.TestCase):
    def test_pending_withdrawal_matches_already_matched_expense_transaction(self):
        entry = CashEntry(
            date=date(2026, 6, 30),
            direction="in",
            amount=Decimal("70000"),
            currency="RSD",
            description="Temporary cash withdrawal",
            entry_type="pending_withdrawal",
        )
        transaction = BankTransaction(
            date=date(2026, 6, 30),
            amount=Decimal("-70000"),
            direction="out",
            currency="RSD",
            counterparty_name="ALTA BANKA AD BEOGRAD",
            purpose="Kartica 4025480007356295 : ATM ALTA BANKA VRSAC",
            status="matched",
            matched_type="expense",
            matched_id=123,
        )

        self.assertTrue(_pending_entry_matches_matched_cash_expense_transaction(entry, transaction, 14))

    def test_pending_withdrawal_does_not_match_non_expense_transaction(self):
        entry = CashEntry(
            date=date(2026, 6, 30),
            direction="in",
            amount=Decimal("70000"),
            currency="RSD",
            description="Temporary cash withdrawal",
            entry_type="pending_withdrawal",
        )
        transaction = BankTransaction(
            date=date(2026, 6, 30),
            amount=Decimal("-70000"),
            direction="out",
            currency="RSD",
            purpose="Kartica 4025480007356295 : ATM ALTA BANKA VRSAC",
            status="matched",
            matched_type="obligation",
            matched_id=123,
        )

        self.assertFalse(_pending_entry_matches_matched_cash_expense_transaction(entry, transaction, 14))

    def test_pending_withdrawal_matches_manual_cash_transfer(self):
        entry = CashEntry(
            date=date(2026, 6, 30),
            direction="in",
            amount=Decimal("80000"),
            currency="RSD",
            description="Temporary cash withdrawal",
            entry_type="pending_withdrawal",
        )
        transaction = BankTransaction(
            date=date(2026, 6, 30),
            amount=Decimal("-80000"),
            direction="out",
            currency="RSD",
            purpose="Kartica 4025480007356295 : ATM ALTA BANKA VRSAC",
            status="unmatched",
        )

        self.assertTrue(_pending_entry_matches_manual_cash_transfer(entry, transaction, 14))

    def test_pending_withdrawal_does_not_match_manual_transfer_before_entry_date(self):
        entry = CashEntry(
            date=date(2026, 6, 30),
            direction="in",
            amount=Decimal("80000"),
            currency="RSD",
            description="Temporary cash withdrawal",
            entry_type="pending_withdrawal",
        )
        transaction = BankTransaction(
            date=date(2026, 6, 29),
            amount=Decimal("-80000"),
            direction="out",
            currency="RSD",
            purpose="Kartica 4025480007356295 : ATM ALTA BANKA VRSAC",
            status="unmatched",
        )

        self.assertFalse(_pending_entry_matches_manual_cash_transfer(entry, transaction, 14))


if __name__ == "__main__":
    unittest.main()
