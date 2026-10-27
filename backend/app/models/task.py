from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey, Boolean, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class TaskStatus(str, PyEnum):
    IN_PROGRESS = "in_progress"    # В работе
    CRITICAL = "critical"          # Критично важно
    CLOSED = "closed"              # Закрыто


class TaskSection(str, PyEnum):
    PREPARATION = "preparation"    # Подготовка исходников
    DELIVERY = "delivery"          # Поставки
    QUALITY = "quality"            # Качество открытия магазина


class TaskTemplate(Base):
    """Справочник задач — редактируется администратором."""
    __tablename__ = "task_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    section: Mapped[str] = mapped_column(
        Enum(TaskSection, values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )
    subsection: Mapped[str | None] = mapped_column(String(200))  # подраздел (напр. "Поставка рек. поставщиков")
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    def __repr__(self) -> str:
        return f"<TaskTemplate id={self.id} section={self.section} name={self.name!r}>"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Содержание
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    section: Mapped[str] = mapped_column(
        Enum(TaskSection, values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )
    subsection: Mapped[str | None] = mapped_column(String(200))

    # Связи
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.id"), nullable=False)
    assignee_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employees.id"))
    creator_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employees.id"))
    template_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("task_templates.id"))

    # Статус и срок
    status: Mapped[str] = mapped_column(
        Enum(TaskStatus, values_callable=lambda x: [e.value for e in x]),
        default=TaskStatus.IN_PROGRESS,
        nullable=False
    )
    deadline: Mapped[datetime | None] = mapped_column(DateTime)
    is_overdue_notified: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Отношения
    store: Mapped["Store"] = relationship(back_populates="tasks")
    assignee: Mapped["Employee | None"] = relationship(
        foreign_keys=[assignee_id], back_populates="tasks_assigned"
    )
    creator: Mapped["Employee | None"] = relationship(
        foreign_keys=[creator_id], back_populates="tasks_created"
    )
    comments: Mapped[list["Comment"]] = relationship("Comment", back_populates="task", cascade="all, delete-orphan")
    reminders: Mapped[list["Reminder"]] = relationship("Reminder", back_populates="task", cascade="all, delete-orphan")
    history: Mapped[list["HistoryEntry"]] = relationship("HistoryEntry", back_populates="task", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Task id={self.id} title={self.title!r} status={self.status}>"
