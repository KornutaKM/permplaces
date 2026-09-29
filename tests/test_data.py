from app.data import Venue
from app.ui import render_venue_card, venue_keyboard


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
