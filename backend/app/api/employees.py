from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.employee import Employee, NotificationSettings
from app.schemas.employee import EmployeeCreate, EmployeeUpdate, EmployeeOut, NotificationSettingsUpdate
from app.services.auth import _tg_user_from_request, get_or_create_employee

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
async def create_employee(data: EmployeeCreate, db: AsyncSession = Depends(get_db)):
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
    await db.refresh(emp)

    result = await db.execute(
        select(Employee)
        .where(Employee.id == emp.id)
        .options(selectinload(Employee.notification_settings))
    )
    return result.scalar_one()


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
    employee_id: int, data: EmployeeUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Employee)
        .where(Employee.id == employee_id)
        .options(selectinload(Employee.notification_settings))
    )
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "Сотрудник не найден")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(emp, field, value)

    await db.commit()
    await db.refresh(emp)
    return emp


@router.patch("/{employee_id}/notifications", response_model=EmployeeOut)
async def update_notifications(
    employee_id: int, data: NotificationSettingsUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Employee)
        .where(Employee.id == employee_id)
        .options(selectinload(Employee.notification_settings))
    )
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "Сотрудник не найден")

    if not emp.notification_settings:
        ns = NotificationSettings(employee_id=emp.id)
        db.add(ns)
        await db.flush()
        await db.refresh(emp)

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(emp.notification_settings, field, value)

    await db.commit()
    await db.refresh(emp)
    return emp
