from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Discount Parser API"
    env: str = "local"
    debug: bool = False
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    log_format: str = "plain"
    timezone: str = "Europe/Moscow"
    database_url: str = "sqlite:///./discount_parser.db"

    sources_config_path: str = "config/sources.yaml"
    collect_interval_minutes: int = 120
    maintenance_hour: int = 22
    maintenance_minute: int = 0
    stale_after_days: int = 7


@lru_cache
def get_settings() -> Settings:
    return Settings()
