import pytest
from pydantic import ValidationError

from app.config import Settings, overpass_endpoints


def test_overpass_endpoints_preserve_order_and_deduplicate() -> None:
    assert overpass_endpoints(
        "https://primary.test/api",
        " https://fallback-a.test/api,https://fallback-b.test/api,"
        "https://fallback-a.test/api ",
    ) == (
        "https://primary.test/api",
        "https://fallback-a.test/api",
        "https://fallback-b.test/api",
    )


def test_overpass_endpoints_ignore_empty_fallbacks() -> None:
    assert overpass_endpoints("https://primary.test/api", " , ") == (
        "https://primary.test/api",
    )



def test_health_port_validation() -> None:
    with pytest.raises(ValidationError):
        Settings(BOT_TOKEN="123456:abcdefghijklmnopqrstuvwxyzABCDE", HEALTH_PORT=0)

    settings = Settings(
        BOT_TOKEN="123456:abcdefghijklmnopqrstuvwxyzABCDE",
        HEALTH_PORT=9090,
    )
    assert settings.health_port == 9090


def test_geoapify_settings_are_opt_in() -> None:
    settings = Settings(BOT_TOKEN="123456:abcdefghijklmnopqrstuvwxyzABCDE")
    assert settings.geoapify_api_key == ""
    assert settings.geoapify_url == "https://api.geoapify.com/v2/places"
    assert settings.geoapify_timeout_seconds == 10.0
    assert settings.geoapify_daily_request_budget == 2500

    configured = Settings(
        BOT_TOKEN="123456:abcdefghijklmnopqrstuvwxyzABCDE",
        GEOAPIFY_API_KEY="free-key",
        GEOAPIFY_URL="https://example.test/v2/places",
        GEOAPIFY_TIMEOUT_SECONDS=4.5,
        GEOAPIFY_DAILY_REQUEST_BUDGET=1234,
    )
    assert configured.geoapify_api_key == "free-key"
    assert configured.geoapify_url == "https://example.test/v2/places"
    assert configured.geoapify_timeout_seconds == 4.5
    assert configured.geoapify_daily_request_budget == 1234

    with pytest.raises(ValidationError):
        Settings(
            BOT_TOKEN="123456:abcdefghijklmnopqrstuvwxyzABCDE",
            GEOAPIFY_DAILY_REQUEST_BUDGET=0,
        )
