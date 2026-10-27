import logging
import re

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import Optional


class Settings(BaseSettings):
    # Telegram Bot
    BOT_TOKEN: str = Field(..., description="Токен бота от @BotFather")
    TELEGRAM_API_BASE: str = "https://api.telegram.org"
    WEBHOOK_URL: Optional[str] = None   # Если пусто — long polling
    WEBHOOK_SECRET: Optional[str] = None

    # БД
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/taskmanager.db"

    # Приложение
    APP_SECRET_KEY: str = "change-me-in-production-please"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    DEBUG: bool = False

    # Telegram user ID администраторов (через запятую)
    ADMIN_TG_IDS: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @field_validator("BOT_TOKEN")
    @classmethod
    def _clean_token(cls, token: str) -> str:
        token = token.strip()
        if not re.fullmatch(r"\d+:[\w-]{30,}", token):
            logging.getLogger(__name__).error(
                "BOT_TOKEN выглядит неполным: нужен токен целиком, вида 1234567890:AAxxxx… (цифры, двоеточие, буквы)"
            )
        return token

    @field_validator("DATABASE_URL")
    @classmethod
    def _default_database_name(cls, url: str) -> str:
        # Без имени базы asyncpg подставляет имя пользователя, а пулер Supabase такой базы не знает
        from sqlalchemy.engine import make_url
        url = url.strip()
        parsed = make_url(url)
        if parsed.get_backend_name() == "postgresql" and not parsed.database:
            return parsed.set(database="postgres").render_as_string(hide_password=False)
        return url

    @property
    def public_url(self) -> str:
        if self.WEBHOOK_URL:
            return self.WEBHOOK_URL.removesuffix("/").removesuffix("/webhook")
        return f"http://localhost:{self.APP_PORT}"

    @property
    def admin_ids_list(self) -> list[int]:
        if not self.ADMIN_TG_IDS:
            return []
        return [int(x.strip()) for x in self.ADMIN_TG_IDS.split(",") if x.strip()]


settings = Settings()
