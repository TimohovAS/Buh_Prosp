"""Shared DB helpers used across routers and services.

Helpers accept an optional `exc_cls` kwarg so service-layer callers can
surface domain-specific exceptions (e.g. `ValueError` subclasses) while
routers keep the default `HTTPException` behavior.
"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Contract, Project, TransactionCategory

UNASSIGNED_PROJECT_CODE = "INT-UNASSIGNED"


def _raise(exc_cls: type[Exception], message: str, status: int) -> None:
    if exc_cls is HTTPException or (isinstance(exc_cls, type) and issubclass(exc_cls, HTTPException)):
        raise HTTPException(status, message)
    raise exc_cls(message)


async def get_unassigned_project_id(db: AsyncSession) -> int | None:
    """Return id of the INT-UNASSIGNED project or None."""
    result = await db.execute(select(Project).where(Project.code == UNASSIGNED_PROJECT_CODE))
    project = result.scalar_one_or_none()
    return project.id if project else None


async def get_project_or_404(
    db: AsyncSession,
    project_id: int,
    *,
    exc_cls: type[Exception] = HTTPException,
    inactive_exc_cls: type[Exception] | None = None,
    allow_completed: bool = False,
) -> Project:
    """Fetch a project; reject completed projects unless explicitly allowed for historical use."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        _raise(exc_cls, "Project not found", 404)
    if not allow_completed and project.status == "completed" and project.code != UNASSIGNED_PROJECT_CODE:
        _raise(inactive_exc_cls or exc_cls, "Cannot use completed project", 400)
    return project


async def get_contract_or_404(
    db: AsyncSession,
    contract_id: int,
    *,
    exc_cls: type[Exception] = HTTPException,
) -> Contract:
    """Fetch a contract; raise `exc_cls` if missing."""
    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()
    if not contract:
        _raise(exc_cls, "Contract not found", 404)
    return contract


async def resolve_project_contract_links(
    db: AsyncSession,
    project_id: int | None,
    contract_id: int | None,
    *,
    not_found_exc_cls: type[Exception] = HTTPException,
    validation_exc_cls: type[Exception] = HTTPException,
    allow_completed: bool = False,
) -> tuple[int | None, int | None]:
    resolved_project_id = project_id or await get_unassigned_project_id(db)
    requested_project_id = resolved_project_id
    resolved_contract_id = contract_id
    project_validated = False

    if resolved_contract_id is not None:
        contract = await get_contract_or_404(db, resolved_contract_id, exc_cls=not_found_exc_cls)
        if contract.project_id is None:
            if resolved_project_id is None:
                _raise(validation_exc_cls, "Select a project before linking this contract", 400)
            await get_project_or_404(
                db,
                resolved_project_id,
                exc_cls=not_found_exc_cls,
                inactive_exc_cls=validation_exc_cls,
                allow_completed=False,
            )
            project_validated = True
            contract.project_id = resolved_project_id
            await db.flush()
        resolved_project_id = contract.project_id

    if resolved_project_id is not None and not project_validated:
        await get_project_or_404(
            db,
            resolved_project_id,
            exc_cls=not_found_exc_cls,
            inactive_exc_cls=validation_exc_cls,
            allow_completed=allow_completed and resolved_project_id == requested_project_id,
        )

    return resolved_project_id, resolved_contract_id


async def get_category_or_none(db: AsyncSession, category_id: int | None) -> TransactionCategory | None:
    """Fetch a category by id or return None if id is None/missing."""
    if category_id is None:
        return None
    result = await db.execute(select(TransactionCategory).where(TransactionCategory.id == category_id))
    return result.scalar_one_or_none()


async def get_category_or_404(
    db: AsyncSession,
    category_id: int,
    *,
    exc_cls: type[Exception] = HTTPException,
) -> TransactionCategory:
    """Fetch a category; raise `exc_cls` if missing."""
    result = await db.execute(select(TransactionCategory).where(TransactionCategory.id == category_id))
    category = result.scalar_one_or_none()
    if not category:
        _raise(exc_cls, "Category not found", 404)
    return category


async def resolve_category_expense_links(
    db: AsyncSession,
    category_id: int | None,
    project_id: int | None,
    contract_id: int | None,
    *,
    strict: bool = False,
    exc_cls: type[Exception] = HTTPException,
) -> tuple[int | None, int | None, bool]:
    """Apply category defaults to (project_id, contract_id); return also is_tax_related.

    When `strict=True`, a non-null `category_id` that is missing in the DB will
    raise `exc_cls` (mirrors bank_transactions_router's historical behavior).
    Otherwise, missing categories are treated as "no defaults to apply".
    """
    if category_id is None:
        return project_id, contract_id, False

    if strict:
        category = await get_category_or_404(db, category_id, exc_cls=exc_cls)
    else:
        category = await get_category_or_none(db, category_id)
        if not category:
            return project_id, contract_id, False

    resolved_project_id = category.default_project_id or project_id
    resolved_contract_id = contract_id
    is_tax_related = category.category_group == "tax"

    if category.default_project_id and resolved_contract_id is not None:
        contract = await get_contract_or_404(db, resolved_contract_id, exc_cls=exc_cls)
        if contract.project_id is not None and contract.project_id != category.default_project_id:
            resolved_contract_id = None

    return resolved_project_id, resolved_contract_id, is_tax_related
