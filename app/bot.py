from dataclasses import asdict

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from app.data import Venue
from app.providers.overpass import ProviderError
from app.search import SearchService
from app.ui import (
    CATEGORY_LABELS,
    DISTRICTS,
    categories_keyboard,
    districts_keyboard,
    filters_keyboard,
    home_keyboard,
    render_venue_card,
    results_keyboard,
    scenarios_keyboard,
    venue_keyboard,
)

router = Router()


class SearchState(StatesGroup):
    awaiting_query = State()


WELCOME = """<b>Привет! 👋
Я PermPlaces — подскажу, куда сходить в Перми.</b>

🍽 Кафе, рестораны и бары
📍 Поиск рядом с вами
🎛 Удобные фильтры
🗺 Маршруты и контакты
❤️ Избранные места

Как хотите искать заведение?"""


_TEXT_CATEGORIES = {
    "кофе": "cafe",
    "кофейн": "cafe",
    "ресторан": "restaurant",
    "бар": "bar",
    "пицц": "pizza",
    "суш": "sushi",
    "завтрак": "breakfast",
    "фастфуд": "fastfood",
    "десерт": "dessert",
}

_SCENARIO_CATEGORIES = {
    "coffee": "cafe",
    "eat": "restaurant",
    "breakfast": "breakfast",
    "drink": "bar",
    "random": "restaurant",
}


def _venue_from_dict(value: dict[str, object]) -> Venue:
    cuisine = value.get("cuisine")
    if isinstance(cuisine, list):
        value = {**value, "cuisine": tuple(str(item) for item in cuisine)}
    return Venue(**value)  # type: ignore[arg-type]


def _find_result(results: list[dict[str, object]], venue_id: str) -> Venue | None:
    for raw in results:
        if raw.get("id") == venue_id:
            return _venue_from_dict(raw)
    return None


async def _run_search(
    *,
    state: FSMContext,
    search_service: SearchService,
    category: str,
) -> list[Venue] | None:
    data = await state.get_data()
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    if not isinstance(latitude, (float, int)) or not isinstance(longitude, (float, int)):
        return None

    radius_m = data.get("radius_m", 3000)
    if not isinstance(radius_m, int):
        radius_m = 3000

    venues = await search_service.nearby(
        category=category,
        latitude=float(latitude),
        longitude=float(longitude),
        radius_m=radius_m,
        limit=5,
    )
    await state.update_data(
        results=[asdict(venue) for venue in venues],
        result_index=0,
        category=category,
    )
    return venues


async def _edit_current_result(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return

    data = await state.get_data()
    results = data.get("results")
    index = data.get("result_index", 0)
    if not isinstance(results, list) or not results:
        await callback.message.edit_text(
            "Результатов пока нет. Выберите категорию:",
            reply_markup=categories_keyboard(),
        )
        return

    if not isinstance(index, int):
        index = 0
    index = max(0, min(index, len(results) - 1))
    raw = results[index]
    if not isinstance(raw, dict):
        return

    venue = _venue_from_dict(raw)
    await callback.message.edit_text(
        render_venue_card(venue, position=index + 1, total=len(results)),
        reply_markup=results_keyboard(
            venue.id,
            can_previous=index > 0,
            can_next=index < len(results) - 1,
        ),
        disable_web_page_preview=True,
    )


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(radius_m=3000)
    await message.answer(WELCOME, reply_markup=home_keyboard())


@router.message(F.location)
async def location_received(message: Message, state: FSMContext) -> None:
    if message.location is None:
        return
    await state.update_data(
        latitude=message.location.latitude,
        longitude=message.location.longitude,
        radius_m=3000,
        location_source="telegram",
    )
    await message.answer(
        "<b>Геолокация получена.</b> Ищу реальные места вокруг этой точки.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer("Что ищем? 🍴", reply_markup=categories_keyboard())


@router.message(F.text == "🏙 Выбрать район")
async def choose_district(message: Message) -> None:
    await message.answer("Где искать заведения?", reply_markup=districts_keyboard())


@router.message(F.text == "🔎 Поиск текстом")
async def ask_text_search(message: Message, state: FSMContext) -> None:
    await state.set_state(SearchState.awaiting_query)
    await message.answer(
        "Напишите категорию: <i>кофе</i>, <i>ресторан</i>, <i>бар</i>, "
        "<i>пицца</i>, <i>суши</i> или <i>завтрак</i>.",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(SearchState.awaiting_query, F.text)
async def text_search(
    message: Message,
    state: FSMContext,
    search_service: SearchService,
) -> None:
    await state.set_state(None)
    query = (message.text or "").casefold()
    category = next(
        (value for key, value in _TEXT_CATEGORIES.items() if key in query),
        None,
    )
    if category is None:
        await message.answer(
            "Пока свободный текст поддерживает категории заведений. Выберите категорию:",
            reply_markup=categories_keyboard(),
        )
        return

    try:
        venues = await _run_search(
            state=state,
            search_service=search_service,
            category=category,
        )
    except ProviderError:
        await message.answer(
            "Сервис OpenStreetMap сейчас не ответил. Попробуйте ещё раз чуть позже."
        )
        return

    if venues is None:
        await message.answer(
            "Сначала отправьте геолокацию через кнопку «📍 Рядом со мной».",
            reply_markup=home_keyboard(),
        )
        return
    if not venues:
        await message.answer(
            "В выбранном радиусе ничего не найдено. Можно увеличить радиус в фильтрах.",
            reply_markup=categories_keyboard(),
        )
        return

    venue = venues[0]
    await message.answer(
        render_venue_card(venue, position=1, total=len(venues)),
        reply_markup=results_keyboard(
            venue.id,
            can_previous=False,
            can_next=len(venues) > 1,
        ),
        disable_web_page_preview=True,
    )


@router.message(F.text == "✨ Сценарии")
async def scenarios(message: Message) -> None:
    await message.answer("Выберите готовый сценарий:", reply_markup=scenarios_keyboard())


@router.message(F.text == "❤️ Избранное")
async def favorites(message: Message) -> None:
    await message.answer(
        "❤️ <b>Избранное</b>\n\nПерсистентное хранение избранного — следующий этап."
    )


@router.callback_query(F.data == "nav:categories")
async def nav_categories(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("Что ищем? 🍴", reply_markup=categories_keyboard())


@router.callback_query(F.data == "nav:filters")
async def nav_filters(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            "<b>Настройте фильтры</b>\n\n"
            "Радиус уже работает. Остальные фильтры будут включаться только "
            "когда источник данных позволяет применить их без догадок.",
            reply_markup=filters_keyboard(),
        )


@router.callback_query(F.data.startswith("district:"))
async def district_selected(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.message or not callback.data:
        return

    value = callback.data.split(":", 1)[1]
    district = "Вся Пермь" if value == "all" else DISTRICTS[int(value)]
    await callback.message.edit_text(
        f"📍 <b>{district}</b>\n\n"
        "Точный live-поиск по административным границам районов ещё не подключён. "
        "Для реального поиска сейчас используйте «📍 Рядом со мной».",
    )


@router.callback_query(F.data.startswith("category:"))
async def category_selected(
    callback: CallbackQuery,
    state: FSMContext,
    search_service: SearchService,
) -> None:
    await callback.answer()
    if not callback.message or not callback.data:
        return

    category = callback.data.split(":", 1)[1]
    label = CATEGORY_LABELS.get(category, "Заведения")
    try:
        venues = await _run_search(
            state=state,
            search_service=search_service,
            category=category,
        )
    except ProviderError:
        await callback.message.edit_text(
            "OpenStreetMap сейчас не ответил. Вернитесь к категориям и попробуйте ещё раз.",
            reply_markup=categories_keyboard(),
        )
        return

    if venues is None:
        await callback.message.edit_text(
            f"<b>{label}</b>\n\n"
            "Для live-поиска сначала отправьте геолокацию через кнопку «📍 Рядом со мной».",
        )
        return
    if not venues:
        await callback.message.edit_text(
            f"<b>{label}</b>\n\n"
            "В выбранном радиусе OpenStreetMap не вернул подходящих мест.",
            reply_markup=categories_keyboard(),
        )
        return

    venue = venues[0]
    await callback.message.edit_text(
        render_venue_card(venue, position=1, total=len(venues)),
        reply_markup=results_keyboard(
            venue.id,
            can_previous=False,
            can_next=len(venues) > 1,
        ),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("venue:"))
async def venue_detail(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.message or not callback.data:
        return

    data = await state.get_data()
    results = data.get("results")
    if not isinstance(results, list):
        return

    venue_id = callback.data.split(":", 1)[1]
    dict_results = [item for item in results if isinstance(item, dict)]
    venue = _find_result(dict_results, venue_id)
    if venue is None:
        await callback.message.edit_text("Карточка больше не доступна. Запустите поиск снова.")
        return

    await callback.message.edit_text(
        render_venue_card(venue),
        reply_markup=venue_keyboard(venue),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("favorite:"))
async def favorite(callback: CallbackQuery) -> None:
    await callback.answer("Сохранение избранного подключим следующим этапом ❤️")


@router.callback_query(F.data.startswith("route:"))
async def route(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.message or not callback.data:
        return

    data = await state.get_data()
    results = data.get("results")
    if not isinstance(results, list):
        return

    venue_id = callback.data.split(":", 1)[1]
    dict_results = [item for item in results if isinstance(item, dict)]
    venue = _find_result(dict_results, venue_id)
    if venue is None:
        return

    await callback.message.answer_location(
        latitude=venue.latitude,
        longitude=venue.longitude,
    )


@router.callback_query(F.data.startswith("menu:"))
async def menu(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "📖 OpenStreetMap не гарантирует наличие меню. "
            "Кнопка станет активной, когда подключим источник, который предоставляет меню."
        )


@router.callback_query(F.data.startswith("scenario:"))
async def scenario(
    callback: CallbackQuery,
    state: FSMContext,
    search_service: SearchService,
) -> None:
    await callback.answer()
    if not callback.message or not callback.data:
        return

    scenario_name = callback.data.split(":", 1)[1]
    category = _SCENARIO_CATEGORIES.get(scenario_name)
    if category is None:
        await callback.message.edit_text(
            "Для этого сценария нужны дополнительные признаки заведений. "
            "Подключим его после базового каталога.",
            reply_markup=categories_keyboard(),
        )
        return

    try:
        venues = await _run_search(
            state=state,
            search_service=search_service,
            category=category,
        )
    except ProviderError:
        await callback.message.edit_text(
            "OpenStreetMap сейчас не ответил.",
            reply_markup=categories_keyboard(),
        )
        return

    if venues is None:
        await callback.message.edit_text(
            "Сначала отправьте геолокацию через «📍 Рядом со мной»."
        )
        return
    if not venues:
        await callback.message.edit_text(
            "Подходящих мест в выбранном радиусе не найдено.",
            reply_markup=categories_keyboard(),
        )
        return

    venue = venues[0]
    await callback.message.edit_text(
        render_venue_card(venue, position=1, total=len(venues)),
        reply_markup=results_keyboard(
            venue.id,
            can_previous=False,
            can_next=len(venues) > 1,
        ),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("filter:"))
async def filter_selected(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.data:
        return

    parts = callback.data.split(":")
    if len(parts) == 3 and parts[1] == "radius":
        radius_m = int(parts[2])
        await state.update_data(radius_m=radius_m)
        await callback.answer(f"Радиус: {radius_m / 1000:g} км")
        return

    await callback.answer(
        "Этот фильтр пока нельзя применить надёжно к текущему источнику данных."
    )


@router.callback_query(F.data.startswith("results:"))
async def result_navigation(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.data:
        return
    await callback.answer()

    data = await state.get_data()
    results = data.get("results")
    if not isinstance(results, list) or not results:
        return

    index = data.get("result_index", 0)
    if not isinstance(index, int):
        index = 0

    action = callback.data.split(":", 1)[1]
    if action == "prev":
        index -= 1
    elif action == "next":
        index += 1
    elif action != "current":
        return

    index = max(0, min(index, len(results) - 1))
    await state.update_data(result_index=index)
    await _edit_current_result(callback, state)
