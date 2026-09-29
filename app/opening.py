from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from opening_hours import (
    InvalidCoordinatesError,
    OpeningHours,
    ParserError,
    UnknownCountryError,
)


class OpeningState(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    UNKNOWN = "unknown"


def opening_state(
    value: str | None,
    *,
    latitude: float,
    longitude: float,
    at: datetime | None = None,
) -> OpeningState:
    if not value or not value.strip():
        return OpeningState.UNKNOWN

    try:
        hours = OpeningHours(
            value.strip(),
            coords=(latitude, longitude),
            auto_timezone=True,
            auto_country=True,
        )
        if hours.is_open(at):
            return OpeningState.OPEN
        if hours.is_closed(at):
            return OpeningState.CLOSED
        return OpeningState.UNKNOWN
    except (
        ParserError,
        InvalidCoordinatesError,
        UnknownCountryError,
        TypeError,
        ValueError,
        RuntimeError,
    ):
        return OpeningState.UNKNOWN
