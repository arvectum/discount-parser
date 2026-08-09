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
    web_port: int = 8765
    log_level: str = "INFO"
    log_format: str = "plain"
    timezone: str = "Europe/Moscow"
    database_url: str = "sqlite:///./discount_parser.db"

    sources_config_path: str = "config/sources.yaml"
    collect_interval_minutes: int = 120
    maintenance_hour: int = 22
    maintenance_minute: int = 0
    stale_after_days: int = 7

    telegram_bot_token: str | None = None
    telegram_bot_name: str | None = None
    telegram_channel_id: str | None = None
    telegram_admin_ids: str = ""
    telegram_default_min_discount: int = 20
    autopost_interval_minutes: int = 30

    # Optional source-collection integrations. They are intentionally separate
    # from the Telegram publishing bot credentials.
    telegram_collector_mode: str = "public"
    telegram_collector_api_id: str | None = None
    telegram_collector_api_hash: str | None = None
    telegram_collector_session: str | None = None
    vk_access_token: str | None = None
    vk_api_version: str = "5.199"

    @property
    def telegram_admin_id_set(self) -> set[int]:
        result: set[int] = set()
        for item in self.telegram_admin_ids.split(","):
            item = item.strip()
            if item:
                result.add(int(item))
        return result

    @property
    def setup_complete(self) -> bool:
        return bool(
            self.telegram_bot_token
            and self.telegram_channel_id
            and self.telegram_admin_id_set
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
