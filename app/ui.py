from html import escape
from urllib.parse import quote, urlencode, urlsplit

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.data import Venue
from app.districts import PERM_DISTRICTS
from app.favorite_compare import FavoriteCompareOption
from app.favorite_facets import FavoriteFacets
from app.favorite_sort import DEFAULT_FAVORITE_SORT, FAVORITE_SORT_LABELS
from app.tags import FAVORITE_TAG_KEYS, FAVORITE_TAG_LABELS

CATEGORY_LABELS = {
    "restaurant": "🍽 Рестораны",
    "cafe": "☕ Кофейни",
    "bar": "🍺 Бары",
    "breakfast": "🥐 Завтраки",
    "pizza": "🍕 Пицца",
    "sushi": "🍣 Суши",
    "fastfood": "🍔 Фастфуд",
    "dessert": "🧁 Десерты",
}


def home_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Рядом со мной", request_location=True)],
            [KeyboardButton(text="🏙 Выбрать район"), KeyboardButton(text="🔎 Поиск текстом")],
            [KeyboardButton(text="✨ Сценарии"), KeyboardButton(text="❤️ Избранное")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Куда хотите сходить?",
    )


def categories_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    items = list(CATEGORY_LABELS.items())
    for index in range(0, len(items), 2):
        rows.append(
            [
                InlineKeyboardButton(text=label, callback_data=f"category:{key}")
                for key, label in items[index : index + 2]
            ]
        )
    rows.append([InlineKeyboardButton(text="🎲 Удиви меня", callback_data="scenario:random")])
    rows.append([InlineKeyboardButton(text="🎛 Фильтры", callback_data="nav:filters")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def districts_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📍 Вся Пермь", callback_data="district:all")],
        *[
            [
                InlineKeyboardButton(
                    text=district.name,
                    callback_data=f"district:{district.key}",
                )
            ]
            for district in PERM_DISTRICTS
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def filters_keyboard(
    *,
    radius_m: int = 3000,
    location_scope: bool = True,
    outdoor_seating: bool = False,
    wifi: bool = False,
    open_now: bool = False,
    family_friendly: bool = False,
    open_late: bool = False,
) -> InlineKeyboardMarkup:
    if location_scope:
        radius_buttons = []
        for value, label in ((500, "500 м"), (1000, "1 км"), (3000, "3 км"), (5000, "5 км")):
            prefix = "✅ " if radius_m == value else ""
            radius_buttons.append(
                InlineKeyboardButton(
                    text=f"{prefix}{label}",
                    callback_data=f"filter:radius:{value}",
                )
            )
        radius_row = radius_buttons
    else:
        radius_row = [
            InlineKeyboardButton(
                text="📍 Радиус — только «Рядом со мной»",
                callback_data="filter:radius:blocked",
            )
        ]

    return InlineKeyboardMarkup(
        inline_keyboard=[
            radius_row,
            [
                InlineKeyboardButton(
                    text=("✅ " if outdoor_seating else "") + "🌿 С верандой",
                    callback_data="filter:terrace:toggle",
                ),
                InlineKeyboardButton(
                    text=("✅ " if wifi else "") + "📶 Wi-Fi",
                    callback_data="filter:wifi:toggle",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=("✅ " if open_now else "") + "🟢 Открыто сейчас",
                    callback_data="filter:open:toggle",
                ),
                InlineKeyboardButton(
                    text=("✅ " if open_late else "") + "🌙 Открыто в 23:00",
                    callback_data="filter:late:toggle",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=("✅ " if family_friendly else "") + "👨‍👩‍👧 Для детей",
                    callback_data="filter:family:toggle",
                )
            ],
            [InlineKeyboardButton(text="🧹 Сбросить фильтры", callback_data="filter:reset:all")],
            [InlineKeyboardButton(text="← К категориям", callback_data="nav:categories")],
        ]
    )


def scenarios_keyboard() -> InlineKeyboardMarkup:
    scenarios = (
        ("☕ Выпить кофе", "coffee"),
        ("🍽 Поесть", "eat"),
        ("🥐 Позавтракать", "breakfast"),
        ("🍺 Выпить", "drink"),
        ("❤️ На свидание", "date"),
        ("👨‍👩‍👧 С детьми", "family"),
        ("💻 Поработать (Wi-Fi)", "work"),
        ("🌙 Поздно вечером", "late"),
        ("🎲 Куда-нибудь", "random"),
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"scenario:{key}")]
            for label, key in scenarios
        ]
    )


def results_keyboard(
    venue_id: str,
    *,
    can_previous: bool,
    can_next: bool,
    favorites_mode: bool = False,
    active_favorite_tag: str | None = None,
    favorite_search_active: bool = False,
    active_favorite_sort: str = DEFAULT_FAVORITE_SORT,
) -> InlineKeyboardMarkup:
    navigation: list[InlineKeyboardButton] = []
    if can_previous:
        navigation.append(
            InlineKeyboardButton(text="← Предыдущее", callback_data="results:prev")
        )
    if can_next:
        navigation.append(InlineKeyboardButton(text="Следующее →", callback_data="results:next"))

    favorite_label = "💔 Удалить из избранного" if favorites_mode else "❤️ В избранное"
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="Подробнее", callback_data=f"venue:{venue_id}")],
        [InlineKeyboardButton(text=favorite_label, callback_data=f"favorite:{venue_id}")],
    ]
    if favorites_mode:
        filter_label = "🏷 Фильтр по метке"
        if active_favorite_tag in FAVORITE_TAG_LABELS:
            filter_label += f": {FAVORITE_TAG_LABELS[active_favorite_tag]}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=filter_label,
                    callback_data="ff:menu",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="🧩 Категория / район / кухня",
                    callback_data="fx:menu",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        "🔎 Новый поиск в избранном"
                        if favorite_search_active
                        else "🔎 Поиск в избранном"
                    ),
                    callback_data="fs:start",
                )
            ]
        )
        if favorite_search_active:
            rows.append(
                [
                    InlineKeyboardButton(
                        text="🧹 Сбросить поиск",
                        callback_data="fs:clear",
                    )
                ]
            )
        sort_label = FAVORITE_SORT_LABELS.get(
            active_favorite_sort,
            FAVORITE_SORT_LABELS[DEFAULT_FAVORITE_SORT],
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"↕️ Сортировка: {sort_label}",
                    callback_data="fso:menu",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="📊 Обзор избранного",
                    callback_data="fo:overview",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="⚖️ Сравнить с другим избранным",
                    callback_data="fcmp:start",
                )
            ]
        )
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton(text="← К категориям", callback_data="nav:categories")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _safe_http_url(value: str | None) -> str | None:
    if not value:
        return None

    candidate = value.strip()
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return candidate


def primary_photo_url(venue: Venue) -> str | None:
    for photo in venue.photos:
        url = _safe_http_url(photo.url)
        if url:
            return url
    return None


def _twogis_source_id(venue: Venue) -> str | None:
    if venue.source == "2gis" and venue.source_id:
        return venue.source_id
    for ref in venue.source_refs:
        if ref.provider == "2gis" and ref.source_id:
            return ref.source_id
    return None


def _twogis_url(venue: Venue) -> str:
    source_id = _twogis_source_id(venue)
    if source_id:
        return f"https://2gis.ru/firm/{quote(source_id, safe='')}"
    return f"https://2gis.ru/geo/{venue.longitude:.6f},{venue.latitude:.6f}"


def _osm_point_url(venue: Venue) -> str:
    lat = f"{venue.latitude:.6f}"
    lon = f"{venue.longitude:.6f}"
    return f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=18/{lat}/{lon}"


def _google_directions_url(venue: Venue) -> str:
    query = urlencode(
        {
            "api": "1",
            "destination": f"{venue.latitude:.6f},{venue.longitude:.6f}",
        }
    )
    return f"https://www.google.com/maps/dir/?{query}"


def route_keyboard(venue: Venue) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🧭 2ГИС", url=_twogis_url(venue)),
                InlineKeyboardButton(
                    text="🗺 Google Maps",
                    url=_google_directions_url(venue),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🌍 OpenStreetMap",
                    url=_osm_point_url(venue),
                )
            ],
        ]
    )


def share_venue_url(venue: Venue) -> str:
    source_url = _safe_http_url(venue.source_url)
    if source_url:
        target_url = source_url
    elif _twogis_source_id(venue):
        target_url = _twogis_url(venue)
    else:
        target_url = _osm_point_url(venue)

    details = venue.address or venue.category_label
    text = venue.name if not details else f"{venue.name} — {details}"
    return "https://t.me/share/url?" + urlencode(
        {
            "url": target_url,
            "text": text,
        }
    )


def mydata_keyboard(
    *,
    has_persistent_data: bool,
) -> InlineKeyboardMarkup | None:
    if not has_persistent_data:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📦 Скачать JSON",
                    callback_data="privacy:export",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить мои данные",
                    callback_data="privacy:delete",
                )
            ],
        ]
    )


def delete_data_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, удалить",
                    callback_data="privacy:delete:confirm",
                ),
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data="privacy:delete:cancel",
                ),
            ]
        ]
    )


def favorite_note_keyboard(
    venue_id: str,
    *,
    has_note: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if has_note:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🗑 Удалить заметку",
                    callback_data=f"favorite_note:remove:{venue_id}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="Отмена",
                callback_data="favorite_note:cancel",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def favorite_overview_keyboard(
    *,
    active_sort: str,
) -> InlineKeyboardMarkup:
    sort_label = FAVORITE_SORT_LABELS.get(
        active_sort,
        FAVORITE_SORT_LABELS[DEFAULT_FAVORITE_SORT],
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏷 Фильтр по метке",
                    callback_data="ff:menu",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🧩 Категория / район / кухня",
                    callback_data="fx:menu",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔎 Поиск в избранном",
                    callback_data="fs:start",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"↕️ Сортировка: {sort_label}",
                    callback_data="fso:menu",
                )
            ],
            [
                InlineKeyboardButton(
                    text="← К результатам",
                    callback_data="results:current",
                )
            ],
        ]
    )


def _facet_active_label(
    options: tuple,
    value: str | None,
) -> str | None:
    if value is None:
        return None
    for option in options:
        if option.value == value:
            return option.label
    return value


def favorite_facets_keyboard(
    facets: FavoriteFacets,
    *,
    active_category: str | None,
    active_district: str | None,
    district_missing: bool,
    active_cuisine: str | None,
    cuisine_missing: bool,
) -> InlineKeyboardMarkup:
    category_label = _facet_active_label(facets.categories, active_category) or "все"
    if district_missing:
        district_label = "не указан"
    else:
        district_label = _facet_active_label(facets.districts, active_district) or "все"
    if cuisine_missing:
        cuisine_label = "не указана"
    else:
        cuisine_label = _facet_active_label(facets.cuisines, active_cuisine) or "все"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🍽 Категория: {category_label}",
                    callback_data="fx:categories",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🏙 Район: {district_label}",
                    callback_data="fx:districts",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🍜 Кухня: {cuisine_label}",
                    callback_data="fx:cuisines",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🧹 Сбросить локальные facets",
                    callback_data="fx:reset",
                )
            ],
            [
                InlineKeyboardButton(
                    text="← К результатам",
                    callback_data="results:current",
                )
            ],
        ]
    )


def favorite_category_facets_keyboard(
    facets: FavoriteFacets,
    *,
    active_category: str | None,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=("✅ " if active_category is None else "") + "Все категории",
                callback_data="fx:c:all",
            )
        ]
    ]
    rows.extend(
        [
            InlineKeyboardButton(
                text=("✅ " if active_category == option.value else "")
                + f"{option.label} ({option.count})",
                callback_data=f"fx:c:{option.token}",
            )
        ]
        for option in facets.categories
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="← К фильтрам",
                callback_data="fx:menu",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def favorite_district_facets_keyboard(
    facets: FavoriteFacets,
    *,
    active_district: str | None,
    district_missing: bool,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=(
                    "✅ Все районы"
                    if active_district is None and not district_missing
                    else "Все районы"
                ),
                callback_data="fx:d:all",
            )
        ]
    ]
    rows.extend(
        [
            InlineKeyboardButton(
                text=("✅ " if active_district == option.value and not district_missing else "")
                + f"{option.label} ({option.count})",
                callback_data=f"fx:d:{option.token}",
            )
        ]
        for option in facets.districts
    )
    if facets.missing_district:
        rows.append(
            [
                InlineKeyboardButton(
                    text=("✅ " if district_missing else "")
                    + f"Район не указан ({facets.missing_district})",
                    callback_data="fx:d:missing",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="← К фильтрам",
                callback_data="fx:menu",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def favorite_cuisine_facets_keyboard(
    facets: FavoriteFacets,
    *,
    active_cuisine: str | None,
    cuisine_missing: bool,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=(
                    "✅ Все кухни"
                    if active_cuisine is None and not cuisine_missing
                    else "Все кухни"
                ),
                callback_data="fx:u:all",
            )
        ]
    ]
    rows.extend(
        [
            InlineKeyboardButton(
                text=("✅ " if active_cuisine == option.value and not cuisine_missing else "")
                + f"{option.label} ({option.count})",
                callback_data=f"fx:u:{option.token}",
            )
        ]
        for option in facets.cuisines
    )
    if facets.missing_cuisine:
        rows.append(
            [
                InlineKeyboardButton(
                    text=("✅ " if cuisine_missing else "")
                    + f"Кухня не указана ({facets.missing_cuisine})",
                    callback_data="fx:u:missing",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="← К фильтрам",
                callback_data="fx:menu",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def favorite_sort_keyboard(
    *,
    active_sort: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=("✅ " if active_sort == key else "") + label,
                    callback_data=f"fso:{key}",
                )
            ]
            for key, label in FAVORITE_SORT_LABELS.items()
        ]
        + [
            [
                InlineKeyboardButton(
                    text="← К результатам",
                    callback_data="results:current",
                )
            ]
        ]
    )


def _truncate_button_label(value: str, *, limit: int = 44) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def favorite_compare_keyboard(
    options: tuple[FavoriteCompareOption, ...],
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=_truncate_button_label(option.venue.name),
                callback_data=f"fcmp:pick:{option.token}",
            )
        ]
        for option in options
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="← К результатам",
                callback_data="results:current",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def favorite_comparison_result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚖️ Сравнить с другим",
                    callback_data="fcmp:choose",
                )
            ],
            [
                InlineKeyboardButton(
                    text="← К результатам",
                    callback_data="results:current",
                )
            ],
        ]
    )


def favorite_search_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data="fs:cancel",
                )
            ]
        ]
    )


def favorite_tags_keyboard(
    venue_id: str,
    *,
    current_tags: tuple[str, ...],
) -> InlineKeyboardMarkup:
    active = set(current_tags)
    rows = [
        [
            InlineKeyboardButton(
                text=("✅ " if tag in active else "") + FAVORITE_TAG_LABELS[tag],
                callback_data=f"ft:{tag}:{venue_id}",
            )
        ]
        for tag in FAVORITE_TAG_KEYS
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="← Закрыть метки",
                callback_data="ft:close",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def favorite_filter_keyboard(
    *,
    total: int,
    counts: dict[str, int],
    active_tag: str | None,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=("✅ " if active_tag is None else "") + f"Все ({total})",
                callback_data="ff:all",
            )
        ]
    ]
    for tag in FAVORITE_TAG_KEYS:
        count = counts.get(tag, 0)
        rows.append(
            [
                InlineKeyboardButton(
                    text=("✅ " if active_tag == tag else "")
                    + f"{FAVORITE_TAG_LABELS[tag]} ({count})",
                    callback_data=f"ff:{tag}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="← К результатам",
                callback_data="results:current",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def rating_keyboard(
    venue_id: str,
    *,
    current_score: int | None = None,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=("✅ " if current_score == score else "") + f"{score} ⭐",
                callback_data=f"rating:{score}:{venue_id}",
            )
            for score in range(1, 6)
        ]
    ]
    if current_score is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🗑 Удалить мою оценку",
                    callback_data=f"rating:remove:{venue_id}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def venue_keyboard(
    venue: Venue,
    *,
    allow_note: bool = False,
    allow_tags: bool = False,
) -> InlineKeyboardMarkup:
    primary_actions = [
        InlineKeyboardButton(text="📍 Маршрут", callback_data=f"route:{venue.id}")
    ]
    menu_url = _safe_http_url(venue.menu_url)
    if menu_url:
        primary_actions.append(InlineKeyboardButton(text="📖 Меню", url=menu_url))

    rows: list[list[InlineKeyboardButton]] = [primary_actions]

    website_url = _safe_http_url(venue.website)
    if website_url:
        rows.append([InlineKeyboardButton(text="🌐 Сайт", url=website_url)])

    rows.append(
        [
            InlineKeyboardButton(
                text="⭐ Оценить",
                callback_data=f"rate:{venue.id}",
            )
        ]
    )
    if allow_note:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📝 Заметка",
                    callback_data=f"favorite_note:edit:{venue.id}",
                )
            ]
        )
    if allow_tags:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🏷 Мои метки",
                    callback_data=f"ft:menu:{venue.id}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="❤️ В избранное",
                callback_data=f"detail_favorite:{venue.id}",
            ),
            InlineKeyboardButton(text="↗️ Поделиться", url=share_venue_url(venue)),
        ]
    )
    source_url = _safe_http_url(venue.source_url)
    if source_url:
        source_label = {
            "osm": "🗺 Открыть в OSM",
            "2gis": "🗺 Открыть в 2ГИС",
            "foursquare": "🗺 Открыть в Foursquare",
            "geoapify": "🗺 Открыть источник",
        }.get(venue.source, "🗺 Открыть источник")
        rows.append([InlineKeyboardButton(text=source_label, url=source_url)])
    rows.append([InlineKeyboardButton(text="← Закрыть карточку", callback_data="detail:close")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _format_distance(distance: int | None) -> str | None:
    if distance is None:
        return None
    if distance < 1000:
        return f"📏 {distance} м"
    return f"📏 {distance / 1000:.1f} км"


def render_venue_card(venue: Venue, *, position: int = 1, total: int = 1) -> str:
    lines = [f"<b>{escape(venue.name)}</b>  <i>{position}/{total}</i>"]

    if venue.rating is not None:
        rating = f"⭐ {venue.rating:.1f}"
        if venue.rating_scale is not None:
            rating += f"/{venue.rating_scale:g}"
        if venue.review_count is not None:
            rating += f" ({venue.review_count})"
        lines.append(rating)

    if (
        venue.community_rating is not None
        and venue.community_rating_count is not None
        and venue.community_rating_count > 0
    ):
        lines.append(
            "👥 PermPlaces: "
            f"{venue.community_rating:.1f}/5 "
            f"({venue.community_rating_count})"
        )

    if venue.personal_note:
        lines.append(f"📝 Ваша заметка: {escape(venue.personal_note)}")

    tag_labels = [
        FAVORITE_TAG_LABELS[tag]
        for tag in venue.personal_tags
        if tag in FAVORITE_TAG_LABELS
    ]
    if tag_labels:
        lines.append(
            "🏷 Ваши метки: " + ", ".join(escape(label) for label in tag_labels)
        )

    details = [escape(venue.category_label)]
    if venue.price_label:
        details.append(escape(venue.price_label))
    lines.append(" · ".join(details))

    distance = _format_distance(venue.distance_m)
    if distance:
        lines.append(distance)

    if venue.address:
        lines.append(f"📍 {escape(venue.address)}")
    else:
        lines.append("📍 Адрес не указан источником")

    if venue.district:
        lines.append(f"🏙 {escape(venue.district)}")

    if venue.is_open_now:
        lines.append("🟢 Открыто сейчас")

    if venue.is_open_late:
        lines.append("🌙 Открыто сегодня в 23:00")

    if venue.opening_hours:
        lines.append(f"🕐 {escape(venue.opening_hours)}")

    if venue.cuisine:
        cuisine = ", ".join(item.replace("_", " ") for item in venue.cuisine[:4])
        lines.append(f"🍴 {escape(cuisine)}")

    if venue.outdoor_seating:
        lines.append("🌿 Есть места на улице / терраса")

    if venue.wifi:
        lines.append("📶 Есть Wi-Fi")

    family_features: list[str] = []
    if venue.kids_area:
        family_features.append("детская зона")
    if venue.highchair:
        family_features.append("детский стульчик")
    if venue.changing_table:
        family_features.append("пеленальный столик")
    if family_features:
        lines.append("👨‍👩‍👧 Для детей: " + ", ".join(family_features))

    if venue.phone:
        lines.append(f"☎️ {escape(venue.phone)}")

    providers = {
        ref.provider
        for ref in venue.source_refs
    } or {venue.source}
    attribution = _provider_attribution(providers)
    if attribution:
        lines.extend(["", "<i>Источники: " + "; ".join(attribution) + "</i>"])

    return "\n".join(lines)


def _provider_attribution(providers: set[str]) -> list[str]:
    attribution: list[str] = []
    if "osm" in providers or "geoapify" in providers:
        attribution.append(
            '<a href="https://www.openstreetmap.org/copyright">'
            "© OpenStreetMap contributors</a> · ODbL"
        )
    if "geoapify" in providers:
        attribution.append(
            '<a href="https://www.geoapify.com/">Powered by Geoapify</a>'
        )
    if "2gis" in providers:
        attribution.append("2ГИС")
    if "foursquare" in providers:
        attribution.append('<a href="https://foursquare.com/">Powered by Foursquare</a>')
    return attribution


def _saved_bool(value: bool | None) -> str:
    if value is True:
        return "да"
    if value is False:
        return "нет"
    return "не указано"


def _saved_rating(venue: Venue) -> str:
    if venue.rating is None or venue.rating_scale is None:
        return "не указан"
    value = f"{venue.rating:.1f}/{venue.rating_scale:g}"
    if venue.review_count is not None:
        value += f" ({venue.review_count})"
    return value


def _saved_community_rating(venue: Venue) -> str:
    if (
        venue.community_rating is None
        or venue.community_rating_count is None
        or venue.community_rating_count <= 0
    ):
        return "нет оценок"
    return f"{venue.community_rating:.1f}/5 ({venue.community_rating_count})"


def _saved_family_features(venue: Venue) -> str:
    values: list[str] = []
    if venue.kids_area is True:
        values.append("детская зона")
    if venue.highchair is True:
        values.append("детский стульчик")
    if venue.changing_table is True:
        values.append("пеленальный столик")
    return ", ".join(values) if values else "не указаны"


def _saved_tags(venue: Venue) -> str:
    labels = [
        FAVORITE_TAG_LABELS[tag]
        for tag in venue.personal_tags
        if tag in FAVORITE_TAG_LABELS
    ]
    return ", ".join(labels) if labels else "нет"


def _comparison_block(venue: Venue, *, number: int) -> list[str]:
    cuisine = (
        ", ".join(item.replace("_", " ") for item in venue.cuisine[:6])
        if venue.cuisine
        else "не указана"
    )
    return [
        f"<b>{number}. {escape(venue.name)}</b>",
        f"Тип: {escape(venue.category_label)}",
        "Адрес: "
        + (escape(venue.address) if venue.address else "не указан источником"),
        "Район: "
        + (escape(venue.district) if venue.district else "не указан источником"),
        f"Кухня: {escape(cuisine)}",
        "Часы: "
        + (escape(venue.opening_hours) if venue.opening_hours else "не указаны"),
        "Wi-Fi: " + _saved_bool(venue.wifi),
        "Веранда: " + _saved_bool(venue.outdoor_seating),
        "Для детей: " + escape(_saved_family_features(venue)),
        "Цена: "
        + (escape(venue.price_label) if venue.price_label else "не указана"),
        "Рейтинг источника: " + escape(_saved_rating(venue)),
        "PermPlaces: " + escape(_saved_community_rating(venue)),
        "Ваши метки: " + escape(_saved_tags(venue)),
    ]


def render_favorite_comparison(first: Venue, second: Venue) -> str:
    lines = [
        "⚖️ <b>Сравнение избранного</b>",
        "",
        *_comparison_block(first, number=1),
        "",
        *_comparison_block(second, number=2),
        "",
        (
            "<i>Сравнение использует сохранённые snapshot-поля и не определяет победителя. "
            "Текущий open-state и distance не сравниваются. Рейтинги источников показываются "
            "только вместе с их сохранённой шкалой; шкалы разных провайдеров не нормализуются.</i>"
        ),
    ]

    providers: set[str] = set()
    for venue in (first, second):
        if venue.source_refs:
            providers.update(ref.provider for ref in venue.source_refs)
        else:
            providers.add(venue.source)
    attribution = _provider_attribution(providers)
    if attribution:
        lines.extend(
            [
                "",
                "<i>Источники сохранённых карточек: "
                + "; ".join(attribution)
                + "</i>",
            ]
        )
    return "\n".join(lines)
