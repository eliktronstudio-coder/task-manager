"""APScheduler — напоминания и проверка просрочек."""
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.reminder import Reminder
from app.models.task import Task, TaskStatus
from app.models.employee import Employee
from app.services import notifications

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None

# APScheduler jobstore — SQLAlchemy (синхронный, для хранения заданий)
_JOBSTORE_URL = settings.DATABASE_URL.replace("+aiosqlite", "").replace("+asyncpg", "")


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        jobstores = {
            "default": SQLAlchemyJobStore(
                url=_JOBSTORE_URL,
                engine_options={} if _JOBSTORE_URL.startswith("sqlite") else {"pool_size": 1, "max_overflow": 1, "pool_pre_ping": True},
            )
        }
        _scheduler = AsyncIOScheduler(jobstores=jobstores, timezone="UTC")
    return _scheduler


async def _fire_reminders():
    """Запускается каждую минуту — ищет напоминания, которые нужно отправить."""
    now = datetime.utcnow()

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Reminder)
            .where(
                and_(
                    Reminder.fire_at <= now,
                    Reminder.is_sent.is_(False),
                    Reminder.is_cancelled.is_(False),
                )
            )
            .options(
                selectinload(Reminder.task).selectinload(Task.assignee)
                .selectinload(Employee.notification_settings),
                selectinload(Reminder.task).selectinload(Task.store),
            )
        )
        reminders = result.scalars().all()

        for reminder in reminders:
            task = reminder.task
            if not task or task.status == TaskStatus.CLOSED:
                reminder.is_cancelled = True
                continue
            if not task.assignee:
                reminder.is_sent = True
                continue

            store_name = task.store.name if task.store else "?"
            await notifications.send_reminder(
                task.assignee, task, store_name, reminder.reminder_type
            )
            reminder.is_sent = True

        await session.commit()


async def _check_overdue():
    """Запускается раз в час — ищет просроченные задачи и уведомляет."""
    now = datetime.utcnow()

    async with AsyncSessionLocal() as session:
        # Просроченные незакрытые задачи с исполнителем
        result = await session.execute(
            select(Task)
            .where(
                and_(
                    Task.deadline < now,
                    Task.status != TaskStatus.CLOSED,
                    Task.assignee_id.is_not(None),
                )
            )
            .options(
                selectinload(Task.assignee).selectinload(Employee.notification_settings),
                selectinload(Task.store),
            )
        )
        overdue_tasks = result.scalars().all()

        # Получаем всех администраторов
        admins_result = await session.execute(
            select(Employee)
            .where(and_(Employee.is_admin.is_(True), Employee.is_active.is_(True)))
            .options(selectinload(Employee.notification_settings))
        )
        admins = admins_result.scalars().all()

        for task in overdue_tasks:
            if not task.assignee:
                continue
            store_name = task.store.name if task.store else "?"
            await notifications.notify_overdue(
                task.assignee, task, store_name, admins
            )

        await session.commit()


def start_scheduler():
    scheduler = get_scheduler()
    if not scheduler.running:
        # Напоминания — каждую минуту
        scheduler.add_job(
            _fire_reminders,
            trigger="interval",
            minutes=1,
            id="fire_reminders",
            replace_existing=True,
            misfire_grace_time=60,
        )
        # Проверка просрочек — каждый час
        scheduler.add_job(
            _check_overdue,
            trigger="interval",
            hours=1,
            id="check_overdue",
            replace_existing=True,
            misfire_grace_time=300,
        )
        scheduler.start()
        logger.info("Scheduler started")


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


async def schedule_reminder(
    task_id: int, fire_at: datetime, reminder_type: str
) -> int:
    """Сохранить напоминание в БД (планировщик подхватит по расписанию)."""
    async with AsyncSessionLocal() as session:
        reminder = Reminder(
            task_id=task_id,
            fire_at=fire_at,
            reminder_type=reminder_type,
        )
        session.add(reminder)
        await session.commit()
        await session.refresh(reminder)
        return reminder.id


async def cancel_reminders_for_task(task_id: int):
    """Отменить все несрабатывавшие напоминания задачи."""
    from sqlalchemy import update
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Reminder)
            .where(
                and_(
                    Reminder.task_id == task_id,
                    Reminder.is_sent.is_(False),
                    Reminder.is_cancelled.is_(False),
                )
            )
            .values(is_cancelled=True)
        )
        await session.commit()
