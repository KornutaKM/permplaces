from html import escape

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.data import Venue

DISTRICTS = (
    "Дзержинский",
    "Индустриальный",
    "Кировский",
    "Ленинский",
    "Мотовилихинский",
    "Орджоникидзевский",
    "Свердловский",
)

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
            [InlineKeyboardButton(text=name, callback_data=f"district:{index}")]
            for index, name in enumerate(DISTRICTS)
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def filters_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="500 м", callback_data="filter:radius:500"),
                InlineKeyboardButton(text="1 км", callback_data="filter:radius:1000"),
                InlineKeyboardButton(text="3 км", callback_data="filter:radius:3000"),
                InlineKeyboardButton(text="5 км", callback_data="filter:radius:5000"),
            ],
            [
                InlineKeyboardButton(text="₽", callback_data="filter:price:1"),
                InlineKeyboardButton(text="₽₽", callback_data="filter:price:2"),
                InlineKeyboardButton(text="₽₽₽", callback_data="filter:price:3"),
            ],
            [
                InlineKeyboardButton(text="Открыто сейчас", callback_data="filter:open:1"),
                InlineKeyboardButton(text="С верандой", callback_data="filter:terrace:1"),
            ],
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


def venue_keyboard(venue: Venue) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="📍 Маршрут", callback_data=f"route:{venue.id}"),
            InlineKeyboardButton(text="📖 Меню", callback_data=f"menu:{venue.id}"),
        ],
        [
            InlineKeyboardButton(text="❤️ В избранное", callback_data=f"favorite:{venue.id}"),
            InlineKeyboardButton(text="↗️ Поделиться", switch_inline_query=f"PermPlaces {venue.name}"),
        ],
    ]
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
        lines.append("📍 Адрес не указан в OpenStreetMap")

    if venue.opening_hours:
        lines.append(f"🕐 {escape(venue.opening_hours)}")

    if venue.cuisine:
        cuisine = ", ".join(item.replace("_", " ") for item in venue.cuisine[:4])
        lines.append(f"🍴 {escape(cuisine)}")

    if venue.source == "osm":
        lines.extend(
            [
                "",
                '<i>Данные: <a href="https://www.openstreetmap.org/copyright">'
                "© OpenStreetMap contributors</a> · ODbL</i>",
            ]
        )

    return "\n".join(lines)
