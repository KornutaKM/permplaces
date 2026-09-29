from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str = Field(alias="BOT_TOKEN")
    overpass_url: str = Field(
        default="https://overpass-api.de/api/interpreter",
        alias="OVERPASS_URL",
    )
    overpass_timeout_seconds: float = Field(default=20.0, alias="OVERPASS_TIMEOUT_SECONDS")
    database_path: str = Field(default="data/permplaces.db", alias="DATABASE_PATH")
    provider_cache_ttl_seconds: float = Field(default=120.0, alias="PROVIDER_CACHE_TTL_SECONDS")
    provider_cache_max_entries: int = Field(default=256, alias="PROVIDER_CACHE_MAX_ENTRIES")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


def load_settings() -> Settings:
    return Settings()
