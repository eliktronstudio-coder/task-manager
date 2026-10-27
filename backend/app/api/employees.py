from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.employee import Employee, NotificationSettings
from app.schemas.employee import EmployeeCreate, EmployeeUpdate, EmployeeOut, NotificationSettingsUpdate
from typing import Optional

from app.services.auth import _tg_user_from_request, get_or_create_employee, current_employee

MANAGER_ONLY_FIELDS = {"is_admin", "is_active", "position"}


async def _load_employee(db: AsyncSession, employee_id: int) -> Employee:
    # refresh() не подгружает связи, а ленивая загрузка в async-сессии падает при сериализации
    result = await db.execute(
        select(Employee)
        .where(Employee.id == employee_id)
        .options(selectinload(Employee.notification_settings))
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


def _require_self_or_manager(actor: Optional[Employee], employee_id: int):
    if not actor:
        raise HTTPException(401, "Откройте приложение через бота в Telegram")
    if actor.id != employee_id and not actor.is_manager:
        raise HTTPException(403, "Можно менять только свои настройки")

router = APIRouter(prefix="/employees", tags=["employees"])
me_router = APIRouter(tags=["auth"])


@me_router.get("/me", response_model=EmployeeOut)
async def get_me(request: Request, db: AsyncSession = Depends(get_db)):
    """Текущий пользователь Mini App (регистрируется автоматически при первом входе)."""
    tg_user = _tg_user_from_request(request)
    if not tg_user:
        raise HTTPException(401, "Откройте приложение через бота в Telegram")
    return await get_or_create_employee(db, tg_user)


@router.get("/", response_model=list[EmployeeOut])
async def list_employees(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Employee)
        .where(Employee.is_active.is_(True))
        .options(selectinload(Employee.notification_settings))
        .order_by(Employee.full_name)
    )
    return result.scalars().all()


@router.post("/", response_model=EmployeeOut, status_code=201)
async def create_employee(
    data: EmployeeCreate,
    actor: Optional[Employee] = Depends(current_employee),
    db: AsyncSession = Depends(get_db),
):
    if not actor or not actor.is_manager:
        raise HTTPException(403, "Добавлять сотрудников может только руководитель")
    # Проверка дублей
    exists = await db.execute(
        select(Employee).where(Employee.tg_user_id == data.tg_user_id)
    )
    if exists.scalar_one_or_none():
        raise HTTPException(400, "Сотрудник с таким Telegram ID уже существует")

    emp = Employee(**data.model_dump())
    db.add(emp)
    await db.flush()

    # Создаём настройки уведомлений по умолчанию
    ns = NotificationSettings(employee_id=emp.id)
    db.add(ns)
    await db.commit()
    return await _load_employee(db, emp.id)


@router.get("/{employee_id}", response_model=EmployeeOut)
async def get_employee(employee_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Employee)
        .where(Employee.id == employee_id)
        .options(selectinload(Employee.notification_settings))
    )
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "Сотрудник не найден")
    return emp


@router.patch("/{employee_id}", response_model=EmployeeOut)
async def update_employee(
    employee_id: int,
    data: EmployeeUpdate,
    actor: Optional[Employee] = Depends(current_employee),
    db: AsyncSession = Depends(get_db),
):
    _require_self_or_manager(actor, employee_id)
    changes = data.model_dump(exclude_unset=True)
    if MANAGER_ONLY_FIELDS & changes.keys() and not actor.is_manager:
        raise HTTPException(403, "Должность и роль меняет только руководитель")
    result = await db.execute(
        select(Employee)
        .where(Employee.id == employee_id)
        .options(selectinload(Employee.notification_settings))
    )
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "Сотрудник не найден")

    for field, value in changes.items():
        # null допустим только для должности — так её снимают
        if value is None and field != "position":
            continue
        setattr(emp, field, value)

    await db.commit()
    return await _load_employee(db, emp.id)


@router.patch("/{employee_id}/notifications", response_model=EmployeeOut)
async def update_notifications(
    employee_id: int,
    data: NotificationSettingsUpdate,
    actor: Optional[Employee] = Depends(current_employee),
    db: AsyncSession = Depends(get_db),
):
    _require_self_or_manager(actor, employee_id)
    result = await db.execute(
        select(Employee)
        .where(Employee.id == employee_id)
        .options(selectinload(Employee.notification_settings))
    )
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "Сотрудник не найден")

    if not emp.notification_settings:
        emp.notification_settings = NotificationSettings(employee_id=emp.id)

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(emp.notification_settings, field, value)

    await db.commit()
    return await _load_employee(db, emp.id)
