from app.filters import PlaceFilters
from app.query import ParsedSearchQuery, parse_search_query


def test_parse_category_filters_radius_and_district() -> None:
    parsed = parse_search_query(
        "Кофе с Wi-Fi и верандой в Ленинском районе не дальше 1,5 км"
    )

    assert parsed == ParsedSearchQuery(
        category="cafe",
        outdoor_seating=True,
        wifi=True,
        radius_m=1500,
        district_key="leninsky",
        whole_city=False,
        nearby=False,
    )


def test_parse_common_category_synonyms() -> None:
    assert parse_search_query("где позавтракать").category == "breakfast"
    assert parse_search_query("хочу роллы").category == "sushi"
    assert parse_search_query("найди паб").category == "bar"
    assert parse_search_query("хочу бургер").category == "fastfood"


def test_parse_whole_perm() -> None:
    parsed = parse_search_query("ресторан по всей Перми")

    assert parsed.category == "restaurant"
    assert parsed.whole_city is True
    assert parsed.district_key is None


def test_radius_supports_meters_and_kilometers() -> None:
    assert parse_search_query("кафе 700 м").radius_m == 700
    assert parse_search_query("кафе 2 км").radius_m == 2000
    assert parse_search_query("кафе 2.5 километра").radius_m == 2500


def test_radius_is_bounded() -> None:
    assert parse_search_query("кафе 50 м").radius_m is None
    assert parse_search_query("кафе 25 км").radius_m is None


def test_unknown_text_stays_explicitly_unparsed() -> None:
    parsed = parse_search_query("что-нибудь необычное")

    assert parsed.category is None
    assert parsed.filters == PlaceFilters()
    assert parsed.outdoor_seating is None
    assert parsed.wifi is None
    assert parsed.radius_m is None
    assert parsed.district_key is None
    assert parsed.whole_city is False
    assert parsed.nearby is False



def test_negated_features_do_not_enable_filters() -> None:
    parsed = parse_search_query("кафе без Wi-Fi и без веранды")

    assert parsed.filters == PlaceFilters()



def test_parse_nearby_intent() -> None:
    parsed = parse_search_query("кофе с вайфаем рядом")

    assert parsed.category == "cafe"
    assert parsed.filters.wifi is True
    assert parsed.nearby is True
