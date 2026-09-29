from urllib.parse import parse_qs, urlsplit

from app.data import SourceRef, Venue
from app.ui import (
    filters_keyboard,
    render_venue_card,
    route_keyboard,
    share_venue_url,
    venue_keyboard,
)


def test_real_osm_card_keeps_missing_facts_missing() -> None:
    venue = Venue(
        id="osm:node/1",
        name="Тестовая кофейня",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id="node/1",
        source_url="https://www.openstreetmap.org/node/1",
        distance_m=420,
    )

    card = render_venue_card(venue)

    assert "420 м" in card
    assert "Рейтинг" not in card
    assert "Средний чек" not in card
    assert "© OpenStreetMap contributors" in card


def test_card_escapes_provider_text() -> None:
    venue = Venue(
        id="osm:node/2",
        name="<b>Unsafe</b>",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id="node/2",
    )

    card = render_venue_card(venue)

    assert "&lt;b&gt;Unsafe&lt;/b&gt;" in card



def test_card_shows_sourced_district_and_phone_safely() -> None:
    venue = Venue(
        id="osm:node/3",
        name="Контактное место",
        category="restaurant",
        category_label="Ресторан",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id="node/3",
        district="Ленинский <район>",
        phone="+7 <342> 000-00-00",
    )

    card = render_venue_card(venue)

    assert "🏙 Ленинский &lt;район&gt;" in card
    assert "☎️ +7 &lt;342&gt; 000-00-00" in card


def test_venue_keyboard_accepts_only_http_website_urls() -> None:
    safe = Venue(
        id="osm:node/4",
        name="Safe",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id="node/4",
        website="https://example.org/menu",
    )
    unsafe = Venue(
        id="osm:node/5",
        name="Unsafe",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id="node/5",
        website="javascript:alert(1)",
    )

    safe_urls = [
        button.url
        for row in venue_keyboard(safe).inline_keyboard
        for button in row
        if button.url
    ]
    unsafe_urls = [
        button.url
        for row in venue_keyboard(unsafe).inline_keyboard
        for button in row
        if button.url
    ]

    assert "https://example.org/menu" in safe_urls
    assert all(not url.startswith("javascript:") for url in unsafe_urls)



def test_card_shows_only_confirmed_osm_features() -> None:
    venue = Venue(
        id="osm:node/6",
        name="Рабочая кофейня",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id="node/6",
        outdoor_seating=True,
        wifi=True,
        is_open_now=True,
    )

    card = render_venue_card(venue)

    assert "🟢 Открыто сейчас" in card
    assert "🌿 Есть места на улице / терраса" in card
    assert "📶 Есть Wi-Fi" in card


def test_filter_keyboard_marks_active_osm_filters() -> None:
    keyboard = filters_keyboard(
        radius_m=1000,
        location_scope=True,
        outdoor_seating=True,
        wifi=True,
        open_now=True,
        family_friendly=True,
        open_late=True,
    )
    labels = [
        button.text
        for row in keyboard.inline_keyboard
        for button in row
    ]

    assert "✅ 1 км" in labels
    assert "✅ 🌿 С верандой" in labels
    assert "✅ 📶 Wi-Fi" in labels
    assert "✅ 🟢 Открыто сейчас" in labels
    assert "✅ 🌙 Открыто в 23:00" in labels
    assert "✅ 👨‍👩‍👧 Для детей" in labels


def test_district_filter_keyboard_blocks_radius() -> None:
    keyboard = filters_keyboard(location_scope=False)
    first_button = keyboard.inline_keyboard[0][0]

    assert first_button.callback_data == "filter:radius:blocked"



def test_card_shows_family_features_and_late_state() -> None:
    venue = Venue(
        id="osm:node/7",
        name="Семейное место",
        category="restaurant",
        category_label="Ресторан",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id="node/7",
        kids_area=True,
        highchair=True,
        changing_table=True,
        is_open_late=True,
    )

    card = render_venue_card(venue)

    assert "🌙 Открыто сегодня в 23:00" in card
    assert "детская зона" in card
    assert "детский стульчик" in card
    assert "пеленальный столик" in card



def test_card_shows_all_merged_provider_attributions() -> None:
    venue = Venue(
        id="osm:node/8",
        name="Объединённое место",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id="node/8",
        source_refs=(
            SourceRef("osm", "node/8"),
            SourceRef("2gis", "70000001000000008"),
        ),
    )

    card = render_venue_card(venue)

    assert "OpenStreetMap contributors" in card
    assert "2ГИС" in card
    assert "Источники:" in card


def test_non_osm_missing_address_message_is_provider_neutral() -> None:
    venue = Venue(
        id="2gis:1",
        name="2GIS место",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="2gis",
        source_id="1",
        source_refs=(SourceRef("2gis", "1"),),
    )

    card = render_venue_card(venue)

    assert "Адрес не указан источником" in card
    assert "2ГИС" in card
    assert "OpenStreetMap" not in card



def test_share_button_works_without_bot_inline_mode() -> None:
    venue = Venue(
        id="2gis:70000001000000001",
        name="Тестовое место",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01046,
        longitude=56.25017,
        source="2gis",
        source_id="70000001000000001",
        address="улица Ленина, 10",
    )

    share_url = share_venue_url(venue)
    parsed = urlsplit(share_url)
    params = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "t.me"
    assert parsed.path == "/share/url"
    assert params["url"] == ["https://2gis.ru/firm/70000001000000001"]
    assert params["text"] == ["Тестовое место — улица Ленина, 10"]

    share_button = next(
        button
        for row in venue_keyboard(venue).inline_keyboard
        for button in row
        if button.text == "↗️ Поделиться"
    )
    assert share_button.url == share_url
    assert share_button.switch_inline_query is None


def test_route_keyboard_uses_provider_and_coordinate_links() -> None:
    venue = Venue(
        id="2gis:70000001000000002",
        name="Маршрутное место",
        category="restaurant",
        category_label="Ресторан",
        latitude=58.01046,
        longitude=56.25017,
        source="2gis",
        source_id="70000001000000002",
    )

    urls = {
        button.text: button.url
        for row in route_keyboard(venue).inline_keyboard
        for button in row
    }

    assert urls["🧭 2ГИС"] == "https://2gis.ru/firm/70000001000000002"
    google = urlsplit(urls["🗺 Google Maps"] or "")
    assert google.scheme == "https"
    assert google.netloc == "www.google.com"
    assert parse_qs(google.query)["destination"] == ["58.010460,56.250170"]
    assert (
        urls["🌍 OpenStreetMap"]
        == "https://www.openstreetmap.org/?mlat=58.010460&mlon=56.250170"
        "#map=18/58.010460/56.250170"
    )


def test_share_url_rejects_unsafe_source_url_and_falls_back_to_map() -> None:
    venue = Venue(
        id="osm:node/9",
        name="Unsafe source",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id="node/9",
        source_url="javascript:alert(1)",
    )

    params = parse_qs(urlsplit(share_venue_url(venue)).query)

    assert params["url"] == [
        "https://www.openstreetmap.org/?mlat=58.010000&mlon=56.250000"
        "#map=18/58.010000/56.250000"
    ]
    assert "javascript:" not in share_venue_url(venue)
