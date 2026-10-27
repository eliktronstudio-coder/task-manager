"""Клиент Telegram Bot API."""
import logging
from typing import Any, Optional
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


def _base() -> str:
    return f"{settings.TELEGRAM_API_BASE}/bot{settings.BOT_TOKEN}"


def _safe(e: Exception) -> str:
    """Текст ошибки без токена — httpx кладёт в сообщение полный URL запроса."""
    return str(e).replace(settings.BOT_TOKEN, "***")


async def send_message(
    chat_id: int,
    text: str,
    buttons: Optional[list[list[dict]]] = None,
    parse_mode: str = "HTML",
) -> dict | None:
    """
    Отправить сообщение.
    buttons = [[{text, callback_data или url}, ...], ...]
    """
    body: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if buttons:
        # Конвертируем в Telegram inline_keyboard формат
        tg_buttons = []
        for row in buttons:
            tg_row = []
            for btn in row:
                if btn.get("type") == "callback":
                    tg_row.append({"text": btn["text"], "callback_data": btn["payload"]})
                elif btn.get("type") == "url":
                    tg_row.append({"text": btn["text"], "url": btn["url"]})
                elif btn.get("type") == "web_app":
                    # Telegram принимает web_app только с HTTPS — локально падаем на обычную ссылку
                    if btn["url"].startswith("https://"):
                        tg_row.append({"text": btn["text"], "web_app": {"url": btn["url"]}})
                    else:
                        tg_row.append({"text": btn["text"], "url": btn["url"]})
                else:
                    tg_row.append(btn)
            tg_buttons.append(tg_row)
        body["reply_markup"] = {"inline_keyboard": tg_buttons}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{_base()}/sendMessage", json=body)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.error("TG send_message error chat_id=%s: %s", chat_id, _safe(e))
        return None


async def answer_callback(
    callback_query_id: str,
    text: Optional[str] = None,
    show_alert: bool = False,
) -> bool:
    """Ответить на нажатие кнопки (убирает часики у пользователя)."""
    body: dict[str, Any] = {"callback_query_id": callback_query_id}
    if text:
        body["text"] = text
        body["show_alert"] = show_alert
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{_base()}/answerCallbackQuery", json=body)
            r.raise_for_status()
            return True
    except Exception as e:
        logger.error("TG answer_callback error: %s", _safe(e))
        return False


async def get_updates(offset: Optional[int] = None, timeout: int = 30) -> dict | None:
    """Long polling."""
    params: dict[str, Any] = {"timeout": timeout, "allowed_updates": ["message", "callback_query"]}
    if offset is not None:
        params["offset"] = offset
    try:
        async with httpx.AsyncClient(timeout=timeout + 5) as client:
            r = await client.get(f"{_base()}/getUpdates", params=params)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.error("TG get_updates error: %s", _safe(e))
        return None


async def set_webhook(url: str, secret_token: Optional[str] = None) -> bool:
    body: dict[str, Any] = {
        "url": url,
        "allowed_updates": ["message", "callback_query"],
        "drop_pending_updates": True,
    }
    if secret_token:
        body["secret_token"] = secret_token
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{_base()}/setWebhook", json=body)
            r.raise_for_status()
            result = r.json()
            if result.get("ok"):
                logger.info("Webhook set: %s", url)
                return True
            logger.error("Webhook error: %s", result)
            return False
    except Exception as e:
        logger.error("TG set_webhook error: %s", _safe(e))
        return False


async def delete_webhook() -> bool:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{_base()}/deleteWebhook")
            r.raise_for_status()
            return True
    except Exception as e:
        logger.error("TG delete_webhook error: %s", _safe(e))
        return False


async def send_document(chat_id: int, file_bytes: bytes, filename: str, caption: str = "") -> dict | None:
    """Отправить файл."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{_base()}/sendDocument",
                data={"chat_id": chat_id, "caption": caption},
                files={"document": (filename, file_bytes)},
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.error("TG send_document error: %s", _safe(e))
        return None


# ── Вспомогательные функции для кнопок ──────────────────────────────────────

def btn_callback(text: str, payload: str) -> dict:
    return {"type": "callback", "text": text, "payload": payload}


def btn_url(text: str, url: str) -> dict:
    return {"type": "url", "text": text, "url": url}


def btn_webapp(text: str, url: str) -> dict:
    return {"type": "web_app", "text": text, "url": url}


async def set_menu_button(text: str, url: str) -> bool:
    """Кнопка «Меню» слева от поля ввода, открывающая Mini App у всех пользователей."""
    body = {"menu_button": {"type": "web_app", "text": text, "web_app": {"url": url}}}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{_base()}/setChatMenuButton", json=body)
            r.raise_for_status()
            return r.json().get("ok", False)
    except Exception as e:
        logger.error("TG set_menu_button error: %s", _safe(e))
        return False
