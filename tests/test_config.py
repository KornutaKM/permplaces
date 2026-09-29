from app.config import overpass_endpoints


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
