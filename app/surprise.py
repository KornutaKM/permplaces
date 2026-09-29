from __future__ import annotations

from collections.abc import Callable, Sequence
from secrets import randbelow

from app.data import Venue


def choose_surprise(
    venues: Sequence[Venue],
    *,
    choose_index: Callable[[int], int] = randbelow,
) -> tuple[int, Venue]:
    if not venues:
        raise ValueError("Cannot choose a surprise venue from an empty sequence")

    index = choose_index(len(venues))
    if not 0 <= index < len(venues):
        raise ValueError("Random index provider returned an out-of-range value")

    return index, venues[index]
