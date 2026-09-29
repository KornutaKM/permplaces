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
) -> InlineKeyboardMarkup:
    navigation: list[InlineKeyboardButton] = []
    if can_previous:
        navigation.append(
            InlineKeyboardButton(text="← Предыдущее", callback_data="results:prev")
        )
    if can_next:
        navigation.append(InlineKeyboardButton(text="Следующее →", callback_data="results:next"))

    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="Подробнее", callback_data=f"venue:{venue_id}")],
        [InlineKeyboardButton(text="❤️ В избранное", callback_data=f"favorite:{venue_id}")],
    ]
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
    target_url = source_url or _twogis_url(venue)

    details = venue.address or venue.category_label
    text = venue.name if not details else f"{venue.name} — {details}"
    return "https://t.me/share/url?" + urlencode(
        {
            "url": target_url,
            "text": text,
        }
    )


def venue_keyboard(venue: Venue) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="📍 Маршрут", callback_data=f"route:{venue.id}"),
            InlineKeyboardButton(text="📖 Меню", callback_data=f"menu:{venue.id}"),
        ],
    ]

    website_url = _safe_http_url(venue.website)
    if website_url:
        rows.append([InlineKeyboardButton(text="🌐 Сайт", url=website_url)])

    rows.append(
        [
            InlineKeyboardButton(text="❤️ В избранное", callback_data=f"favorite:{venue.id}"),
            InlineKeyboardButton(text="↗️ Поделиться", url=share_venue_url(venue)),
        ]
    )
    if venue.source_url:
        rows.append([InlineKeyboardButton(text="🗺 Открыть в OSM", url=venue.source_url)])
    rows.append([InlineKeyboardButton(text="← Назад к результатам", callback_data="results:current")])
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
        if venue.review_count is not None:
            rating += f" ({venue.review_count})"
        lines.append(rating)

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

    attribution: list[str] = []
    if "osm" in providers:
        attribution.append(
            '<a href="https://www.openstreetmap.org/copyright">'
            "© OpenStreetMap contributors</a> · ODbL"
        )
    if "2gis" in providers:
        attribution.append("2ГИС")

    if attribution:
        lines.extend(["", "<i>Источники: " + "; ".join(attribution) + "</i>"])

    return "\n".join(lines)
