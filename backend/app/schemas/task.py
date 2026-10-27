from datetime import datetime
from pydantic import BaseModel
from typing import Optional, List
from app.models.task import TaskStatus, TaskSection


class TaskTemplateBase(BaseModel):
    section: TaskSection
    subsection: Optional[str] = None
    name: str
    is_active: bool = True
    sort_order: int = 0


class TaskTemplateCreate(TaskTemplateBase):
    pass


class TaskTemplateUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    subsection: Optional[str] = None


class TaskTemplateOut(TaskTemplateBase):
    id: int

    model_config = {"from_attributes": True}


class ReminderInfo(BaseModel):
    id: int
    fire_at: datetime
    reminder_type: str
    is_sent: bool
    is_cancelled: bool

    model_config = {"from_attributes": True}


class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    section: TaskSection
    subsection: Optional[str] = None
    store_id: int
    assignee_id: Optional[int] = None
    deadline: Optional[datetime] = None


class TaskCreate(TaskBase):
    template_id: Optional[int] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assignee_id: Optional[int] = None
    status: Optional[TaskStatus] = None
    deadline: Optional[datetime] = None
    subsection: Optional[str] = None


class AssigneeShort(BaseModel):
    id: int
    full_name: str
    tg_user_id: int

    model_config = {"from_attributes": True}


class StoreShort(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class TaskListItem(BaseModel):
    id: int
    title: str
    section: TaskSection
    subsection: Optional[str]
    status: TaskStatus
    deadline: Optional[datetime]
    store: Optional[StoreShort]
    assignee: Optional[AssigneeShort]
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskOut(TaskBase):
    id: int
    status: TaskStatus
    creator_id: Optional[int]
    template_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    assignee: Optional[AssigneeShort] = None
    store: Optional[StoreShort] = None
    reminders: List[ReminderInfo] = []

    model_config = {"from_attributes": True}
