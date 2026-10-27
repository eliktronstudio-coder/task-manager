from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.store import Store
from app.models.task import Task, TaskTemplate, TaskStatus
from app.schemas.store import StoreCreate, StoreUpdate, StoreOut

router = APIRouter(prefix="/stores", tags=["stores"])


async def _create_tasks_from_templates(store: Store, db: AsyncSession):
    """При создании магазина автоматически создаёт задачи из активных шаблонов."""
    result = await db.execute(
        select(TaskTemplate).where(TaskTemplate.is_active.is_(True)).order_by(TaskTemplate.sort_order)
    )
    templates = result.scalars().all()
    for tmpl in templates:
        task = Task(
            title=tmpl.name,
            section=tmpl.section,
            subsection=tmpl.subsection,
            store_id=store.id,
            template_id=tmpl.id,
            status=TaskStatus.IN_PROGRESS,
        )
        db.add(task)
    await db.flush()


@router.get("/", response_model=list[StoreOut])
async def list_stores(active_only: bool = True, db: AsyncSession = Depends(get_db)):
    q = select(Store)
    if active_only:
        q = q.where(Store.is_active.is_(True))
    result = await db.execute(q.order_by(Store.name))
    return result.scalars().all()


@router.post("/", response_model=StoreOut, status_code=201)
async def create_store(
    data: StoreCreate,
    auto_tasks: bool = True,
    db: AsyncSession = Depends(get_db),
):
    store = Store(**data.model_dump())
    db.add(store)
    await db.flush()

    if auto_tasks:
        await _create_tasks_from_templates(store, db)

    await db.commit()
    await db.refresh(store)
    return store


@router.get("/{store_id}", response_model=StoreOut)
async def get_store(store_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Store).where(Store.id == store_id))
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(404, "Магазин не найден")
    return store


@router.patch("/{store_id}", response_model=StoreOut)
async def update_store(store_id: int, data: StoreUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Store).where(Store.id == store_id))
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(404, "Магазин не найден")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(store, field, value)

    await db.commit()
    await db.refresh(store)
    return store


@router.get("/{store_id}/summary")
async def store_summary(store_id: int, db: AsyncSession = Depends(get_db)):
    """Сводка по магазину для руководителя."""
    from datetime import datetime
    from sqlalchemy import and_

    result = await db.execute(select(Store).where(Store.id == store_id))
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(404, "Магазин не найден")

    now = datetime.utcnow()
    tasks_result = await db.execute(select(Task).where(Task.store_id == store_id))
    tasks = tasks_result.scalars().all()

    total = len(tasks)
    closed = sum(1 for t in tasks if t.status == TaskStatus.CLOSED)
    critical = [t for t in tasks if t.status == TaskStatus.CRITICAL]
    overdue = [t for t in tasks if t.deadline and t.deadline < now and t.status != TaskStatus.CLOSED]

    return {
        "store_id": store_id,
        "store_name": store.name,
        "total_tasks": total,
        "closed_tasks": closed,
        "open_tasks": total - closed,
        "critical_count": len(critical),
        "overdue_count": len(overdue),
        "critical_tasks": [{"id": t.id, "title": t.title} for t in critical],
        "overdue_tasks": [{"id": t.id, "title": t.title, "deadline": t.deadline} for t in overdue],
    }
