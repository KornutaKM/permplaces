from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def overpass_endpoints(primary: str, fallbacks_csv: str) -> tuple[str, ...]:
    candidates = [primary, *fallbacks_csv.split(",")]
    endpoints: list[str] = []
    for candidate in candidates:
        endpoint = candidate.strip()
        if endpoint and endpoint not in endpoints:
            endpoints.append(endpoint)
    return tuple(endpoints)


class Settings(BaseSettings):
    bot_token: str = Field(alias="BOT_TOKEN")
    overpass_url: str = Field(
        default="https://overpass-api.de/api/interpreter",
        alias="OVERPASS_URL",
    )
    overpass_fallback_urls: str = Field(default="", alias="OVERPASS_FALLBACK_URLS")
    overpass_timeout_seconds: float = Field(default=20.0, alias="OVERPASS_TIMEOUT_SECONDS")
    database_path: str = Field(default="data/permplaces.db", alias="DATABASE_PATH")
    provider_cache_ttl_seconds: float = Field(default=120.0, alias="PROVIDER_CACHE_TTL_SECONDS")
    provider_cache_max_entries: int = Field(default=256, alias="PROVIDER_CACHE_MAX_ENTRIES")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def overpass_endpoints(self) -> tuple[str, ...]:
        return overpass_endpoints(self.overpass_url, self.overpass_fallback_urls)


def load_settings() -> Settings:
    return Settings()
