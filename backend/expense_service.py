"""Business helpers for expenses."""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db_utils import get_contract_or_404, get_project_or_404, get_unassigned_project_id
from backend.decimal_utils import ZERO_DECIMAL, to_decimal
from backend.models import BankTransaction, CashEntry, Expense, ExpenseItem


class NotFoundError(ValueError):
    """Domain reference was not found."""


async def _get_project_or_error(db: AsyncSession, project_id: int):
    try:
        return await get_project_or_404(db, project_id, exc_cls=ValueError)
    except ValueError as exc:
        if str(exc) == "Project not found":
            raise NotFoundError(str(exc)) from exc
        raise


def _item_field(item, key: str):
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _to_optional_decimal(value):
    if value in (None, ""):
        return None
    return to_decimal(value)


def normalize_expense_items(items) -> list[dict]:
    normalized = []
    for item in items or []:
        name = str(_item_field(item, "name") or "").strip()
        quantity = _to_optional_decimal(_item_field(item, "quantity"))
        unit_price = _to_optional_decimal(_item_field(item, "unit_price"))
        note = str(_item_field(item, "note") or "").strip() or None
        amount_value = _item_field(item, "total_amount")
        if quantity is not None and unit_price is not None:
            amount = to_decimal(quantity * unit_price)
        else:
            amount = to_decimal(amount_value if amount_value not in (None, "") else ZERO_DECIMAL)

        has_payload = (
            bool(name) or quantity is not None or unit_price is not None or amount != ZERO_DECIMAL or bool(note)
        )
        if not has_payload:
            continue
        if not name:
            raise ValueError("Expense item name is required")

        normalized.append(
            {
                "name": name[:500],
                "quantity": quantity,
                "unit_price": unit_price,
                "total_amount": amount,
                "note": note,
            }
        )
    return normalized


def expense_amount_from_items(items: list[dict], fallback) -> object:
    if not items:
        return to_decimal(fallback or ZERO_DECIMAL)
    total = ZERO_DECIMAL
    for item in items:
        total += to_decimal(item["total_amount"] or ZERO_DECIMAL)
    return total


def expense_description_from_items(items: list[dict], fallback: str | None) -> str:
    text = str(fallback or "").strip()
    if text:
        return text[:500]
    if items:
        return "; ".join(item["name"] for item in items)[:500]
    return ""


def build_expense_item_models(items: list[dict]) -> list[ExpenseItem]:
    return [
        ExpenseItem(
            line_no=index + 1,
            name=item["name"],
            quantity=item["quantity"],
            unit_price=item["unit_price"],
            total_amount=item["total_amount"],
            note=item["note"],
        )
        for index, item in enumerate(items)
    ]


async def resolve_expense_links(
    db: AsyncSession,
    project_id: int | None,
    contract_id: int | None,
) -> tuple[int | None, int | None]:
    resolved_project_id = project_id or await get_unassigned_project_id(db)
    resolved_contract_id = contract_id
    project_validated = False

    if resolved_contract_id is not None:
        contract = await get_contract_or_404(db, resolved_contract_id, exc_cls=NotFoundError)
        if contract.project_id is None:
            if resolved_project_id is None:
                raise ValueError("Select a project before linking this contract")
            await _get_project_or_error(db, resolved_project_id)
            project_validated = True
            contract.project_id = resolved_project_id
            await db.flush()
        resolved_project_id = contract.project_id

    if resolved_project_id is not None and not project_validated:
        await _get_project_or_error(db, resolved_project_id)

    return resolved_project_id, resolved_contract_id


async def clear_contract_if_project_mismatch(db: AsyncSession, expense: Expense, project_id: int | None) -> None:
    if not expense.contract_id or project_id is None:
        return
    contract = await get_contract_or_404(db, expense.contract_id, exc_cls=NotFoundError)
    if contract.project_id != project_id:
        expense.contract_id = None


def is_reversal_row(expense: Expense) -> bool:
    return (
        bool(expense.reversal_of_id)
        or getattr(expense, "status", None) == "reversed"
        or to_decimal(expense.amount or ZERO_DECIMAL) < ZERO_DECIMAL
    )


async def sync_cash_entry_from_expense(db: AsyncSession, expense: Expense) -> None:
    result = await db.execute(select(CashEntry).where(CashEntry.expense_id == expense.id))
    cash_entry = result.scalar_one_or_none()
    if not cash_entry:
        return

    cash_entry.date = expense.paid_date or expense.date
    cash_entry.amount = to_decimal(expense.amount or ZERO_DECIMAL)
    cash_entry.currency = expense.currency or "RSD"
    cash_entry.description = (expense.description or "")[:500]
    cash_entry.note = expense.note


async def sync_bank_transactions_from_expense(db: AsyncSession, expense: Expense) -> None:
    await db.execute(
        update(BankTransaction)
        .where(BankTransaction.matched_type == "expense", BankTransaction.matched_id == expense.id)
        .values(project_id=expense.project_id)
    )

    if not expense.bank_reference or is_reversal_row(expense):
        return

    amount = abs(to_decimal(expense.amount or ZERO_DECIMAL))
    result = await db.execute(
        select(BankTransaction).where(
            BankTransaction.bank_reference == expense.bank_reference,
            BankTransaction.direction == "out",
        )
    )
    candidates = [tx for tx in result.scalars().all() if abs(to_decimal(tx.amount or ZERO_DECIMAL)) == amount]
    if len(candidates) != 1:
        return

    tx = candidates[0]
    tx.status = "matched"
    tx.matched_type = "expense"
    tx.matched_id = expense.id
    tx.project_id = expense.project_id
