import os
import uuid
import aiofiles
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.comment import Comment, Attachment
from app.models.task import Task, TaskStatus
from app.models.employee import Employee
from app.schemas.comment import CommentOut
from app.services import notifications
from app.services.auth import current_employee

router = APIRouter(prefix="/tasks/{task_id}/comments", tags=["comments"])

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.get("/", response_model=list[CommentOut])
async def list_comments(task_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Comment)
        .where(Comment.task_id == task_id)
        .options(
            selectinload(Comment.author),
            selectinload(Comment.attachments),
        )
        .order_by(Comment.created_at.asc())
    )
    return result.scalars().all()


@router.post("/", response_model=CommentOut, status_code=201)
async def add_comment(
    task_id: int,
    text: Optional[str] = Form(None),
    files: list[UploadFile] = File(default=[]),
    author: Optional[Employee] = Depends(current_employee),
    db: AsyncSession = Depends(get_db),
):
    # Проверяем задачу
    task_result = await db.execute(
        select(Task)
        .where(Task.id == task_id)
        .options(
            selectinload(Task.assignee).selectinload(Employee.notification_settings),
            selectinload(Task.store),
        )
    )
    task = task_result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Задача не найдена")

    comment = Comment(
        task_id=task_id,
        author_id=author.id if author else None,
        text=text,
    )
    db.add(comment)
    await db.flush()

    # Сохраняем вложения локально
    for upload in files:
        if not upload.filename:
            continue
        ext = os.path.splitext(upload.filename)[1]
        local_name = f"{uuid.uuid4()}{ext}"
        local_path = os.path.join(UPLOAD_DIR, local_name)
        content = await upload.read()
        async with aiofiles.open(local_path, "wb") as f:
            await f.write(content)

        att = Attachment(
            comment_id=comment.id,
            local_path=local_path,
            original_name=upload.filename,
            mime_type=upload.content_type,
        )
        db.add(att)

    await db.commit()

    # Загружаем со связями
    result = await db.execute(
        select(Comment)
        .where(Comment.id == comment.id)
        .options(selectinload(Comment.author), selectinload(Comment.attachments))
    )
    comment = result.scalar_one()

    # Уведомляем исполнителя (если комментарий от другого)
    if task.assignee and author and task.assignee.id != author.id:
        store_name = task.store.name if task.store else "?"
        await notifications.notify_new_comment(
            task.assignee, task, store_name, author.full_name
        )
    elif task.assignee and not author:
        store_name = task.store.name if task.store else "?"
        await notifications.notify_new_comment(
            task.assignee, task, store_name, "Система"
        )

    return comment


@router.get("/{comment_id}/attachments/{attachment_id}")
async def get_attachment(
    task_id: int,
    comment_id: int,
    attachment_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Скачать вложение."""
    from fastapi.responses import FileResponse
    result = await db.execute(
        select(Attachment).where(
            Attachment.id == attachment_id,
            Attachment.comment_id == comment_id,
        )
    )
    att = result.scalar_one_or_none()
    if not att or not att.local_path or not os.path.exists(att.local_path):
        raise HTTPException(404, "Файл не найден")

    return FileResponse(
        att.local_path,
        media_type=att.mime_type or "application/octet-stream",
        filename=att.original_name or "file",
    )
