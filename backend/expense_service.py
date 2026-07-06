"""Business helpers for expenses."""

from collections import defaultdict
from datetime import date
from typing import Optional
import re

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.cash_service import CASH_TRANSFER_SOURCE
from backend.db_utils import get_contract_or_404, get_project_or_404, get_unassigned_project_id
from backend.decimal_utils import ZERO_DECIMAL, money_gt, to_decimal
from backend.models import BankTransaction, CashEntry, Expense, ExpenseItem, MonthlyObligation
from backend.schemas import ExpenseDuplicateGroup, ExpenseDuplicateItem
from backend.state_machine import mark_expense_paid

EFAKTURA_IMPORT_SOURCE = "efaktura_import"
RECEIPT_SOURCE = "receipt"


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


def visible_expense_condition():
    return or_(Expense.status != "planned", Expense.source.in_([EFAKTURA_IMPORT_SOURCE, RECEIPT_SOURCE]))


def _normalize_duplicate_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _amount_key(value: float | int | None) -> str:
    return f"{abs(to_decimal(value or ZERO_DECIMAL)):.2f}"


def _is_active_duplicate_candidate(expense: Expense) -> bool:
    if is_reversal_row(expense):
        return False
    if getattr(expense, "reversed_expense_id", None):
        return False
    if getattr(expense, "status", None) == "planned":
        return False
    return money_gt(expense.amount or ZERO_DECIMAL)


async def load_expenses_for_period(
    db: AsyncSession,
    year: Optional[int],
    month: Optional[int],
) -> list[Expense]:
    query = (
        select(Expense)
        .where(
            Expense.source != CASH_TRANSFER_SOURCE,
            visible_expense_condition(),
        )
        .order_by(Expense.date.desc(), Expense.id.desc())
    )
    if year:
        query = query.where(Expense.date >= date(year, 1, 1), Expense.date <= date(year, 12, 31))
    if month and year:
        import calendar

        last_day = calendar.monthrange(year, month)[1]
        query = query.where(Expense.date >= date(year, month, 1), Expense.date <= date(year, month, last_day))
    result = await db.execute(query)
    return list(result.scalars().all())


async def find_expense_duplicate_groups(
    db: AsyncSession,
    year: Optional[int],
    month: Optional[int],
) -> list[ExpenseDuplicateGroup]:
    items = [item for item in await load_expenses_for_period(db, year, month) if _is_active_duplicate_candidate(item)]
    by_reference: dict[tuple[str, str], list[Expense]] = defaultdict(list)
    by_description: dict[tuple[str, str, date | None], list[Expense]] = defaultdict(list)

    for item in items:
        amount_key = _amount_key(item.amount)
        normalized_reference = _normalize_duplicate_text(item.bank_reference)
        normalized_description = _normalize_duplicate_text(item.description)
        if normalized_reference:
            by_reference[(normalized_reference, amount_key)].append(item)
        elif normalized_description:
            by_description[(normalized_description, amount_key, item.date)].append(item)

    groups: list[ExpenseDuplicateGroup] = []
    seen_ids: set[tuple[int, ...]] = set()

    def add_group(
        reason: str, expenses: list[Expense], payment_reference: str | None = None, description: str | None = None
    ) -> None:
        ids = tuple(sorted(expense.id for expense in expenses))
        if len(ids) < 2 or ids in seen_ids:
            return
        seen_ids.add(ids)
        sorted_items = sorted(expenses, key=lambda expense: (expense.date, expense.id))
        groups.append(
            ExpenseDuplicateGroup(
                reason=reason,
                amount=to_decimal(sorted_items[0].amount or ZERO_DECIMAL),
                payment_reference=payment_reference,
                description=description,
                item_count=len(sorted_items),
                items=[ExpenseDuplicateItem.model_validate(item) for item in sorted_items],
            )
        )

    for (_, _), expenses in sorted(by_reference.items(), key=lambda item: item[0]):
        if len(expenses) > 1:
            add_group("payment_reference", expenses, payment_reference=expenses[0].bank_reference)

    for (_, _, _), expenses in sorted(by_description.items(), key=lambda item: item[0]):
        if len(expenses) > 1:
            add_group("description_amount", expenses, description=expenses[0].description)

    groups.sort(key=lambda group: (group.items[0].date if group.items else date.min, group.item_count), reverse=True)
    return groups


def _non_empty_payment_refs(expenses: list[Expense]) -> set[str]:
    refs: set[str] = set()
    for expense in expenses:
        normalized_reference = _normalize_duplicate_text(getattr(expense, "bank_reference", None))
        if normalized_reference:
            refs.add(normalized_reference)
    return refs


def _merge_notes(primary: str | None, secondary: str | None) -> str | None:
    left = (primary or "").strip()
    right = (secondary or "").strip()
    if not left:
        return right or None
    if not right or right in left:
        return left
    if left in right:
        return right
    return f"{left}\n{right}"


async def _merge_expense_links(
    db: AsyncSession,
    keep: Expense,
    duplicate: Expense,
) -> None:
    await db.execute(
        update(BankTransaction)
        .where(BankTransaction.matched_type == "expense", BankTransaction.matched_id == duplicate.id)
        .values(matched_id=keep.id)
    )
    await db.execute(
        update(MonthlyObligation).where(MonthlyObligation.expense_id == duplicate.id).values(expense_id=keep.id)
    )


async def merge_duplicate_expenses(db: AsyncSession, keep_id: int, merge_ids: list[int]) -> Expense:
    normalized_merge_ids = [expense_id for expense_id in merge_ids if expense_id != keep_id]
    if not normalized_merge_ids:
        raise ValueError("No duplicate expenses selected for merge")

    result = await db.execute(select(Expense).where(Expense.id.in_([keep_id, *normalized_merge_ids])))
    items = {item.id: item for item in result.scalars().all()}
    keep = items.get(keep_id)
    if not keep:
        raise NotFoundError("Expense to keep was not found")
    if is_reversal_row(keep) or getattr(keep, "reversed_expense_id", None):
        raise ValueError("Reversal expenses cannot be merged")

    duplicates: list[Expense] = []
    for expense_id in normalized_merge_ids:
        duplicate = items.get(expense_id)
        if not duplicate:
            raise NotFoundError(f"Expense {expense_id} was not found")
        if is_reversal_row(duplicate) or getattr(duplicate, "reversed_expense_id", None):
            raise ValueError("Reversal expenses cannot be merged")
        duplicates.append(duplicate)

    payment_refs = _non_empty_payment_refs([keep, *duplicates])
    if len(payment_refs) > 1:
        raise ValueError("Expenses with different payment references cannot be merged")

    unassigned_project_id = await get_unassigned_project_id(db)
    for duplicate in duplicates:
        await _merge_expense_links(db, keep, duplicate)

        if not keep.bank_reference and duplicate.bank_reference:
            keep.bank_reference = duplicate.bank_reference
        if keep.category_id is None and duplicate.category_id is not None:
            keep.category_id = duplicate.category_id
        if not keep.category and duplicate.category:
            keep.category = duplicate.category
        if keep.contract_id is None and duplicate.contract_id is not None:
            keep.contract_id = duplicate.contract_id
        if keep.project_id in (None, unassigned_project_id) and duplicate.project_id not in (
            None,
            unassigned_project_id,
        ):
            keep.project_id = duplicate.project_id
        if keep.paid_date is None and duplicate.paid_date is not None:
            keep.paid_date = duplicate.paid_date
        if keep.status != "paid" and duplicate.status == "paid":
            mark_expense_paid(keep, paid_date=keep.paid_date, allow_same=True)
        keep.note = _merge_notes(keep.note, duplicate.note)

        await db.execute(delete(ExpenseItem).where(ExpenseItem.expense_id == duplicate.id))
        await db.delete(duplicate)

    if keep.project_id is not None:
        await clear_contract_if_project_mismatch(db, keep, keep.project_id)
        await sync_bank_transactions_from_expense(db, keep)

    await db.flush()
    return keep


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
