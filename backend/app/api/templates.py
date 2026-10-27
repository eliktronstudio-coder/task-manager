from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.task import TaskTemplate, TaskSection
from app.schemas.task import TaskTemplateCreate, TaskTemplateUpdate, TaskTemplateOut

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("/", response_model=list[TaskTemplateOut])
async def list_templates(
    section: TaskSection | None = None,
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
):
    q = select(TaskTemplate)
    if active_only:
        q = q.where(TaskTemplate.is_active.is_(True))
    if section:
        q = q.where(TaskTemplate.section == section)
    result = await db.execute(q.order_by(TaskTemplate.section, TaskTemplate.sort_order, TaskTemplate.id))
    return result.scalars().all()


@router.post("/", response_model=TaskTemplateOut, status_code=201)
async def create_template(data: TaskTemplateCreate, db: AsyncSession = Depends(get_db)):
    tmpl = TaskTemplate(**data.model_dump())
    db.add(tmpl)
    await db.commit()
    await db.refresh(tmpl)
    return tmpl


@router.patch("/{template_id}", response_model=TaskTemplateOut)
async def update_template(
    template_id: int, data: TaskTemplateUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(TaskTemplate).where(TaskTemplate.id == template_id))
    tmpl = result.scalar_one_or_none()
    if not tmpl:
        raise HTTPException(404, "Шаблон не найден")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(tmpl, field, value)

    await db.commit()
    await db.refresh(tmpl)
    return tmpl


@router.delete("/{template_id}", status_code=204)
async def hide_template(template_id: int, db: AsyncSession = Depends(get_db)):
    """Скрыть (мягкое удаление) — is_active = False."""
    result = await db.execute(select(TaskTemplate).where(TaskTemplate.id == template_id))
    tmpl = result.scalar_one_or_none()
    if not tmpl:
        raise HTTPException(404, "Шаблон не найден")
    tmpl.is_active = False
    await db.commit()
