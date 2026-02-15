"""Конфигурация приложения ProspEl."""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Настройки приложения."""
    app_name: str = "ProspEl"
    debug: bool = False
    database_url: str = "sqlite+aiosqlite:///./prospel.db"
    secret_key: str = "change-this-in-production-use-secure-random-string"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 часа
    
    # Лимиты по законодательству Сербии (RSD)
    income_limit_pausal: int = 6_000_000  # Порог выхода из паушального режима
    income_limit_vat: int = 8_000_000     # Порог регистрации НДС
    limit_warning_percent: float = 0.8     # 80% - предупреждение

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
