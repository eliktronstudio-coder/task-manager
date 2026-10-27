from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional


class NotificationSettingsOut(BaseModel):
    notify_new_task: bool
    notify_status_change: bool
    notify_deadline_change: bool
    notify_new_comment: bool
    notify_critical: bool
    notify_overdue: bool
    quiet_hours_enabled: bool
    quiet_hours_start: int
    quiet_hours_end: int

    model_config = {"from_attributes": True}


class NotificationSettingsUpdate(BaseModel):
    notify_new_task: Optional[bool] = None
    notify_status_change: Optional[bool] = None
    notify_deadline_change: Optional[bool] = None
    notify_new_comment: Optional[bool] = None
    notify_critical: Optional[bool] = None
    notify_overdue: Optional[bool] = None
    quiet_hours_enabled: Optional[bool] = None
    quiet_hours_start: Optional[int] = Field(None, ge=0, le=23)
    quiet_hours_end: Optional[int] = Field(None, ge=0, le=23)


class EmployeeBase(BaseModel):
    full_name: str
    username: Optional[str] = None
    is_admin: bool = False
    timezone: str = "Europe/Moscow"


class EmployeeCreate(EmployeeBase):
    tg_user_id: int


class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = None
    username: Optional[str] = None
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None
    timezone: Optional[str] = None


class EmployeeOut(EmployeeBase):
    id: int
    tg_user_id: int
    is_active: bool
    created_at: datetime
    notification_settings: Optional[NotificationSettingsOut] = None

    model_config = {"from_attributes": True}
