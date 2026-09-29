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
