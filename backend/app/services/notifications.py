"""Сервис уведомлений через Telegram."""
import logging
from datetime import datetime
from typing import Optional
import pytz

from app.models.employee import Employee, NotificationSettings
from app.models.task import Task, TaskStatus
from app.services import telegram_api as tg

logger = logging.getLogger(__name__)

STATUS_LABELS = {
    TaskStatus.IN_PROGRESS: "В работе",
    TaskStatus.CRITICAL: "⚠️ Критично важно",
    TaskStatus.CLOSED: "✅ Закрыто",
}


def _is_quiet_time(ns: NotificationSettings, tz_name: str) -> bool:
    if not ns.quiet_hours_enabled:
        return False
    try:
        tz = pytz.timezone(tz_name)
        h = datetime.now(tz).hour
        start, end = ns.quiet_hours_start, ns.quiet_hours_end
        return (h >= start or h < end) if start >= end else (start <= h < end)
    except Exception:
        return False


async def _can_notify(employee: Employee, notif_type: str) -> bool:
    ns = employee.notification_settings
    if ns is None:
        return True
    attr_map = {
        "new_task": "notify_new_task",
        "status_change": "notify_status_change",
        "deadline_change": "notify_deadline_change",
        "new_comment": "notify_new_comment",
        "critical": "notify_critical",
        "overdue": "notify_overdue",
    }
    if not getattr(ns, attr_map.get(notif_type, "notify_new_task"), True):
        return False
    return not _is_quiet_time(ns, employee.timezone)


def _deadline_str(task: Task) -> str:
    return task.deadline.strftime("%d.%m.%Y %H:%M") if task.deadline else "не указан"


def _app_url(task_id: int) -> str:
    from app.config import settings
    return f"{settings.public_url}/?task_id={task_id}"


async def notify_new_task(employee: Employee, task: Task, store_name: str):
    if not await _can_notify(employee, "new_task"):
        return
    text = (
        f"📋 <b>Новая задача назначена вам</b>\n\n"
        f"<b>{task.title}</b>\n"
        f"🏪 Магазин: {store_name}\n"
        f"📅 Срок: {_deadline_str(task)}"
    )
    buttons = [[
        tg.btn_webapp("📂 Открыть", _app_url(task.id)),
        tg.btn_callback("✅ Взять в работу", f"take:{task.id}"),
    ]]
    await tg.send_message(employee.tg_user_id, text, buttons)


async def notify_status_changed(employee: Employee, task: Task, store_name: str, new_status: str):
    if not await _can_notify(employee, "status_change"):
        return
    label = STATUS_LABELS.get(TaskStatus(new_status), new_status)
    text = (
        f"🔄 <b>Изменён статус задачи</b>\n\n"
        f"<b>{task.title}</b>\n"
        f"🏪 {store_name}\n"
        f"Новый статус: {label}"
    )
    buttons = [[tg.btn_webapp("📂 Открыть", _app_url(task.id))]]
    await tg.send_message(employee.tg_user_id, text, buttons)


async def notify_deadline_changed(employee: Employee, task: Task, store_name: str):
    if not await _can_notify(employee, "deadline_change"):
        return
    text = (
        f"📅 <b>Изменён срок задачи</b>\n\n"
        f"<b>{task.title}</b>\n"
        f"🏪 {store_name}\n"
        f"Новый срок: {_deadline_str(task)}"
    )
    buttons = [[tg.btn_webapp("📂 Открыть", _app_url(task.id))]]
    await tg.send_message(employee.tg_user_id, text, buttons)


async def notify_new_comment(employee: Employee, task: Task, store_name: str, author_name: str):
    if not await _can_notify(employee, "new_comment"):
        return
    text = (
        f"💬 <b>Новый комментарий</b>\n\n"
        f"<b>{task.title}</b>\n"
        f"🏪 {store_name}\n"
        f"От: {author_name}"
    )
    buttons = [[tg.btn_webapp("📂 Открыть", _app_url(task.id))]]
    await tg.send_message(employee.tg_user_id, text, buttons)


async def notify_critical(employee: Employee, task: Task, store_name: str, admins: list[Employee]):
    if await _can_notify(employee, "critical"):
        text = (
            f"⚠️ <b>КРИТИЧНО ВАЖНО</b>\n\n"
            f"<b>{task.title}</b>\n"
            f"🏪 {store_name}"
        )
        buttons = [[tg.btn_webapp("📂 Открыть", _app_url(task.id))]]
        await tg.send_message(employee.tg_user_id, text, buttons)

    for admin in admins:
        if admin.tg_user_id == employee.tg_user_id:
            continue
        if not await _can_notify(admin, "critical"):
            continue
        text = (
            f"⚠️ <b>КРИТИЧНО у {employee.full_name}</b>\n\n"
            f"<b>{task.title}</b>\n"
            f"🏪 {store_name}"
        )
        await tg.send_message(admin.tg_user_id, text, [[tg.btn_webapp("📂 Открыть", _app_url(task.id))]])


async def notify_overdue(employee: Employee, task: Task, store_name: str, admins: list[Employee]):
    deadline_str = task.deadline.strftime("%d.%m.%Y") if task.deadline else "?"
    text = (
        f"🚨 <b>Просроченная задача</b>\n\n"
        f"<b>{task.title}</b>\n"
        f"🏪 {store_name}\n"
        f"Срок был: {deadline_str}"
    )
    buttons = [[tg.btn_webapp("📂 Открыть", _app_url(task.id))]]

    if await _can_notify(employee, "overdue"):
        await tg.send_message(employee.tg_user_id, text, buttons)

    for admin in admins:
        if admin.tg_user_id == employee.tg_user_id:
            continue
        if await _can_notify(admin, "overdue"):
            admin_text = f"🚨 <b>Просрочено у {employee.full_name}</b>\n\n<b>{task.title}</b>\n🏪 {store_name}\nСрок был: {deadline_str}"
            await tg.send_message(admin.tg_user_id, admin_text, buttons)


async def send_reminder(employee: Employee, task: Task, store_name: str, reminder_type: str):
    text = (
        f"⏰ <b>Напоминание</b>\n\n"
        f"<b>{task.title}</b>\n"
        f"🏪 {store_name}\n"
        f"Срок: {_deadline_str(task)}\n"
        f"({reminder_type})"
    )
    buttons = [[tg.btn_webapp("📂 Открыть", _app_url(task.id))]]
    await tg.send_message(employee.tg_user_id, text, buttons)
