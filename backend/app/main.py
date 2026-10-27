import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.services.scheduler import start_scheduler, stop_scheduler
from app.api import webhook, employees, stores, templates, tasks, comments, export

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
# httpx пишет каждый запрос с полным URL, а в URL Telegram API лежит токен бота
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

_polling_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _polling_task

    await init_db()
    logger.info("Database initialized")
    await _seed_templates()

    start_scheduler()

    if settings.WEBHOOK_URL:
        from app.services.telegram_api import set_webhook, delete_webhook
        await delete_webhook()
        ok = await set_webhook(settings.WEBHOOK_URL, settings.WEBHOOK_SECRET)
        logger.info("Webhook %s: %s", settings.WEBHOOK_URL, "OK" if ok else "FAILED")
        if settings.public_url.startswith("https://"):
            from app.services.telegram_api import set_menu_button
            await set_menu_button("Задачи", f"{settings.public_url}/")
        if not ok:
            _polling_task = asyncio.create_task(_start_polling())
    else:
        logger.info("No WEBHOOK_URL — using long polling")
        _polling_task = asyncio.create_task(_start_polling())

    yield

    stop_scheduler()
    if _polling_task and not _polling_task.done():
        from app.services.polling import stop_polling
        stop_polling()
        _polling_task.cancel()
        try:
            await _polling_task
        except asyncio.CancelledError:
            pass


async def _start_polling():
    from app.services.polling import run_polling
    await run_polling()


app = FastAPI(
    title="Task Manager (Telegram)",
    description="Контроль задач по открытию магазинов — Telegram bot",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook.router)
app.include_router(employees.router, prefix="/api")
app.include_router(employees.me_router, prefix="/api")
app.include_router(stores.router, prefix="/api")
app.include_router(templates.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(comments.router, prefix="/api")
app.include_router(export.router, prefix="/api")

frontend_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
if os.path.isdir(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")


async def _seed_templates():
    from sqlalchemy import select, func
    from app.database import AsyncSessionLocal
    from app.models.task import TaskTemplate, TaskSection

    async with AsyncSessionLocal() as session:
        count = await session.execute(select(func.count()).select_from(TaskTemplate))
        if count.scalar() > 0:
            return

        templates_data = [
            (TaskSection.PREPARATION, None, "БКОЛ", 1),
            (TaskSection.PREPARATION, None, "Инженерное заключение", 2),
            (TaskSection.PREPARATION, None, "Планограмма", 3),
            (TaskSection.PREPARATION, None, "Дизайн Макер", 4),
            (TaskSection.PREPARATION, None, "Калькулятор РСР", 5),
            (TaskSection.PREPARATION, None, "Договор ген. подряда", 6),
            (TaskSection.PREPARATION, None, "Договор проектировщиков", 7),
            (TaskSection.PREPARATION, None, "Договор РПР", 8),
            (TaskSection.PREPARATION, None, "Договор на подъёмный стол", 9),
            (TaskSection.PREPARATION, None, "Фотоотчёт открытия", 10),
            (TaskSection.PREPARATION, None, "Фотоотчёт СМР", 11),
            (TaskSection.PREPARATION, None, "Поставка оборудования", 12),
            (TaskSection.PREPARATION, None, "Поставка РИМ", 13),
            (TaskSection.PREPARATION, None, "Калькулятор СМР", 14),
            (TaskSection.PREPARATION, None, "Проверка рек. поставщиков", 15),
            (TaskSection.PREPARATION, None, "Проекты по ПБ", 16),
            (TaskSection.PREPARATION, None, "Приёмочная комиссия", 17),
            (TaskSection.PREPARATION, None, "Устранение замечаний к ген. подрядчику", 18),
            (TaskSection.PREPARATION, None, "Устранение замечаний к собственнику", 19),
            (TaskSection.PREPARATION, None, "Устранение замечаний по оборудованию", 20),
            (TaskSection.PREPARATION, None, "Устранение замечаний РИМ", 21),
            (TaskSection.PREPARATION, None, "Устранение замечаний к иным КА", 22),
            (TaskSection.DELIVERY, "Поставка рек. поставщиков", "Сплит-системы", 1),
            (TaskSection.DELIVERY, "Поставка рек. поставщиков", "ВТЗ", 2),
            (TaskSection.DELIVERY, "Поставка рек. поставщиков", "Электрика", 3),
            (TaskSection.DELIVERY, "Поставка рек. поставщиков", "Светильники", 4),
            (TaskSection.DELIVERY, "Поставка рек. поставщиков", "Керамогранит", 5),
            (TaskSection.DELIVERY, "Поставка рек. поставщиков", "Автоматические двери", 6),
            (TaskSection.DELIVERY, "Поставка рек. поставщиков", "Подъёмный стол", 7),
            (TaskSection.DELIVERY, "Поставка рек. поставщиков", "Стены ОГКЛ", 8),
            (TaskSection.DELIVERY, "Поставка рек. поставщиков", "Потолок ОГКЛ", 9),
            (TaskSection.DELIVERY, "Поставка рек. поставщиков", "ОПС", 10),
            (TaskSection.DELIVERY, "Поставка интегратора", "Холодильное оборудование", 1),
            (TaskSection.DELIVERY, "Поставка интегратора", "Стеллажное оборудование", 2),
            (TaskSection.DELIVERY, "Поставка интегратора", "РЦ", 3),
            (TaskSection.DELIVERY, "Поставка интегратора", "Медиаконтент", 4),
            (TaskSection.DELIVERY, "Поставка интегратора", "Видеонаблюдение", 5),
            (TaskSection.QUALITY, None, "Замечание отдела продаж", 1),
            (TaskSection.QUALITY, None, "Замечание интегратора оборудования", 2),
            (TaskSection.QUALITY, None, "Замечание медиаконтент", 3),
            (TaskSection.QUALITY, None, "Замечание видеонаблюдение", 4),
            (TaskSection.QUALITY, None, "Замечание РИМ", 5),
            (TaskSection.QUALITY, None, "Замечание строительства", 6),
        ]
        for section, subsection, name, order in templates_data:
            session.add(TaskTemplate(section=section, subsection=subsection, name=name, sort_order=order))
        await session.commit()
        logger.info("Templates seeded: %d", len(templates_data))
