from urllib.parse import parse_qs, urlsplit

from app.data import PhotoRef, SourceRef, Venue
from app.ui import (
    delete_data_confirmation_keyboard,
    favorite_filter_keyboard,
    favorite_note_keyboard,
    favorite_overview_keyboard,
    favorite_search_keyboard,
    favorite_sort_keyboard,
    favorite_tags_keyboard,
    filters_keyboard,
    mydata_keyboard,
    primary_photo_url,
    rating_keyboard,
    render_venue_card,
    results_keyboard,
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
        (
            "https://www.openstreetmap.org/?mlat=58.010000&mlon=56.250000"
            "#map=18/58.010000/56.250000"
        )
    ]
    assert "javascript:" not in share_venue_url(venue)


def test_foursquare_rating_card_keeps_ten_point_scale_and_attribution() -> None:
    venue = Venue(
        id="foursquare:abc",
        name="FSQ place",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="foursquare",
        source_id="abc",
        source_refs=(SourceRef("foursquare", "abc"),),
        rating=8.7,
        rating_scale=10.0,
        review_count=321,
    )

    card = render_venue_card(venue)

    assert "⭐ 8.7/10 (321)" in card
    assert "Powered by Foursquare" in card


def test_venue_keyboard_shows_only_safe_provider_menu_url() -> None:
    safe = Venue(
        id="foursquare:menu-safe",
        name="Menu safe",
        category="restaurant",
        category_label="Ресторан",
        latitude=58.01,
        longitude=56.25,
        source="foursquare",
        source_id="menu-safe",
        menu_url="https://menu.example.test/place",
    )
    unsafe = Venue(
        id="foursquare:menu-unsafe",
        name="Menu unsafe",
        category="restaurant",
        category_label="Ресторан",
        latitude=58.01,
        longitude=56.25,
        source="foursquare",
        source_id="menu-unsafe",
        menu_url="javascript:alert(1)",
    )
    missing = Venue(
        id="osm:node/menu-missing",
        name="Menu missing",
        category="restaurant",
        category_label="Ресторан",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id="node/menu-missing",
    )

    safe_menu = [
        button
        for row in venue_keyboard(safe).inline_keyboard
        for button in row
        if button.text == "📖 Меню"
    ]
    unsafe_menu = [
        button
        for row in venue_keyboard(unsafe).inline_keyboard
        for button in row
        if button.text == "📖 Меню"
    ]
    missing_menu = [
        button
        for row in venue_keyboard(missing).inline_keyboard
        for button in row
        if button.text == "📖 Меню"
    ]

    assert len(safe_menu) == 1
    assert safe_menu[0].url == "https://menu.example.test/place"
    assert safe_menu[0].callback_data is None
    assert unsafe_menu == []
    assert missing_menu == []


def test_primary_photo_url_uses_first_safe_provider_photo() -> None:
    venue = Venue(
        id="foursquare:photo",
        name="Photo place",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="foursquare",
        source_id="photo",
        photos=(
            PhotoRef(
                provider="foursquare",
                source_id="unsafe",
                url="javascript:alert(1)",
                attribution="Powered by Foursquare",
            ),
            PhotoRef(
                provider="foursquare",
                source_id="safe",
                url="https://images.example.test/original/safe.jpg",
                attribution="Powered by Foursquare",
            ),
        ),
    )

    assert primary_photo_url(venue) == "https://images.example.test/original/safe.jpg"


def test_venue_detail_keyboard_closes_without_mutating_results_message() -> None:
    venue = Venue(
        id="osm:node/detail",
        name="Detail",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id="node/detail",
    )

    close_button = next(
        button
        for row in venue_keyboard(venue).inline_keyboard
        for button in row
        if button.text == "← Закрыть карточку"
    )

    assert close_button.callback_data == "detail:close"

    favorite_button = next(
        button
        for row in venue_keyboard(venue).inline_keyboard
        for button in row
        if button.text == "❤️ В избранное"
    )
    assert favorite_button.callback_data == "detail_favorite:osm:node/detail"


def test_geoapify_card_has_required_free_plan_attribution() -> None:
    venue = Venue(
        id="geoapify:place-1",
        name="Geoapify cafe",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="geoapify",
        source_id="place-1",
        source_refs=(SourceRef("geoapify", "place-1"),),
    )

    card = render_venue_card(venue)

    assert "OpenStreetMap contributors" in card
    assert "Powered by Geoapify" in card
    assert "Источники:" in card



def test_card_distinguishes_community_rating_from_provider_rating() -> None:
    venue = Venue(
        id="osm:node/community-rating",
        name="Community place",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id="node/community-rating",
        rating=8.7,
        rating_scale=10.0,
        review_count=100,
        community_rating=4.3,
        community_rating_count=7,
    )

    card = render_venue_card(venue)

    assert "⭐ 8.7/10 (100)" in card
    assert "👥 PermPlaces: 4.3/5 (7)" in card


def test_rating_keyboard_encodes_score_and_venue_identity() -> None:
    keyboard = rating_keyboard("osm:node/42")

    callbacks = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
    ]

    assert callbacks == [
        "rating:1:osm:node/42",
        "rating:2:osm:node/42",
        "rating:3:osm:node/42",
        "rating:4:osm:node/42",
        "rating:5:osm:node/42",
    ]


def test_venue_keyboard_exposes_explicit_rating_action() -> None:
    venue = Venue(
        id="osm:node/rate",
        name="Rate me",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id="node/rate",
    )

    button = next(
        button
        for row in venue_keyboard(venue).inline_keyboard
        for button in row
        if button.text == "⭐ Оценить"
    )

    assert button.callback_data == "rate:osm:node/rate"



def test_rating_keyboard_marks_current_score_and_offers_removal() -> None:
    keyboard = rating_keyboard("osm:node/88", current_score=4)

    labels = [
        button.text
        for row in keyboard.inline_keyboard
        for button in row
    ]
    callbacks = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
    ]

    assert "✅ 4 ⭐" in labels
    assert "🗑 Удалить мою оценку" in labels
    assert "rating:remove:osm:node/88" in callbacks



def test_mydata_keyboard_exposes_export_and_delete_when_data_exists() -> None:
    assert mydata_keyboard(has_persistent_data=False) is None

    keyboard = mydata_keyboard(has_persistent_data=True)
    assert keyboard is not None
    buttons = [
        button
        for row in keyboard.inline_keyboard
        for button in row
    ]

    assert [button.text for button in buttons] == [
        "📦 Скачать JSON",
        "🗑 Удалить мои данные",
    ]
    assert [button.callback_data for button in buttons] == [
        "privacy:export",
        "privacy:delete",
    ]


def test_delete_data_confirmation_requires_explicit_confirmation() -> None:
    keyboard = delete_data_confirmation_keyboard()

    callbacks = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
    ]

    assert callbacks == [
        "privacy:delete:confirm",
        "privacy:delete:cancel",
    ]



def test_personal_note_card_is_explicit_and_html_escaped() -> None:
    venue = Venue(
        id="osm:node/note",
        name="Note place",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id="node/note",
        personal_note="<b>только моя</b>",
    )

    card = render_venue_card(venue)

    assert "📝 Ваша заметка:" in card
    assert "&lt;b&gt;только моя&lt;/b&gt;" in card
    assert "<b>только моя</b>" not in card


def test_venue_keyboard_exposes_note_only_in_favorites_context() -> None:
    venue = Venue(
        id="osm:node/note-button",
        name="Note button",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id="node/note-button",
    )

    normal_labels = [
        button.text
        for row in venue_keyboard(venue).inline_keyboard
        for button in row
    ]
    favorite_keyboard = venue_keyboard(venue, allow_note=True)
    favorite_buttons = [
        button
        for row in favorite_keyboard.inline_keyboard
        for button in row
    ]

    assert "📝 Заметка" not in normal_labels
    note_button = next(
        button
        for button in favorite_buttons
        if button.text == "📝 Заметка"
    )
    assert note_button.callback_data == "favorite_note:edit:osm:node/note-button"


def test_favorite_note_keyboard_requires_explicit_remove_or_cancel() -> None:
    without_note = favorite_note_keyboard(
        "osm:node/1",
        has_note=False,
    )
    assert [
        button.callback_data
        for row in without_note.inline_keyboard
        for button in row
    ] == ["favorite_note:cancel"]

    with_note = favorite_note_keyboard(
        "osm:node/1",
        has_note=True,
    )
    assert [
        button.callback_data
        for row in with_note.inline_keyboard
        for button in row
    ] == [
        "favorite_note:remove:osm:node/1",
        "favorite_note:cancel",
    ]



def test_personal_tags_render_as_user_labels_not_provider_facts() -> None:
    venue = Venue(
        id="osm:node/tags-card",
        name="Tagged",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id="node/tags-card",
        personal_tags=("want", "work", "unknown"),
    )

    card = render_venue_card(venue)

    assert "🏷 Ваши метки:" in card
    assert "📌 Хочу сходить" in card
    assert "💻 Для работы" in card
    assert "unknown" not in card


def test_favorite_tags_keyboard_marks_current_tags() -> None:
    keyboard = favorite_tags_keyboard(
        "osm:node/tags",
        current_tags=("return", "friends"),
    )
    buttons = [
        button
        for row in keyboard.inline_keyboard
        for button in row
    ]

    assert any(
        button.text == "✅ 🔁 Вернуться"
        and button.callback_data == "ft:return:osm:node/tags"
        for button in buttons
    )
    assert any(
        button.text == "✅ 👥 С друзьями"
        and button.callback_data == "ft:friends:osm:node/tags"
        for button in buttons
    )
    assert buttons[-1].callback_data == "ft:close"


def test_favorite_filter_keyboard_shows_counts_and_active_filter() -> None:
    keyboard = favorite_filter_keyboard(
        total=4,
        counts={"want": 2, "return": 1, "work": 0, "family": 1, "friends": 0},
        active_tag="want",
    )
    labels = [
        button.text
        for row in keyboard.inline_keyboard
        for button in row
    ]

    assert "Все (4)" in labels
    assert "✅ 📌 Хочу сходить (2)" in labels
    assert "💻 Для работы (0)" in labels


def test_favorites_results_keyboard_exposes_filter_and_remove_semantics() -> None:
    keyboard = results_keyboard(
        "osm:node/favorite",
        can_previous=False,
        can_next=True,
        favorites_mode=True,
        active_favorite_tag="work",
    )
    buttons = [
        button
        for row in keyboard.inline_keyboard
        for button in row
    ]
    labels = [button.text for button in buttons]

    assert "💔 Удалить из избранного" in labels
    assert "🏷 Фильтр по метке: 💻 Для работы" in labels
    filter_button = next(button for button in buttons if button.callback_data == "ff:menu")
    assert filter_button.text.startswith("🏷 Фильтр")


def test_venue_keyboard_exposes_tags_only_in_favorites_context() -> None:
    venue = Venue(
        id="osm:node/tag-button",
        name="Tag button",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id="node/tag-button",
    )

    normal_labels = [
        button.text
        for row in venue_keyboard(venue).inline_keyboard
        for button in row
    ]
    favorite_labels = [
        button.text
        for row in venue_keyboard(
            venue,
            allow_note=True,
            allow_tags=True,
        ).inline_keyboard
        for button in row
    ]

    assert "🏷 Мои метки" not in normal_labels
    assert "🏷 Мои метки" in favorite_labels



def test_favorite_search_keyboard_has_explicit_cancel() -> None:
    keyboard = favorite_search_keyboard()

    assert keyboard.inline_keyboard[0][0].text == "Отмена"
    assert keyboard.inline_keyboard[0][0].callback_data == "fs:cancel"


def test_favorite_results_keyboard_marks_active_search_and_clear_action() -> None:
    keyboard = results_keyboard(
        "osm:node/search",
        can_previous=False,
        can_next=False,
        favorites_mode=True,
        favorite_search_active=True,
    )
    buttons = [
        button
        for row in keyboard.inline_keyboard
        for button in row
    ]
    labels = [button.text for button in buttons]
    callbacks = [button.callback_data for button in buttons]

    assert "🔎 Новый поиск в избранном" in labels
    assert "🧹 Сбросить поиск" in labels
    assert "fs:start" in callbacks
    assert "fs:clear" in callbacks



def test_favorite_sort_keyboard_marks_active_mode() -> None:
    keyboard = favorite_sort_keyboard(active_sort="tags")
    buttons = [
        button
        for row in keyboard.inline_keyboard
        for button in row
    ]
    labels = [button.text for button in buttons]
    callbacks = [button.callback_data for button in buttons]

    assert "✅ 🏷 Сначала с метками" in labels
    assert "fso:tags" in callbacks
    assert callbacks[-1] == "results:current"


def test_favorites_results_keyboard_shows_current_sort() -> None:
    keyboard = results_keyboard(
        "osm:node/sorted",
        can_previous=False,
        can_next=False,
        favorites_mode=True,
        active_favorite_sort="name",
    )
    labels = [
        button.text
        for row in keyboard.inline_keyboard
        for button in row
    ]

    assert "↕️ Сортировка: 🔤 По названию" in labels



def test_favorite_overview_keyboard_exposes_local_management_actions() -> None:
    keyboard = favorite_overview_keyboard(active_sort="tags")
    buttons = [
        button
        for row in keyboard.inline_keyboard
        for button in row
    ]
    labels = [button.text for button in buttons]
    callbacks = [button.callback_data for button in buttons]

    assert "🏷 Фильтр по метке" in labels
    assert "🔎 Поиск в избранном" in labels
    assert "↕️ Сортировка: 🏷 Сначала с метками" in labels
    assert "← К результатам" in labels
    assert callbacks == ["ff:menu", "fs:start", "fso:menu", "results:current"]


def test_favorite_results_keyboard_exposes_overview() -> None:
    keyboard = results_keyboard(
        "osm:node/overview",
        can_previous=False,
        can_next=False,
        favorites_mode=True,
    )
    buttons = [
        button
        for row in keyboard.inline_keyboard
        for button in row
    ]

    overview = next(
        button
        for button in buttons
        if button.callback_data == "fo:overview"
    )
    assert overview.text == "📊 Обзор избранного"
