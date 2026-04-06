"""Роутер справочника проектов."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.auth import get_current_user_required, require_edit_access
from backend.database import get_db
from backend.finance_service import get_project_movement_bounds
from backend.models import Project, User
from backend.schemas import ProjectCreate, ProjectResponse, ProjectUpdate
from backend.services import allocate_next_project_code
from backend.state_machine import InvalidStatusTransition, initialize_project_status, transition_project_status

router = APIRouter(prefix="/projects", tags=["projects"])


def _project_status_sort_order():
    """Приоритет: lead/active(0), completed(1), archived(2)."""
    return case(
        (Project.status.in_(["lead", "active"]), 0),
        (Project.status == "completed", 1),
        (Project.status == "archived", 2),
        else_=3,
    )


def _project_response_with_meta(project: Project, movement_bounds: dict[int, dict] | None = None) -> ProjectResponse:
    movement_bounds = movement_bounds or {}
    return ProjectResponse.model_validate(project).model_copy(update={
        "client_name": project.client.name if project.client else None,
        **movement_bounds.get(project.id, {}),
    })


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    show_archived: bool = Query(False, description="Показывать архивированные"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Список проектов. Сортировка: active/lead → completed → archived, затем по name."""
    q = select(Project).options(selectinload(Project.client)).order_by(_project_status_sort_order(), Project.name)
    if not show_archived:
        q = q.where(Project.status != "archived")
    result = await db.execute(q)
    projects = result.scalars().all()
    movement_bounds = await get_project_movement_bounds(db, [project.id for project in projects])
    return [_project_response_with_meta(project, movement_bounds) for project in projects]


@router.post("", response_model=ProjectResponse)
async def create_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Добавить проект. code генерируется автоматически (PR-YYYY-NNNN), если не передан."""
    payload = data.model_dump()
    code_val = payload.get("code")
    status_val = payload.pop("status", "active")
    if code_val is None or (isinstance(code_val, str) and not code_val.strip()):
        payload["code"] = await allocate_next_project_code(db)
    project = Project(**payload)
    try:
        initialize_project_status(project, status_val)
    except InvalidStatusTransition as exc:
        raise HTTPException(400, str(exc)) from exc
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return _project_response_with_meta(project)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Получить проект."""
    r = await db.execute(select(Project).options(selectinload(Project.client)).where(Project.id == project_id))
    project = r.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Проект не найден")
    movement_bounds = await get_project_movement_bounds(db, [project.id])
    return _project_response_with_meta(project, movement_bounds)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Обновить проект."""
    r = await db.execute(select(Project).options(selectinload(Project.client)).where(Project.id == project_id))
    project = r.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Проект не найден")
    dump = data.model_dump(exclude_unset=True)
    next_status = dump.pop("status", None)
    for key, value in dump.items():
        setattr(project, key, value)
    if next_status is not None:
        try:
            transition_project_status(project, next_status, allow_same=True)
        except InvalidStatusTransition as exc:
            raise HTTPException(400, str(exc)) from exc
    await db.commit()
    await db.refresh(project)
    movement_bounds = await get_project_movement_bounds(db, [project.id])
    return _project_response_with_meta(project, movement_bounds)


@router.delete("/{project_id}")
async def delete_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Удалить проект (мягкое удаление — деактивировать)."""
    r = await db.execute(select(Project).where(Project.id == project_id))
    project = r.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Проект не найден")
    try:
        transition_project_status(project, "archived", allow_same=False)
    except InvalidStatusTransition as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return {"ok": True}
