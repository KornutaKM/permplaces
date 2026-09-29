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
    twogis_api_key: str = Field(default="", alias="TWOGIS_API_KEY")
    twogis_url: str = Field(
        default="https://catalog.api.2gis.com/3.0/items",
        alias="TWOGIS_URL",
    )
    twogis_timeout_seconds: float = Field(default=10.0, alias="TWOGIS_TIMEOUT_SECONDS")
    foursquare_api_key: str = Field(default="", alias="FOURSQUARE_API_KEY")
    foursquare_url: str = Field(
        default="https://places-api.foursquare.com/places/search",
        alias="FOURSQUARE_URL",
    )
    foursquare_timeout_seconds: float = Field(
        default=10.0,
        alias="FOURSQUARE_TIMEOUT_SECONDS",
    )
    health_host: str = Field(default="0.0.0.0", alias="HEALTH_HOST")
    health_port: int = Field(default=8080, alias="HEALTH_PORT", ge=1, le=65535)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def overpass_endpoints(self) -> tuple[str, ...]:
        return overpass_endpoints(self.overpass_url, self.overpass_fallback_urls)


def load_settings() -> Settings:
    return Settings()
