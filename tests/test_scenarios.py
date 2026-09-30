import pytest

from app.data import Venue
from app.scenarios import (
    ScenarioSelection,
    plan_scenario,
    rank_scenario_candidates,
    render_scenario_reasons,
    scenario_reasons,
    select_scenario_candidate,
)


def _venue(venue_id: str, name: str, **overrides: object) -> Venue:
    values: dict[str, object] = {
        "id": venue_id,
        "name": name,
        "category": "cafe",
        "category_label": "Кофейня",
        "latitude": 58.01,
        "longitude": 56.25,
        "source": "osm",
        "source_id": venue_id,
    }
    values.update(overrides)
    return Venue(**values)  # type: ignore[arg-type]


def test_planner_covers_live_scenarios_and_keeps_date_disabled() -> None:
    expected_categories = {
        "coffee": "cafe",
        "eat": "restaurant",
        "breakfast": "breakfast",
        "drink": "bar",
        "work": "cafe",
        "family": "food_drink",
        "late": "food_drink",
        "random": "food_drink",
    }

    for key, category in expected_categories.items():
        plan = plan_scenario(key)
        assert plan is not None
        assert plan.category == category

    assert plan_scenario("date") is None


def test_planner_encodes_required_provider_backed_filters() -> None:
    work = plan_scenario("work")
    family = plan_scenario("family")
    late = plan_scenario("late")
    random = plan_scenario("random")

    assert work is not None
    assert family is not None
    assert late is not None
    assert random is not None

    assert work.state_update_dict() == {"filter_wifi": True}
    assert family.state_update_dict() == {"filter_family_friendly": True}
    assert late.state_update_dict() == {"filter_open_late": True}
    assert random.state_update_dict() == {}
    assert random.candidate_limit == 20
    assert random.selection is ScenarioSelection.RANDOM


def test_search_order_ranking_and_first_selection_are_deterministic() -> None:
    plan = plan_scenario("coffee")
    assert plan is not None

    venues = [_venue("b", "Beta"), _venue("a", "Alpha")]
    ranked = rank_scenario_candidates(plan, venues)
    index, selected = select_scenario_candidate(plan, ranked)

    assert ranked == venues
    assert index == 0
    assert selected.id == "b"


def test_random_selection_is_explicit_and_injectable() -> None:
    plan = plan_scenario("random")
    assert plan is not None

    venues = [_venue("a", "Alpha"), _venue("b", "Beta")]
    index, selected = select_scenario_candidate(
        plan,
        venues,
        choose_index=lambda size: size - 1,
    )

    assert index == 1
    assert selected.id == "b"


def test_explanations_fail_closed_when_facts_are_unknown() -> None:
    plan = plan_scenario("work")
    assert plan is not None

    venue = _venue("unknown", "Unknown")

    assert scenario_reasons(plan, venue) == ()
    assert render_scenario_reasons(plan, venue) == ""


def test_explanations_use_only_confirmed_or_calculated_facts() -> None:
    plan = plan_scenario("work")
    assert plan is not None

    venue = _venue(
        "facts",
        "Facts",
        distance_m=850,
        wifi=True,
        kids_area=True,
        highchair=True,
        is_open_now=True,
        is_open_late=True,
        rating=8.7,
        rating_scale=10.0,
        review_count=123,
        price_label="₽₽",
    )

    reasons = scenario_reasons(plan, venue)

    assert reasons == (
        "Wi-Fi подтверждён данными источника",
        "Открыто сейчас по подтверждённым данным",
        "Для детей подтверждено: детская зона, детский стульчик",
        "Открыто сегодня в 23:00 по подтверждённым данным",
        "Расстояние: 850 м",
        "Рейтинг источника: 8.7/10 · оценок: 123",
        "Ценовой уровень источника: ₽₽",
    )
    rendered = render_scenario_reasons(plan, venue)
    assert rendered.startswith("<b>Почему подходит</b>\n")
    assert "• Расстояние: 850 м" in rendered


def test_rating_without_scale_is_not_used_as_scenario_reason() -> None:
    plan = plan_scenario("coffee")
    assert plan is not None

    venue = _venue("rating", "Rating", rating=9.5)

    assert scenario_reasons(plan, venue) == ()


def test_selection_rejects_empty_candidates() -> None:
    plan = plan_scenario("coffee")
    assert plan is not None

    with pytest.raises(ValueError, match="empty"):
        select_scenario_candidate(plan, [])
