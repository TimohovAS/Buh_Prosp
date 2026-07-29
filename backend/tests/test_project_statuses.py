from types import SimpleNamespace

from backend.finance_service import get_finance_by_project
from backend.routers.projects_router import delete_project, list_projects


async def test_project_list_hides_completed_by_default(db_session, make_project):
    active = await make_project(db_session, code="PR-ACTIVE", name="Active")
    completed = await make_project(
        db_session,
        code="PR-DONE",
        name="Completed",
        status="completed",
    )

    visible = await list_projects(
        show_inactive=False,
        show_archived=None,
        db=db_session,
        current_user=SimpleNamespace(id=1),
    )
    all_projects = await list_projects(
        show_inactive=True,
        show_archived=None,
        db=db_session,
        current_user=SimpleNamespace(id=1),
    )

    assert [project.id for project in visible] == [active.id]
    assert {project.id for project in all_projects} == {active.id, completed.id}


async def test_finance_by_project_uses_same_inactive_filter(db_session, make_project):
    active = await make_project(db_session, code="PR-ACTIVE", name="Active")
    completed = await make_project(
        db_session,
        code="PR-DONE",
        name="Completed",
        status="completed",
    )

    visible = await get_finance_by_project(
        db_session,
        date_from=active.created_at.date(),
        date_to=active.created_at.date(),
        include_inactive=False,
    )
    all_projects = await get_finance_by_project(
        db_session,
        date_from=active.created_at.date(),
        date_to=active.created_at.date(),
        include_inactive=True,
    )

    visible_ids = {row["project_id"] for row in visible["by_project"]}
    all_ids = {row["project_id"] for row in all_projects["by_project"]}
    assert active.id in visible_ids
    assert completed.id not in visible_ids
    assert {active.id, completed.id}.issubset(all_ids)


async def test_legacy_delete_endpoint_is_idempotent(db_session, make_project):
    project = await make_project(db_session, code="PR-DELETE", name="Project")

    first = await delete_project(project.id, db_session, SimpleNamespace(id=1))
    second = await delete_project(project.id, db_session, SimpleNamespace(id=1))

    assert first == {"ok": True}
    assert second == {"ok": True}
    assert project.status == "completed"
