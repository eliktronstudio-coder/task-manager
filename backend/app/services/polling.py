"""Long polling для локальной разработки."""
import asyncio
import logging
from app.services import telegram_api as tg
from app.api.webhook import handle_update

logger = logging.getLogger(__name__)
_stop_event = asyncio.Event()


async def run_polling():
    logger.info("Starting Telegram long polling...")
    offset = None
    while not _stop_event.is_set():
        try:
            data = await tg.get_updates(offset=offset, timeout=25)
            if data and data.get("ok"):
                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    try:
                        await handle_update(update)
                    except Exception as e:
                        logger.error("Error handling update %s: %s", update.get("update_id"), e)
            else:
                # get_updates глотает сетевые ошибки и возвращает None — без паузы цикл крутится вхолостую
                await asyncio.sleep(3)
        except Exception as e:
            logger.error("Polling error: %s", e)
            await asyncio.sleep(3)


def stop_polling():
    _stop_event.set()
