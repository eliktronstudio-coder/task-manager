from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.task import Task, TaskStatus, TaskSection
from app.models.employee import Employee
from app.models.store import Store
from app.models.history import HistoryEntry
from app.models.reminder import Reminder
from app.schemas.task import TaskCreate, TaskUpdate, TaskOut, TaskListItem
from app.services import notifications
from app.services.scheduler import schedule_reminder, cancel_reminders_for_task
from app.services.auth import current_employee

router = APIRouter(prefix="/tasks", tags=["tasks"])


async def _get_admins(db: AsyncSession) -> list[Employee]:
    result = await db.execute(
        select(Employee)
        .where(and_(Employee.manager_filter(), Employee.is_active.is_(True)))
        .options(selectinload(Employee.notification_settings))
    )
    return result.scalars().all()


async def _load_task(task_id: int, db: AsyncSession) -> Task:
    result = await db.execute(
        select(Task)
        .where(Task.id == task_id)
        .options(
            selectinload(Task.assignee).selectinload(Employee.notification_settings),
            selectinload(Task.creator).selectinload(Employee.notification_settings),
            selectinload(Task.store),
            selectinload(Task.reminders),
        )
        # без этого после смены исполнителя в ответе остаётся старый, уже загруженный в сессию
        .execution_options(populate_existing=True)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Задача не найдена")
    return task


def _require_actor(actor: Optional[Employee]):
    if not actor:
        raise HTTPException(401, "Откройте приложение через бота в Telegram")


def _fmt(value) -> str:
    return value.value if isinstance(value, Enum) else str(value)


def _add_history(db: AsyncSession, task_id: int, actor_id: Optional[int], field: str,
                 old_val: Optional[str], new_val: Optional[str], note: Optional[str] = None):
    entry = HistoryEntry(
        task_id=task_id, actor_id=actor_id, field=field,
        old_value=old_val, new_value=new_val, note=note,
    )
    db.add(entry)


@router.get("/", response_model=list[TaskListItem])
async def list_tasks(
    assignee_id: Optional[int] = None,
    store_id: Optional[int] = None,
    status: Optional[TaskStatus] = None,
    section: Optional[TaskSection] = None,
    overdue_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    q = select(Task).options(
        selectinload(Task.assignee),
        selectinload(Task.store),
    )
    filters = []
    if assignee_id:
        filters.append(Task.assignee_id == assignee_id)
    if store_id:
        filters.append(Task.store_id == store_id)
    if status:
        filters.append(Task.status == status)
    if section:
        filters.append(Task.section == section)
    if overdue_only:
        filters.append(Task.deadline < datetime.utcnow())
        filters.append(Task.status != TaskStatus.CLOSED)
    if filters:
        q = q.where(and_(*filters))
    q = q.order_by(Task.deadline.asc().nullslast(), Task.created_at.desc())
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/", response_model=TaskOut, status_code=201)
async def create_task(
    data: TaskCreate,
    creator: Optional[Employee] = Depends(current_employee),
    db: AsyncSession = Depends(get_db),
):
    _require_actor(creator)
    if not creator.is_manager and data.assignee_id not in (None, creator.id):
        raise HTTPException(403, "Назначать задачи другим может только руководитель")

    task = Task(
        **data.model_dump(exclude={"template_id"}),
        creator_id=creator.id if creator else None,
        template_id=data.template_id,
    )
    db.add(task)
    await db.flush()

    _add_history(db, task.id, creator.id if creator else None, "created", None, task.title)

    await db.commit()
    task = await _load_task(task.id, db)

    # Уведомление исполнителю
    if task.assignee:
        store_name = task.store.name if task.store else "?"
        await notifications.notify_new_task(task.assignee, task, store_name)

    return task


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)):
    return await _load_task(task_id, db)


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: int,
    data: TaskUpdate,
    actor: Optional[Employee] = Depends(current_employee),
    db: AsyncSession = Depends(get_db),
):
    task = await _load_task(task_id, db)
    _require_actor(actor)
    changes = data.model_dump(exclude_none=True)
    if not actor.is_manager:
        if task.assignee_id != actor.id:
            raise HTTPException(403, "Менять можно только свои задачи")
        if changes.get("assignee_id", actor.id) != actor.id:
            raise HTTPException(403, "Назначать задачи другим может только руководитель")

    admins = await _get_admins(db)
    store_name = task.store.name if task.store else "?"

    notify_status = None
    notify_deadline = False
    notify_assignee = False
    notify_critical = False

    for field, new_val in changes.items():
        old_val = getattr(task, field)

        if field == "status" and old_val != new_val:
            notify_status = (_fmt(old_val), _fmt(new_val))
            if new_val == TaskStatus.CRITICAL:
                notify_critical = True

        if field == "deadline" and old_val != new_val:
            notify_deadline = True
            # Пересчитываем напоминания
            await cancel_reminders_for_task(task_id)

        if field == "assignee_id" and old_val != new_val:
            notify_assignee = True

        _add_history(
            db, task_id, actor.id if actor else None, field,
            _fmt(old_val) if old_val else None,
            _fmt(new_val) if new_val else None,
        )
        setattr(task, field, new_val)

    task.updated_at = datetime.utcnow()
    await db.commit()
    task = await _load_task(task_id, db)

    # Уведомления
    if task.assignee:
        if notify_status:
            await notifications.notify_status_changed(task.assignee, task, store_name, notify_status[1])
        if notify_deadline:
            await notifications.notify_deadline_changed(task.assignee, task, store_name)
        if notify_critical:
            await notifications.notify_critical(task.assignee, task, store_name, admins)

    if notify_assignee and task.assignee:
        await notifications.notify_new_task(task.assignee, task, store_name)

    return task


@router.post("/{task_id}/take", response_model=TaskOut)
async def take_task(
    task_id: int,
    actor: Optional[Employee] = Depends(current_employee),
    db: AsyncSession = Depends(get_db),
):
    """Взять задачу коллеги на себя (ИС, НОЗ и руководитель)."""
    task = await _load_task(task_id, db)
    _require_actor(actor)
    if not actor.can_take_tasks:
        raise HTTPException(403, "Брать задачи коллег может только ИС или руководитель")
    if task.status == TaskStatus.CLOSED:
        raise HTTPException(400, "Задача уже закрыта")
    if task.assignee_id == actor.id:
        return task

    previous = task.assignee
    _add_history(
        db, task_id, actor.id, "assignee_id",
        str(previous.id) if previous else None, str(actor.id), note="взял задачу на себя",
    )
    task.assignee_id = actor.id
    task.updated_at = datetime.utcnow()
    await db.commit()
    task = await _load_task(task_id, db)

    if previous:
        store_name = task.store.name if task.store else "?"
        await notifications.notify_task_taken(previous, task, store_name, actor.full_name)
    return task


@router.get("/{task_id}/history")
async def task_history(task_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(HistoryEntry)
        .where(HistoryEntry.task_id == task_id)
        .options(selectinload(HistoryEntry.actor))
        .order_by(HistoryEntry.created_at.asc())
    )
    entries = result.scalars().all()
    return [
        {
            "id": e.id,
            "field": e.field,
            "old_value": e.old_value,
            "new_value": e.new_value,
            "note": e.note,
            "actor": e.actor.full_name if e.actor else "Система",
            "created_at": e.created_at,
        }
        for e in entries
    ]


@router.post("/{task_id}/reminders")
async def add_reminder(
    task_id: int,
    fire_at: datetime,
    reminder_type: str = "custom",
    db: AsyncSession = Depends(get_db),
):
    """Добавить напоминание к задаче."""
    task = await _load_task(task_id, db)
    if task.status == TaskStatus.CLOSED:
        raise HTTPException(400, "Нельзя добавить напоминание к закрытой задаче")

    rid = await schedule_reminder(task_id, fire_at, reminder_type)
    return {"id": rid, "fire_at": fire_at, "reminder_type": reminder_type}


@router.post("/{task_id}/reminders/preset")
async def add_preset_reminder(
    task_id: int,
    preset: str = Query(..., description="1h,2h,3h,1d,2d,3d"),
    db: AsyncSession = Depends(get_db),
):
    """Добавить напоминание по пресету (за X часов/дней до дедлайна)."""
    task = await _load_task(task_id, db)
    if not task.deadline:
        raise HTTPException(400, "У задачи не указан срок выполнения")
    if task.status == TaskStatus.CLOSED:
        raise HTTPException(400, "Задача закрыта")

    PRESETS = {
        "1h": timedelta(hours=1), "2h": timedelta(hours=2), "3h": timedelta(hours=3),
        "1d": timedelta(days=1), "2d": timedelta(days=2), "3d": timedelta(days=3),
    }
    delta = PRESETS.get(preset)
    if not delta:
        raise HTTPException(400, f"Неизвестный пресет: {preset}. Допустимы: {', '.join(PRESETS)}")

    PRESET_LABELS = {
        "1h": "за 1 час", "2h": "за 2 часа", "3h": "за 3 часа",
        "1d": "за 1 день", "2d": "за 2 дня", "3d": "за 3 дня",
    }
    fire_at = task.deadline - delta
    if fire_at <= datetime.utcnow():
        raise HTTPException(400, "Время напоминания уже прошло")

    rid = await schedule_reminder(task_id, fire_at, PRESET_LABELS[preset])
    return {"id": rid, "fire_at": fire_at, "reminder_type": PRESET_LABELS[preset]}
