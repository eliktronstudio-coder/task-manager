"""Авторизация пользователей Mini App по подписанным Telegram initData."""
import hashlib
import hmac
import json
import time
from typing import Optional
from urllib.parse import parse_qsl

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.employee import Employee, NotificationSettings

INIT_DATA_MAX_AGE = 24 * 3600


def validate_init_data(init_data: str) -> Optional[dict]:
    """Вернуть объект user из initData, если подпись верна, иначе None."""
    if not init_data:
        return None
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None

    check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", settings.BOT_TOKEN.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        return None

    try:
        if time.time() - int(pairs.get("auth_date", 0)) > INIT_DATA_MAX_AGE:
            return None
        user = json.loads(pairs.get("user", ""))
    except (ValueError, TypeError):
        return None
    return user if isinstance(user, dict) and user.get("id") else None


async def get_or_create_employee(db: AsyncSession, tg_user: dict) -> Employee:
    tg_user_id = int(tg_user["id"])
    result = await db.execute(
        select(Employee)
        .where(Employee.tg_user_id == tg_user_id)
        .options(selectinload(Employee.notification_settings))
    )
    emp = result.scalar_one_or_none()
    is_admin = tg_user_id in settings.admin_ids_list
    if emp:
        if is_admin and not emp.is_admin:
            emp.is_admin = True
            await db.commit()
        return emp

    full_name = " ".join(filter(None, [tg_user.get("first_name"), tg_user.get("last_name")])) or "Пользователь"
    emp = Employee(
        tg_user_id=tg_user_id,
        username=tg_user.get("username"),
        full_name=full_name,
        is_admin=is_admin,
    )
    db.add(emp)
    await db.flush()
    db.add(NotificationSettings(employee_id=emp.id))
    await db.commit()

    result = await db.execute(
        select(Employee).where(Employee.id == emp.id).options(selectinload(Employee.notification_settings))
    )
    return result.scalar_one()


def _tg_user_from_request(request: Request) -> Optional[dict]:
    user = validate_init_data(request.headers.get("X-Telegram-Init-Data", ""))
    if user:
        return user
    # Для проверки в обычном браузере без Telegram — только при DEBUG=true
    if settings.DEBUG:
        debug_id = request.headers.get("X-Debug-Tg-User-Id")
        if debug_id and debug_id.isdigit():
            return {"id": int(debug_id), "first_name": f"Debug {debug_id}"}
    return None


async def current_employee(
    request: Request, db: AsyncSession = Depends(get_db)
) -> Optional[Employee]:
    """Сотрудник, от имени которого выполняется запрос (None — если не определён)."""
    tg_user = _tg_user_from_request(request)
    if not tg_user:
        return None
    result = await db.execute(select(Employee).where(Employee.tg_user_id == int(tg_user["id"])))
    return result.scalar_one_or_none()
