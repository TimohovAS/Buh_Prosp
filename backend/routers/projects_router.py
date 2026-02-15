"""Роутер справочника проектов."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.models import Project, User
from backend.schemas import ProjectCreate, ProjectUpdate, ProjectResponse
from backend.auth import get_current_user_required, require_edit_access
from backend.services import allocate_next_project_code

router = APIRouter(prefix="/projects", tags=["projects"])


def _project_status_sort_order():
    """Приоритет: lead/active(0), completed(1), archived(2)."""
    return case(
        (Project.status.in_(["lead", "active"]), 0),
        (Project.status == "completed", 1),
        (Project.status == "archived", 2),
        else_=3,
    )


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
    return [
        ProjectResponse.model_validate(p).model_copy(update={"client_name": p.client.name if p.client else None})
        for p in projects
    ]


@router.post("", response_model=ProjectResponse)
async def create_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Добавить проект. code генерируется автоматически (PR-YYYY-NNNN), если не передан."""
    payload = data.model_dump()
    code_val = payload.get("code")
    if code_val is None or (isinstance(code_val, str) and not code_val.strip()):
        payload["code"] = await allocate_next_project_code(db)
    project = Project(**payload)
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return ProjectResponse.model_validate(project)


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
    resp = ProjectResponse.model_validate(project)
    return resp.model_copy(update={"client_name": project.client.name if project.client else None})


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_edit_access),
):
    """Обновить проект."""
    r = await db.execute(select(Project).where(Project.id == project_id))
    project = r.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Проект не найден")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(project, k, v)
    await db.flush()
    await db.refresh(project)
    return ProjectResponse.model_validate(project)


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
    project.status = "archived"
    await db.flush()
    return {"ok": True}
