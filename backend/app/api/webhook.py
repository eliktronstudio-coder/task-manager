"""Обработчик Telegram webhook и long polling."""
import logging
from fastapi import APIRouter, Request, Response, Header
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.employee import Employee
from app.models.task import Task, TaskStatus
from app.services import telegram_api as tg
from app.services.auth import get_or_create_employee

logger = logging.getLogger(__name__)
router = APIRouter(tags=["webhook"])


@router.post("/webhook")
async def webhook_endpoint(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(None),
):
    # Проверка секрета (опционально)
    if settings.WEBHOOK_SECRET and x_telegram_bot_api_secret_token != settings.WEBHOOK_SECRET:
        return Response(status_code=403)
    try:
        body = await request.json()
    except Exception:
        return Response(status_code=400)
    await handle_update(body)
    return Response(status_code=200)


async def handle_update(update: dict):
    """Диспетчер Telegram-событий."""
    if "message" in update:
        await _on_message(update["message"])
    elif "callback_query" in update:
        await _on_callback(update["callback_query"])


async def _on_message(message: dict):
    """Входящее сообщение от пользователя."""
    user = message.get("from", {})
    tg_user_id = user.get("id")
    chat_id = message.get("chat", {}).get("id") or tg_user_id
    text = message.get("text", "")

    if not tg_user_id:
        return

    async with AsyncSessionLocal() as session:
        await get_or_create_employee(session, user)

    welcome = (
        "👋 <b>Добро пожаловать в систему задач!</b>\n\n"
        "Здесь вы получаете уведомления о задачах и можете открыть приложение.\n\n"
        "Нажмите кнопку ниже 👇"
    )
    buttons = [[tg.btn_webapp("📋 Открыть приложение", f"{settings.public_url}/")]]
    await tg.send_message(chat_id, welcome, buttons)


async def _on_callback(callback: dict):
    """Нажатие inline-кнопки."""
    callback_id = callback.get("id")
    payload = callback.get("data", "")
    user = callback.get("from", {})
    tg_user_id = user.get("id")

    if not callback_id:
        return

    if payload.startswith("take:"):
        task_id = int(payload.split(":")[1])
        await _handle_take_task(callback_id, task_id, tg_user_id)
    else:
        await tg.answer_callback(callback_id, "Готово")


async def _handle_take_task(callback_id: str, task_id: int, tg_user_id: int):
    async with AsyncSessionLocal() as session:
        emp_r = await session.execute(select(Employee).where(Employee.tg_user_id == tg_user_id))
        emp = emp_r.scalar_one_or_none()
        if not emp:
            await tg.answer_callback(callback_id, "❌ Пользователь не найден", show_alert=True)
            return

        task_r = await session.execute(
            select(Task).where(Task.id == task_id).options(selectinload(Task.store))
        )
        task = task_r.scalar_one_or_none()
        if not task:
            await tg.answer_callback(callback_id, "❌ Задача не найдена", show_alert=True)
            return
        if task.status == TaskStatus.CLOSED:
            await tg.answer_callback(callback_id, "Задача уже закрыта", show_alert=True)
            return

        task.assignee_id = emp.id
        task.status = TaskStatus.IN_PROGRESS
        await session.commit()

    await tg.answer_callback(callback_id, "✅ Задача взята в работу!")
