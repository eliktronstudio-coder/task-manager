from datetime import datetime, date
from pydantic import BaseModel
from typing import Optional


class StoreBase(BaseModel):
    name: str
    address: Optional[str] = None
    planned_open_date: Optional[date] = None


class StoreCreate(StoreBase):
    pass


class StoreUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    planned_open_date: Optional[date] = None
    is_active: Optional[bool] = None


class StoreOut(StoreBase):
    id: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
