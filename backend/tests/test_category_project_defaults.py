"""Дефолтный проект категории — подстановка, а не перебивка выбора пользователя."""

from backend.db_utils import resolve_category_expense_links
from backend.models import TransactionCategory


async def _make_category(db, *, default_project_id=None, group="expense"):
    category = TransactionCategory(
        name_ru="Транспорт",
        name_sr="Transport",
        category_type="expense",
        category_group=group,
        default_project_id=default_project_id,
    )
    db.add(category)
    await db.flush()
    return category


async def test_explicit_project_wins_over_category_default(db_session, make_project):
    """Расход по «транспорту» можно привязать к реальному проекту."""
    transport = await make_project(db_session, code="INT-TRANSPORT")
    real_project = await make_project(db_session, code="PR-2026-0001")
    category = await _make_category(db_session, default_project_id=transport.id)

    project_id, contract_id, _ = await resolve_category_expense_links(db_session, category.id, real_project.id, None)

    assert project_id == real_project.id
    assert contract_id is None


async def test_category_default_fills_missing_project(db_session, make_project):
    """Без явного выбора дефолт категории по-прежнему подставляется."""
    transport = await make_project(db_session, code="INT-TRANSPORT")
    category = await _make_category(db_session, default_project_id=transport.id)

    project_id, _, _ = await resolve_category_expense_links(db_session, category.id, None, None)

    assert project_id == transport.id


async def test_category_without_default_keeps_project(db_session, make_project):
    project = await make_project(db_session, code="PR-2026-0002")
    category = await _make_category(db_session)

    project_id, _, _ = await resolve_category_expense_links(db_session, category.id, project.id, None)

    assert project_id == project.id


async def test_tax_group_still_flagged(db_session, make_project):
    project = await make_project(db_session, code="PR-2026-0003")
    category = await _make_category(db_session, group="tax")

    _, _, is_tax_related = await resolve_category_expense_links(db_session, category.id, project.id, None)

    assert is_tax_related is True
