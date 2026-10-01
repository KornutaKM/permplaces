from importlib.metadata import version

from app.version import (
    APP_VERSION,
    PACKAGE_NAME,
    PERMPLACES_USER_AGENT,
    REPOSITORY_URL,
    installed_app_version,
)


def test_runtime_version_matches_installed_package_metadata() -> None:
    expected = version(PACKAGE_NAME)

    assert installed_app_version() == expected
    assert APP_VERSION == expected


def test_user_agent_is_derived_from_runtime_version() -> None:
    assert PERMPLACES_USER_AGENT == (
        f"PermPlaces/{APP_VERSION} (+{REPOSITORY_URL})"
    )
    assert "0+unknown" not in PERMPLACES_USER_AGENT
