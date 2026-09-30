from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from html import escape

from app.data import Venue
from app.surprise import choose_surprise


class ScenarioRanking(StrEnum):
    SEARCH_ORDER = "search_order"


class ScenarioSelection(StrEnum):
    FIRST = "first"
    RANDOM = "random"


@dataclass(frozen=True, slots=True)
class ScenarioDefinition:
    key: str
    category: str
    candidate_limit: int = 5
    required_state_updates: tuple[tuple[str, bool], ...] = ()
    ranking: ScenarioRanking = ScenarioRanking.SEARCH_ORDER
    selection: ScenarioSelection = ScenarioSelection.FIRST
    heading: str | None = None


@dataclass(frozen=True, slots=True)
class ScenarioPlan:
    key: str
    category: str
    candidate_limit: int
    state_updates: tuple[tuple[str, bool], ...]
    ranking: ScenarioRanking
    selection: ScenarioSelection
    heading: str | None = None

    def state_update_dict(self) -> dict[str, object]:
        return dict(self.state_updates)


SCENARIO_DEFINITIONS: tuple[ScenarioDefinition, ...] = (
    ScenarioDefinition(key="coffee", category="cafe"),
    ScenarioDefinition(key="eat", category="restaurant"),
    ScenarioDefinition(key="breakfast", category="breakfast"),
    ScenarioDefinition(key="drink", category="bar"),
    ScenarioDefinition(
        key="work",
        category="cafe",
        required_state_updates=(("filter_wifi", True),),
    ),
    ScenarioDefinition(
        key="family",
        category="food_drink",
        required_state_updates=(("filter_family_friendly", True),),
        heading="👨‍👩‍👧 Места с подтверждёнными удобствами для детей",
    ),
    ScenarioDefinition(
        key="late",
        category="food_drink",
        required_state_updates=(("filter_open_late", True),),
        heading="🌙 Открыто сегодня в 23:00 по подтверждённому графику",
    ),
    ScenarioDefinition(
        key="random",
        category="food_drink",
        candidate_limit=20,
        selection=ScenarioSelection.RANDOM,
        heading="🎲 Случайный выбор",
    ),
)

_SCENARIO_BY_KEY = {definition.key: definition for definition in SCENARIO_DEFINITIONS}


def plan_scenario(key: str) -> ScenarioPlan | None:
    definition = _SCENARIO_BY_KEY.get(key)
    if definition is None:
        return None

    return ScenarioPlan(
        key=definition.key,
        category=definition.category,
        candidate_limit=definition.candidate_limit,
        state_updates=definition.required_state_updates,
        ranking=definition.ranking,
        selection=definition.selection,
        heading=definition.heading,
    )


def rank_scenario_candidates(
    plan: ScenarioPlan,
    venues: Sequence[Venue],
) -> list[Venue]:
    if plan.ranking is ScenarioRanking.SEARCH_ORDER:
        # SearchService already applies deterministic, scope-specific ordering:
        # distance + name for nearby and name + source_id for district search.
        return list(venues)

    raise ValueError(f"Unsupported scenario ranking strategy: {plan.ranking}")


def select_scenario_candidate(
    plan: ScenarioPlan,
    venues: Sequence[Venue],
    *,
    choose_index: Callable[[int], int] | None = None,
) -> tuple[int, Venue]:
    if not venues:
        raise ValueError("Cannot select a scenario venue from an empty sequence")

    if plan.selection is ScenarioSelection.FIRST:
        return 0, venues[0]

    if plan.selection is ScenarioSelection.RANDOM:
        if choose_index is None:
            return choose_surprise(venues)
        return choose_surprise(venues, choose_index=choose_index)

    raise ValueError(f"Unsupported scenario selection strategy: {plan.selection}")


def _distance_reason(distance_m: int | None) -> str | None:
    if distance_m is None:
        return None
    if distance_m < 1000:
        return f"Расстояние: {distance_m} м"
    return f"Расстояние: {distance_m / 1000:.1f} км"


def _family_reason(venue: Venue) -> str | None:
    features: list[str] = []
    if venue.kids_area is True:
        features.append("детская зона")
    if venue.highchair is True:
        features.append("детский стульчик")
    if venue.changing_table is True:
        features.append("пеленальный столик")
    if not features:
        return None
    return "Для детей подтверждено: " + ", ".join(features)


def _rating_reason(venue: Venue) -> str | None:
    if venue.rating is None or venue.rating_scale is None:
        return None

    reason = f"Рейтинг источника: {venue.rating:.1f}/{venue.rating_scale:g}"
    if venue.review_count is not None:
        reason += f" · оценок: {venue.review_count}"
    return reason


def scenario_reasons(plan: ScenarioPlan, venue: Venue) -> tuple[str, ...]:
    reasons: list[str] = []

    def add(reason: str | None) -> None:
        if reason and reason not in reasons:
            reasons.append(reason)

    required_keys = {key for key, enabled in plan.state_updates if enabled}

    if "filter_wifi" in required_keys and venue.wifi is True:
        add("Wi-Fi подтверждён данными источника")
    if "filter_family_friendly" in required_keys:
        add(_family_reason(venue))
    if "filter_open_late" in required_keys and venue.is_open_late is True:
        add("Открыто сегодня в 23:00 по подтверждённым данным")

    if venue.is_open_now is True:
        add("Открыто сейчас по подтверждённым данным")
    if venue.wifi is True:
        add("Wi-Fi подтверждён данными источника")
    add(_family_reason(venue))
    if venue.is_open_late is True:
        add("Открыто сегодня в 23:00 по подтверждённым данным")
    add(_distance_reason(venue.distance_m))
    add(_rating_reason(venue))
    if venue.price_label:
        add(f"Ценовой уровень источника: {venue.price_label}")

    return tuple(reasons)


def render_scenario_reasons(plan: ScenarioPlan, venue: Venue) -> str:
    reasons = scenario_reasons(plan, venue)
    if not reasons:
        return ""

    lines = ["<b>Почему подходит</b>"]
    lines.extend(f"• {escape(reason)}" for reason in reasons)
    return "\n".join(lines)
