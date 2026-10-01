from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

PACKAGE_NAME = "permplaces"
REPOSITORY_URL = "https://github.com/KornutaKM/permplaces"


def installed_app_version() -> str:
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:
        return "0+unknown"


APP_VERSION = installed_app_version()
PERMPLACES_USER_AGENT = f"PermPlaces/{APP_VERSION} (+{REPOSITORY_URL})"
