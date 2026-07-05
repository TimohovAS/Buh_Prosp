"""Read-only diagnostics for cross-entity accounting links."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (
    BankTransaction,
    BankTransactionIncomeAllocation,
    CashEntry,
    CounterpartyLoanMovement,
    ContributionRates,
    Contract,
    EfakturaImportRecord,
    Expense,
    Income,
    IncomingInvoice,
    IncomingInvoiceSettlement,
    MonthlyObligation,
    Payment,
    Project,
    PurchaseReceipt,
)


BANK_MATCH_TYPES_WITH_TARGET = {"income", "expense", "obligation", "cash", "loan_movement"}
BANK_MATCH_TYPES_WITHOUT_TARGET = {"income_allocation", "owner_funds"}
BANK_MATCH_TYPES = BANK_MATCH_TYPES_WITH_TARGET | BANK_MATCH_TYPES_WITHOUT_TARGET
SETTLEMENT_LINK_BY_TYPE = {
    "bank": "bank_transaction_id",
    "cash": "cash_entry_id",
    "offset": "income_id",
}
EF_IMPORT_MODEL_BY_TYPE = {
    "income": Income,
    "expense": Expense,
    "incoming_invoice": IncomingInvoice,
}
VALID_CASH_ENTRY_TYPES = {"withdrawal", "expense", "adjustment", "payment"}


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _money(value: Any) -> str:
    return str(_decimal(value).quantize(Decimal("0.01")))


def _is_different(left: Any, right: Any) -> bool:
    return abs(_decimal(left) - _decimal(right)) > Decimal("0.01")


def _clean(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_clean(item) for item in value]
    return value


class DiagnosticsReport:
    def __init__(self, *, limit: int) -> None:
        self.limit = max(1, min(int(limit or 1000), 10000))
        self.total = 0
        self.by_severity: Counter[str] = Counter()
        self.by_code: Counter[str] = Counter()
        self.issues: list[dict[str, Any]] = []

    def add(
        self,
        severity: str,
        code: str,
        entity_type: str,
        entity_id: int | None,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.total += 1
        self.by_severity[severity] += 1
        self.by_code[code] += 1
        if len(self.issues) >= self.limit:
            return
        self.issues.append(
            {
                "severity": severity,
                "code": code,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "message": message,
                "details": _clean(details or {}),
            }
        )

    def payload(self) -> dict[str, Any]:
        return {
            "ok": self.by_severity["error"] == 0,
            "checked_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "truncated": self.total > len(self.issues),
            "summary": {
                "total": self.total,
                "errors": self.by_severity["error"],
                "warnings": self.by_severity["warning"],
                "info": self.by_severity["info"],
                "by_code": dict(self.by_code),
            },
            "issues": self.issues,
        }


async def _rows_by_id(db: AsyncSession, model: type) -> dict[int, Any]:
    result = await db.execute(select(model))
    return {int(row.id): row for row in result.scalars().all()}


async def _count_rows(db: AsyncSession, model: type) -> int:
    result = await db.execute(select(func.count()).select_from(model))
    return int(result.scalar() or 0)


async def build_link_diagnostics(db: AsyncSession, *, limit: int = 1000) -> dict[str, Any]:
    """Build a read-only report of broken accounting links."""
    report = DiagnosticsReport(limit=limit)

    bank_transactions = await _rows_by_id(db, BankTransaction)
    incomes = await _rows_by_id(db, Income)
    expenses = await _rows_by_id(db, Expense)
    obligations = await _rows_by_id(db, MonthlyObligation)
    cash_entries = await _rows_by_id(db, CashEntry)
    incoming_invoices = await _rows_by_id(db, IncomingInvoice)
    settlements = await _rows_by_id(db, IncomingInvoiceSettlement)
    receipts = await _rows_by_id(db, PurchaseReceipt)
    allocations = await _rows_by_id(db, BankTransactionIncomeAllocation)
    loan_movements = await _rows_by_id(db, CounterpartyLoanMovement)
    contracts = await _rows_by_id(db, Contract)
    projects = await _rows_by_id(db, Project)

    allocation_ids_by_tx: dict[int, list[int]] = defaultdict(list)
    for allocation in allocations.values():
        allocation_ids_by_tx[int(allocation.bank_transaction_id)].append(int(allocation.id))

    settlement_ids_by_invoice: dict[int, list[int]] = defaultdict(list)
    settlement_sum_by_invoice: dict[int, Decimal] = defaultdict(Decimal)
    for settlement in settlements.values():
        settlement_ids_by_invoice[int(settlement.incoming_invoice_id)].append(int(settlement.id))
        settlement_sum_by_invoice[int(settlement.incoming_invoice_id)] += _decimal(settlement.amount)

    incoming_expense_ids = {
        int(invoice.expense_id) for invoice in incoming_invoices.values() if invoice.expense_id is not None
    }
    receipt_expense_ids = {int(receipt.expense_id) for receipt in receipts.values() if receipt.expense_id is not None}
    _check_bank_transactions(
        report,
        bank_transactions=bank_transactions,
        incomes=incomes,
        expenses=expenses,
        obligations=obligations,
        cash_entries=cash_entries,
        loan_movements=loan_movements,
        allocation_ids_by_tx=allocation_ids_by_tx,
    )
    _check_loan_movements(report, movements=loan_movements, bank_transactions=bank_transactions)
    _check_income_allocations(report, allocations=allocations, bank_transactions=bank_transactions, incomes=incomes)
    _check_incomes(report, incomes=incomes, contracts=contracts, projects=projects)
    _check_monthly_obligations(report, obligations=obligations, expenses=expenses)
    _check_incoming_invoice_settlements(
        report,
        settlements=settlements,
        incoming_invoices=incoming_invoices,
        bank_transactions=bank_transactions,
        cash_entries=cash_entries,
        incomes=incomes,
    )
    _check_incoming_invoices(
        report,
        incoming_invoices=incoming_invoices,
        expenses=expenses,
        projects=projects,
        settlement_ids_by_invoice=settlement_ids_by_invoice,
        settlement_sum_by_invoice=settlement_sum_by_invoice,
    )
    _check_expenses(
        report,
        expenses=expenses,
        incoming_expense_ids=incoming_expense_ids,
        receipt_expense_ids=receipt_expense_ids,
    )
    _check_receipts(
        report, receipts=receipts, expenses=expenses, bank_transactions=bank_transactions, cash_entries=cash_entries
    )
    _check_cash_entries(report, cash_entries=cash_entries, expenses=expenses, bank_transactions=bank_transactions)
    await _check_efaktura_import_records(report, db)
    await _check_legacy_tables(report, db)

    return report.payload()


def _check_bank_transactions(
    report: DiagnosticsReport,
    *,
    bank_transactions: dict[int, BankTransaction],
    incomes: dict[int, Income],
    expenses: dict[int, Expense],
    obligations: dict[int, MonthlyObligation],
    cash_entries: dict[int, CashEntry],
    loan_movements: dict[int, CounterpartyLoanMovement],
    allocation_ids_by_tx: dict[int, list[int]],
) -> None:
    target_maps = {
        "income": incomes,
        "expense": expenses,
        "obligation": obligations,
        "cash": cash_entries,
        "loan_movement": loan_movements,
    }
    for tx in bank_transactions.values():
        tx_id = int(tx.id)
        if tx.status == "matched":
            if not tx.matched_type:
                report.add(
                    "error",
                    "bank_matched_without_type",
                    "bank_transaction",
                    tx_id,
                    "Matched bank transaction has no matched_type.",
                )
                continue
            if tx.matched_type not in BANK_MATCH_TYPES:
                report.add(
                    "error",
                    "bank_unknown_matched_type",
                    "bank_transaction",
                    tx_id,
                    "Bank transaction uses an unsupported matched_type.",
                    {"matched_type": tx.matched_type, "matched_id": tx.matched_id},
                )
                continue
            if tx.matched_type in BANK_MATCH_TYPES_WITH_TARGET:
                if tx.matched_id is None:
                    report.add(
                        "error",
                        "bank_matched_without_target",
                        "bank_transaction",
                        tx_id,
                        "Bank transaction matched_type requires matched_id.",
                        {"matched_type": tx.matched_type},
                    )
                    continue
                if int(tx.matched_id) not in target_maps[tx.matched_type]:
                    report.add(
                        "error",
                        "bank_missing_matched_target",
                        "bank_transaction",
                        tx_id,
                        "Bank transaction points to a missing matched target.",
                        {"matched_type": tx.matched_type, "matched_id": tx.matched_id},
                    )
                elif tx.matched_type == "loan_movement":
                    movement = loan_movements[int(tx.matched_id)]
                    if int(movement.bank_transaction_id or 0) != tx_id:
                        report.add(
                            "error",
                            "bank_loan_movement_link_mismatch",
                            "bank_transaction",
                            tx_id,
                            "Bank transaction and loan movement links do not match.",
                            {"movement_id": movement.id, "movement_bank_transaction_id": movement.bank_transaction_id},
                        )
            elif tx.matched_type == "income_allocation":
                if tx.matched_id is not None:
                    report.add(
                        "warning",
                        "bank_allocation_has_matched_id",
                        "bank_transaction",
                        tx_id,
                        "Income-allocation transaction should not use matched_id.",
                        {"matched_id": tx.matched_id},
                    )
                if not allocation_ids_by_tx.get(tx_id):
                    report.add(
                        "error",
                        "bank_allocation_without_rows",
                        "bank_transaction",
                        tx_id,
                        "Bank transaction is marked as income allocation but has no allocation rows.",
                    )
            elif tx.matched_type == "owner_funds" and tx.matched_id is not None:
                report.add(
                    "warning",
                    "bank_owner_funds_has_matched_id",
                    "bank_transaction",
                    tx_id,
                    "Owner-funds transaction should not use matched_id.",
                    {"matched_id": tx.matched_id},
                )
        elif tx.matched_type is not None or tx.matched_id is not None:
            report.add(
                "warning",
                "bank_unmatched_with_link_data",
                "bank_transaction",
                tx_id,
                "Non-matched bank transaction still contains link fields.",
                {"status": tx.status, "matched_type": tx.matched_type, "matched_id": tx.matched_id},
            )


def _check_income_allocations(
    report: DiagnosticsReport,
    *,
    allocations: dict[int, BankTransactionIncomeAllocation],
    bank_transactions: dict[int, BankTransaction],
    incomes: dict[int, Income],
) -> None:
    for allocation in allocations.values():
        allocation_id = int(allocation.id)
        if int(allocation.bank_transaction_id) not in bank_transactions:
            report.add(
                "error",
                "income_allocation_missing_bank_transaction",
                "bank_transaction_income_allocation",
                allocation_id,
                "Income allocation points to a missing bank transaction.",
                {"bank_transaction_id": allocation.bank_transaction_id},
            )
        if int(allocation.income_id) not in incomes:
            report.add(
                "error",
                "income_allocation_missing_income",
                "bank_transaction_income_allocation",
                allocation_id,
                "Income allocation points to a missing income.",
                {"income_id": allocation.income_id},
            )
        if _decimal(allocation.amount) <= 0:
            report.add(
                "warning",
                "income_allocation_non_positive_amount",
                "bank_transaction_income_allocation",
                allocation_id,
                "Income allocation amount should be positive.",
                {"amount": _money(allocation.amount)},
            )


def _check_loan_movements(
    report: DiagnosticsReport,
    *,
    movements: dict[int, CounterpartyLoanMovement],
    bank_transactions: dict[int, BankTransaction],
) -> None:
    for movement in movements.values():
        movement_id = int(movement.id)
        if movement.bank_transaction_id is None:
            continue
        transaction = bank_transactions.get(int(movement.bank_transaction_id))
        if not transaction:
            report.add(
                "error",
                "loan_movement_missing_bank_transaction",
                "counterparty_loan_movement",
                movement_id,
                "Loan movement points to a missing bank transaction.",
                {"bank_transaction_id": movement.bank_transaction_id},
            )
            continue
        if transaction.matched_type != "loan_movement" or int(transaction.matched_id or 0) != movement_id:
            report.add(
                "error",
                "loan_movement_bank_link_mismatch",
                "counterparty_loan_movement",
                movement_id,
                "Loan movement is not linked back from its bank transaction.",
                {
                    "bank_transaction_id": movement.bank_transaction_id,
                    "matched_type": transaction.matched_type,
                    "matched_id": transaction.matched_id,
                },
            )


def _check_incomes(
    report: DiagnosticsReport,
    *,
    incomes: dict[int, Income],
    contracts: dict[int, Contract],
    projects: dict[int, Project],
) -> None:
    for income in incomes.values():
        income_id = int(income.id)
        if income.project_id is not None and int(income.project_id) not in projects:
            report.add(
                "error",
                "income_missing_project",
                "income",
                income_id,
                "Income points to a missing project.",
                {"project_id": income.project_id},
            )
        if income.contract_id is None:
            continue

        contract = contracts.get(int(income.contract_id))
        if contract is None:
            report.add(
                "error",
                "income_missing_contract",
                "income",
                income_id,
                "Income points to a missing contract.",
                {"contract_id": income.contract_id},
            )
            continue
        if income.project_id != contract.project_id:
            report.add(
                "warning",
                "income_contract_project_mismatch",
                "income",
                income_id,
                "Income project_id differs from linked contract project_id.",
                {
                    "income_project_id": income.project_id,
                    "contract_id": income.contract_id,
                    "contract_project_id": contract.project_id,
                },
            )


def _check_monthly_obligations(
    report: DiagnosticsReport,
    *,
    obligations: dict[int, MonthlyObligation],
    expenses: dict[int, Expense],
) -> None:
    for obligation in obligations.values():
        obligation_id = int(obligation.id)
        if obligation.expense_id is not None and int(obligation.expense_id) not in expenses:
            report.add(
                "error",
                "monthly_obligation_missing_expense",
                "monthly_obligation",
                obligation_id,
                "Monthly obligation points to a missing expense.",
                {"expense_id": obligation.expense_id, "status": obligation.status},
            )
        if obligation.status == "paid" and obligation.expense_id is None:
            report.add(
                "warning",
                "monthly_obligation_paid_without_expense",
                "monthly_obligation",
                obligation_id,
                "Paid monthly obligation has no linked expense.",
                {"year": obligation.year, "month": obligation.month},
            )


def _check_incoming_invoice_settlements(
    report: DiagnosticsReport,
    *,
    settlements: dict[int, IncomingInvoiceSettlement],
    incoming_invoices: dict[int, IncomingInvoice],
    bank_transactions: dict[int, BankTransaction],
    cash_entries: dict[int, CashEntry],
    incomes: dict[int, Income],
) -> None:
    target_maps = {
        "bank_transaction_id": bank_transactions,
        "cash_entry_id": cash_entries,
        "income_id": incomes,
    }
    for settlement in settlements.values():
        settlement_id = int(settlement.id)
        if int(settlement.incoming_invoice_id) not in incoming_invoices:
            report.add(
                "error",
                "settlement_missing_invoice",
                "incoming_invoice_settlement",
                settlement_id,
                "Incoming-invoice settlement points to a missing invoice.",
                {"incoming_invoice_id": settlement.incoming_invoice_id},
            )
        expected_fk = SETTLEMENT_LINK_BY_TYPE.get(settlement.settlement_type)
        filled_fks = [
            field
            for field in ("bank_transaction_id", "cash_entry_id", "income_id")
            if getattr(settlement, field) is not None
        ]
        if expected_fk is None:
            report.add(
                "error",
                "settlement_unknown_type",
                "incoming_invoice_settlement",
                settlement_id,
                "Settlement uses an unsupported settlement_type.",
                {"settlement_type": settlement.settlement_type, "filled_fks": filled_fks},
            )
        elif filled_fks != [expected_fk]:
            report.add(
                "error",
                "settlement_invalid_link_shape",
                "incoming_invoice_settlement",
                settlement_id,
                "Settlement must have exactly one FK matching settlement_type.",
                {"settlement_type": settlement.settlement_type, "expected_fk": expected_fk, "filled_fks": filled_fks},
            )
        else:
            target_id = getattr(settlement, expected_fk)
            if int(target_id) not in target_maps[expected_fk]:
                report.add(
                    "error",
                    "settlement_missing_target",
                    "incoming_invoice_settlement",
                    settlement_id,
                    "Settlement points to a missing payment target.",
                    {"settlement_type": settlement.settlement_type, expected_fk: target_id},
                )
        if _decimal(settlement.amount) <= 0:
            report.add(
                "warning",
                "settlement_non_positive_amount",
                "incoming_invoice_settlement",
                settlement_id,
                "Settlement amount should be positive.",
                {"amount": _money(settlement.amount)},
            )


def _check_incoming_invoices(
    report: DiagnosticsReport,
    *,
    incoming_invoices: dict[int, IncomingInvoice],
    expenses: dict[int, Expense],
    projects: dict[int, Project],
    settlement_ids_by_invoice: dict[int, list[int]],
    settlement_sum_by_invoice: dict[int, Decimal],
) -> None:
    for invoice in incoming_invoices.values():
        invoice_id = int(invoice.id)
        amount = _decimal(invoice.amount)
        settled = _decimal(invoice.settled_amount)
        settlements = settlement_ids_by_invoice.get(invoice_id, [])

        if invoice.project_id is not None:
            project = projects.get(int(invoice.project_id))
            if project is None:
                report.add(
                    "error",
                    "incoming_invoice_missing_project",
                    "incoming_invoice",
                    invoice_id,
                    "Incoming invoice points to a missing project.",
                    {"project_id": invoice.project_id},
                )
            elif project.status == "archived":
                report.add(
                    "warning",
                    "incoming_invoice_archived_project",
                    "incoming_invoice",
                    invoice_id,
                    "Incoming invoice points to an archived project.",
                    {"project_id": invoice.project_id, "project_name": project.name},
                )
        if invoice.status != "cancelled" and invoice.expense_id is None:
            report.add(
                "error",
                "incoming_invoice_without_expense",
                "incoming_invoice",
                invoice_id,
                "Active incoming invoice has no linked expense.",
                {"status": invoice.status, "amount": _money(invoice.amount)},
            )
        if invoice.expense_id is not None:
            expense = expenses.get(int(invoice.expense_id))
            if expense is None:
                report.add(
                    "error",
                    "incoming_invoice_missing_expense",
                    "incoming_invoice",
                    invoice_id,
                    "Incoming invoice points to a missing expense.",
                    {"expense_id": invoice.expense_id},
                )
            else:
                if expense.source != "incoming_invoice":
                    report.add(
                        "warning",
                        "incoming_invoice_expense_wrong_source",
                        "incoming_invoice",
                        invoice_id,
                        "Incoming invoice is linked to an expense with unexpected source.",
                        {"expense_id": invoice.expense_id, "expense_source": expense.source},
                    )
                if expense.project_id is not None:
                    expense_project = projects.get(int(expense.project_id))
                    if expense_project is None:
                        report.add(
                            "error",
                            "incoming_invoice_expense_missing_project",
                            "incoming_invoice",
                            invoice_id,
                            "Linked incoming-invoice expense points to a missing project.",
                            {"expense_id": invoice.expense_id, "expense_project_id": expense.project_id},
                        )
                    elif expense_project.status == "archived":
                        report.add(
                            "warning",
                            "incoming_invoice_expense_archived_project",
                            "incoming_invoice",
                            invoice_id,
                            "Linked incoming-invoice expense points to an archived project.",
                            {
                                "expense_id": invoice.expense_id,
                                "expense_project_id": expense.project_id,
                                "project_name": expense_project.name,
                            },
                        )

        expected_sum = settlement_sum_by_invoice.get(invoice_id, Decimal("0"))
        if _is_different(expected_sum, settled):
            report.add(
                "error",
                "incoming_invoice_settled_sum_mismatch",
                "incoming_invoice",
                invoice_id,
                "Invoice settled_amount differs from settlement rows sum.",
                {"settled_amount": _money(settled), "settlement_sum": _money(expected_sum), "settlements": settlements},
            )
        if settled - amount > Decimal("0.01"):
            report.add(
                "error",
                "incoming_invoice_overpaid",
                "incoming_invoice",
                invoice_id,
                "Incoming invoice settled_amount is greater than amount.",
                {"amount": _money(amount), "settled_amount": _money(settled)},
            )
        if invoice.status == "paid" and amount > 0 and settled + Decimal("0.01") < amount:
            report.add(
                "error",
                "incoming_invoice_paid_but_under_settled",
                "incoming_invoice",
                invoice_id,
                "Incoming invoice is paid but settled_amount is lower than amount.",
                {"amount": _money(amount), "settled_amount": _money(settled)},
            )
        if invoice.status == "partial" and (settled <= 0 or settled >= amount):
            report.add(
                "warning",
                "incoming_invoice_partial_amount_inconsistent",
                "incoming_invoice",
                invoice_id,
                "Partial invoice should have settled_amount between zero and amount.",
                {"amount": _money(amount), "settled_amount": _money(settled)},
            )
        if invoice.status == "unpaid" and settled > 0:
            report.add(
                "warning",
                "incoming_invoice_unpaid_with_settled_amount",
                "incoming_invoice",
                invoice_id,
                "Unpaid invoice has non-zero settled_amount.",
                {"settled_amount": _money(settled)},
            )
        if invoice.status in {"partial", "paid"} and amount > 0 and not settlements:
            report.add(
                "warning",
                "incoming_invoice_settled_without_settlement_rows",
                "incoming_invoice",
                invoice_id,
                "Invoice has a settled status but no settlement rows.",
                {"status": invoice.status, "amount": _money(amount), "settled_amount": _money(settled)},
            )


def _check_expenses(
    report: DiagnosticsReport,
    *,
    expenses: dict[int, Expense],
    incoming_expense_ids: set[int],
    receipt_expense_ids: set[int],
) -> None:
    for expense in expenses.values():
        expense_id = int(expense.id)
        if expense.source == "incoming_invoice" and expense_id not in incoming_expense_ids:
            report.add(
                "error",
                "expense_incoming_source_without_invoice",
                "expense",
                expense_id,
                "Expense source is incoming_invoice but no incoming invoice links to it.",
            )
        if expense.source == "receipt" and expense_id not in receipt_expense_ids:
            report.add(
                "error",
                "expense_receipt_source_without_receipt",
                "expense",
                expense_id,
                "Expense source is receipt but no purchase receipt links to it.",
            )


def _check_receipts(
    report: DiagnosticsReport,
    *,
    receipts: dict[int, PurchaseReceipt],
    expenses: dict[int, Expense],
    bank_transactions: dict[int, BankTransaction],
    cash_entries: dict[int, CashEntry],
) -> None:
    bank_tx_by_expense = {
        int(tx.matched_id): tx
        for tx in bank_transactions.values()
        if tx.status == "matched" and tx.matched_type == "expense" and tx.matched_id is not None
    }
    for receipt in receipts.values():
        receipt_id = int(receipt.id)
        linked_expense = expenses.get(int(receipt.expense_id)) if receipt.expense_id is not None else None
        if receipt.expense_id is not None and linked_expense is None:
            report.add(
                "error",
                "receipt_missing_expense",
                "purchase_receipt",
                receipt_id,
                "Purchase receipt points to a missing expense.",
                {"expense_id": receipt.expense_id},
            )
        if receipt.bank_transaction_id is not None and int(receipt.bank_transaction_id) not in bank_transactions:
            report.add(
                "error",
                "receipt_missing_bank_transaction",
                "purchase_receipt",
                receipt_id,
                "Purchase receipt points to a missing bank transaction.",
                {"bank_transaction_id": receipt.bank_transaction_id},
            )
        if receipt.cash_entry_id is not None and int(receipt.cash_entry_id) not in cash_entries:
            report.add(
                "error",
                "receipt_missing_cash_entry",
                "purchase_receipt",
                receipt_id,
                "Purchase receipt points to a missing cash entry.",
                {"cash_entry_id": receipt.cash_entry_id},
            )
        expected_status = _expected_receipt_status(receipt, linked_expense, bank_tx_by_expense)
        if expected_status and receipt.status != expected_status:
            report.add(
                "warning",
                "receipt_status_out_of_sync",
                "purchase_receipt",
                receipt_id,
                "Purchase receipt status is out of sync with linked operations.",
                {"status": receipt.status, "expected_status": expected_status, "expense_id": receipt.expense_id},
            )


def _expected_receipt_status(
    receipt: PurchaseReceipt,
    linked_expense: Expense | None,
    bank_tx_by_expense: dict[int, BankTransaction],
) -> str | None:
    if receipt.expense_id is None:
        return "new"
    if linked_expense is None:
        return None
    if linked_expense.source == "cash":
        return "cash_expense"
    bank_tx = bank_tx_by_expense.get(int(linked_expense.id))
    if bank_tx is not None:
        return "matched_bank"
    if linked_expense.status == "planned":
        return "waiting_bank"
    return "linked_expense"


def _check_cash_entries(
    report: DiagnosticsReport,
    *,
    cash_entries: dict[int, CashEntry],
    expenses: dict[int, Expense],
    bank_transactions: dict[int, BankTransaction],
) -> None:
    for entry in cash_entries.values():
        entry_id = int(entry.id)
        if entry.entry_type not in VALID_CASH_ENTRY_TYPES:
            report.add(
                "warning",
                "cash_entry_unknown_type",
                "cash_entry",
                entry_id,
                "Cash entry uses an unsupported entry_type.",
                {"entry_type": entry.entry_type},
            )
        if entry.expense_id is not None and int(entry.expense_id) not in expenses:
            report.add(
                "error",
                "cash_entry_missing_expense",
                "cash_entry",
                entry_id,
                "Cash entry points to a missing expense.",
                {"expense_id": entry.expense_id},
            )
        if entry.bank_transaction_id is not None and int(entry.bank_transaction_id) not in bank_transactions:
            report.add(
                "error",
                "cash_entry_missing_bank_transaction",
                "cash_entry",
                entry_id,
                "Cash entry points to a missing bank transaction.",
                {"bank_transaction_id": entry.bank_transaction_id},
            )


async def _check_efaktura_import_records(report: DiagnosticsReport, db: AsyncSession) -> None:
    target_ids_by_type: dict[str, set[int]] = {}
    for imported_as, model in EF_IMPORT_MODEL_BY_TYPE.items():
        result = await db.execute(select(model.id))
        target_ids_by_type[imported_as] = {int(row_id) for row_id in result.scalars().all()}

    result = await db.execute(select(EfakturaImportRecord))
    for record in result.scalars().all():
        record_id = int(record.id)
        target_ids = target_ids_by_type.get(record.imported_as)
        if target_ids is None:
            report.add(
                "warning",
                "efaktura_unknown_imported_as",
                "efaktura_import_record",
                record_id,
                "eFaktura import record uses an unsupported imported_as value.",
                {"imported_as": record.imported_as, "imported_record_id": record.imported_record_id},
            )
            continue
        if int(record.imported_record_id) not in target_ids:
            report.add(
                "error",
                "efaktura_missing_imported_record",
                "efaktura_import_record",
                record_id,
                "eFaktura import record points to a missing imported record.",
                {"imported_as": record.imported_as, "imported_record_id": record.imported_record_id},
            )


async def _check_legacy_tables(report: DiagnosticsReport, db: AsyncSession) -> None:
    payment_count = await _count_rows(db, Payment)
    if payment_count:
        report.add(
            "info",
            "legacy_payments_present",
            "payments",
            None,
            "Legacy payments table still contains rows.",
            {"count": payment_count},
        )
    contribution_count = await _count_rows(db, ContributionRates)
    if contribution_count:
        report.add(
            "info",
            "legacy_contribution_rates_present",
            "contribution_rates",
            None,
            "Legacy contribution_rates table still contains rows.",
            {"count": contribution_count},
        )
