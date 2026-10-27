import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

# Создаём папку для SQLite если нужно
if settings.DATABASE_URL.startswith("sqlite"):
    db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "")
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)

_is_sqlite = "sqlite" in settings.DATABASE_URL

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    # Пул Supabase на бесплатном тарифе маленький и сам закрывает простаивающие соединения
    **({} if _is_sqlite else {"pool_size": 4, "max_overflow": 4, "pool_pre_ping": True, "pool_recycle": 1800}),
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """Создаём все таблицы при старте (для разработки)."""
    from app.models import employee, store, task, comment, reminder, history  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)


def _add_missing_columns(sync_conn):
    """create_all не добавляет колонки в существующие таблицы, а Alembic пока не используется."""
    from sqlalchemy import inspect, text
    columns = {c["name"] for c in inspect(sync_conn).get_columns("employees")}
    if "position" not in columns:
        sync_conn.execute(text("ALTER TABLE employees ADD COLUMN position VARCHAR(20)"))
