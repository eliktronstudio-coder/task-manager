from datetime import datetime
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=False, index=True)
    author_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("employees.id"))
    text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    task: Mapped["Task"] = relationship(back_populates="comments")
    author: Mapped["Employee | None"] = relationship()
    attachments: Mapped[list["Attachment"]] = relationship("Attachment", back_populates="comment", cascade="all, delete-orphan")


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    comment_id: Mapped[int] = mapped_column(Integer, ForeignKey("comments.id"), nullable=False)
    # Хранит MAX file token (после загрузки через /uploads)
    max_file_token: Mapped[str | None] = mapped_column(String(500))
    # Или локальный путь к файлу
    local_path: Mapped[str | None] = mapped_column(String(500))
    original_name: Mapped[str | None] = mapped_column(String(300))
    mime_type: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    comment: Mapped["Comment"] = relationship(back_populates="attachments")
