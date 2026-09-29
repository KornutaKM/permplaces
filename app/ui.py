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


def results_keyboard(venue_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подробнее", callback_data=f"venue:{venue_id}")],
            [InlineKeyboardButton(text="❤️ В избранное", callback_data=f"favorite:{venue_id}")],
            [
                InlineKeyboardButton(text="← Предыдущее", callback_data="results:prev"),
                InlineKeyboardButton(text="Следующее →", callback_data="results:next"),
            ],
        ]
    )


def venue_keyboard(venue_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📍 Маршрут", callback_data=f"route:{venue_id}"),
                InlineKeyboardButton(text="📖 Меню", callback_data=f"menu:{venue_id}"),
            ],
            [
                InlineKeyboardButton(text="❤️ В избранное", callback_data=f"favorite:{venue_id}"),
                InlineKeyboardButton(text="↗️ Поделиться", switch_inline_query=f"PermPlaces {venue_id}"),
            ],
            [InlineKeyboardButton(text="← Назад", callback_data="nav:categories")],
        ]
    )


def render_venue_card(venue: Venue, *, position: int = 1, total: int = 1) -> str:
    rating = (
        f"⭐ {venue.rating:.1f} ({venue.review_count})"
        if venue.rating is not None and venue.review_count is not None
        else "⭐ Рейтинг появится после подключения провайдера"
    )
    hours = f"🕐 До {venue.open_until}" if venue.open_until else "🕐 Часы работы уточняются"

    return (
        f"<b>{venue.name}</b>  <i>{position}/{total}</i>\n"
        f"{rating}\n"
        f"{venue.category_label} · {venue.price_label}\n"
        f"📍 {venue.address}\n"
        f"{hours}\n\n"
        "🧪 <i>Сейчас это демонстрационная карточка интерфейса. "
        "Реальные данные заведений подключим через provider API.</i>"
    )
