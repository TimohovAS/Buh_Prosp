import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import text

from backend.cash_service import (
    CASH_PROJECT_CODE,
    _pending_entry_matches_manual_cash_transfer,
    _pending_entry_matches_matched_cash_expense_transaction,
    _select_unambiguous_pending_withdrawal,
    get_or_create_cash_project_id,
)
from backend.models import BankTransaction, CashEntry


async def test_cash_project_reactivates_completed_project(db_session, make_project):
    project = await make_project(
        db_session,
        code=CASH_PROJECT_CODE,
        name="Cash",
        status="completed",
        is_internal=True,
    )

    project_id = await get_or_create_cash_project_id(db_session)

    assert project_id == project.id
    assert project.status == "active"


async def test_cash_project_normalizes_legacy_status(db_session, make_project):
    await db_session.execute(text("PRAGMA ignore_check_constraints = ON"))
    project = await make_project(
        db_session,
        code=CASH_PROJECT_CODE,
        name="Cash",
        status="archived",
        is_internal=True,
    )

    project_id = await get_or_create_cash_project_id(db_session)

    assert project_id == project.id
    assert project.status == "active"


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

    def test_ambiguous_pending_withdrawal_candidates_are_not_auto_selected(self):
        first = CashEntry(
            id=1,
            date=date(2026, 6, 26),
            direction="in",
            amount=Decimal("70000"),
            currency="RSD",
            description="Temporary cash withdrawal",
            entry_type="pending_withdrawal",
        )
        second = CashEntry(
            id=2,
            date=date(2026, 6, 30),
            direction="in",
            amount=Decimal("70000"),
            currency="RSD",
            description="Temporary cash withdrawal",
            entry_type="pending_withdrawal",
        )

        self.assertIsNone(_select_unambiguous_pending_withdrawal([first, second]))

    def test_single_pending_withdrawal_candidate_is_auto_selected(self):
        entry = CashEntry(
            id=1,
            date=date(2026, 6, 26),
            direction="in",
            amount=Decimal("70000"),
            currency="RSD",
            description="Temporary cash withdrawal",
            entry_type="pending_withdrawal",
        )

        self.assertIs(_select_unambiguous_pending_withdrawal([entry]), entry)


if __name__ == "__main__":
    unittest.main()
