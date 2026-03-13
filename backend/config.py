"""Конфигурация приложения ProspEl."""
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator


DEFAULT_DEV_SECRET_KEY = "dev-secret-key-change-me"
DEFAULT_DEV_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]


class Settings(BaseSettings):
    """Настройки приложения."""
    app_name: str = "ProspEl"
    app_version: str = "2.1.0"
    app_env: Literal["dev", "prod"] = "dev"
    debug: bool = False
    database_url: str = "sqlite+aiosqlite:///./prospel.db"
    cors_allowed_origins: list[str] = Field(default_factory=list)
    backup_dir: str = "./backups"
    backup_auto_enabled: bool = True
    backup_auto_interval_hours: int = 6
    backup_auto_retention_count: int = 60
    backup_manual_retention_count: int = 30
    backup_pre_restore_retention_count: int = 20
    backup_scheduler_check_minutes: int = 5
    # В dev допустим предсказуемый ключ, но в prod обязателен внешний безопасный SECRET_KEY.
    secret_key: str = DEFAULT_DEV_SECRET_KEY
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 часа

    # Лимиты по законодательству Сербии (RSD)
    income_limit_pausal: int = 6_000_000  # Порог выхода из паушального режима
    income_limit_vat: int = 8_000_000     # Порог регистрации НДС
    limit_warning_percent: float = 0.8     # 80% - предупреждение

    @field_validator("app_env", mode="before")
    @classmethod
    def normalize_app_env(cls, value):
        normalized = str(value or "dev").strip().lower()
        if normalized not in {"dev", "prod"}:
            raise ValueError("APP_ENV must be either 'dev' or 'prod'")
        return normalized

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def parse_cors_allowed_origins(cls, value):
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        raise ValueError("CORS_ALLOWED_ORIGINS must be a comma-separated string or list")

    @model_validator(mode="after")
    def validate_runtime_safety(self):
        if self.app_env == "dev":
            if not self.cors_allowed_origins:
                self.cors_allowed_origins = list(DEFAULT_DEV_CORS_ORIGINS)
            return self

        if self.debug:
            raise ValueError("DEBUG must be disabled in prod")
        if not self.secret_key or not self.secret_key.strip():
            raise ValueError("SECRET_KEY is required in prod")
        if self.secret_key == DEFAULT_DEV_SECRET_KEY:
            raise ValueError("SECRET_KEY must not use the default dev value in prod")
        if len(self.secret_key.strip()) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters in prod")
        if not self.cors_allowed_origins:
            raise ValueError("CORS_ALLOWED_ORIGINS is required in prod")
        if any(origin == "*" for origin in self.cors_allowed_origins):
            raise ValueError("CORS wildcard '*' is not allowed in prod")
        return self

    @property
    def is_dev(self) -> bool:
        return self.app_env == "dev"

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
