from datetime import datetime
from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(100))
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), default="Europe/Moscow")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    notification_settings: Mapped["NotificationSettings"] = relationship(
        back_populates="employee", uselist=False, cascade="all, delete-orphan"
    )
    tasks_assigned: Mapped[list["Task"]] = relationship(
        "Task", foreign_keys="Task.assignee_id", back_populates="assignee"
    )
    tasks_created: Mapped[list["Task"]] = relationship(
        "Task", foreign_keys="Task.creator_id", back_populates="creator"
    )


class NotificationSettings(Base):
    __tablename__ = "notification_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(Integer, ForeignKey("employees.id"), unique=True)

    notify_new_task: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_status_change: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_deadline_change: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_new_comment: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_critical: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_overdue: Mapped[bool] = mapped_column(Boolean, default=True)

    quiet_hours_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    quiet_hours_start: Mapped[int] = mapped_column(Integer, default=22)
    quiet_hours_end: Mapped[int] = mapped_column(Integer, default=8)

    employee: Mapped["Employee"] = relationship(back_populates="notification_settings")
