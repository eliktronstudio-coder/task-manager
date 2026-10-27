from datetime import datetime
from pydantic import BaseModel
from typing import Optional, List


class AttachmentOut(BaseModel):
    id: int
    original_name: Optional[str]
    mime_type: Optional[str]
    max_file_token: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class CommentCreate(BaseModel):
    text: Optional[str] = None
    # attachment токены приходят после загрузки файла через /upload


class AuthorShort(BaseModel):
    id: int
    full_name: str

    model_config = {"from_attributes": True}


class CommentOut(BaseModel):
    id: int
    task_id: int
    text: Optional[str]
    author: Optional[AuthorShort]
    created_at: datetime
    attachments: List[AttachmentOut] = []

    model_config = {"from_attributes": True}
