from datetime import UTC, datetime

from app.opening import OpeningState, opening_state


PERM_LAT = 58.01046
PERM_LON = 56.25017
FIXED_TIME = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)


def test_24_7_is_open() -> None:
    assert (
        opening_state(
            "24/7",
            latitude=PERM_LAT,
            longitude=PERM_LON,
            at=FIXED_TIME,
        )
        is OpeningState.OPEN
    )


def test_explicit_closed_state_is_closed() -> None:
    assert (
        opening_state(
            "24/7 off",
            latitude=PERM_LAT,
            longitude=PERM_LON,
            at=FIXED_TIME,
        )
        is OpeningState.CLOSED
    )


def test_unknown_state_is_not_promoted_to_open() -> None:
    assert (
        opening_state(
            "24/7 unknown",
            latitude=PERM_LAT,
            longitude=PERM_LON,
            at=FIXED_TIME,
        )
        is OpeningState.UNKNOWN
    )


def test_invalid_or_missing_expression_fails_closed_to_unknown() -> None:
    assert (
        opening_state(
            "definitely not opening hours",
            latitude=PERM_LAT,
            longitude=PERM_LON,
            at=FIXED_TIME,
        )
        is OpeningState.UNKNOWN
    )
    assert (
        opening_state(
            None,
            latitude=PERM_LAT,
            longitude=PERM_LON,
            at=FIXED_TIME,
        )
        is OpeningState.UNKNOWN
    )
