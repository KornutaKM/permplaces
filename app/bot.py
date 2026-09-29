from dataclasses import asdict

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from app.data import Venue
from app.districts import DISTRICT_BY_KEY, PERM_DISTRICTS, PERM_RELATION_ID
from app.filters import PlaceFilters
from app.providers.overpass import ProviderError
from app.search import SearchService
from app.storage import FavoritesRepository
from app.ui import (
    CATEGORY_LABELS,
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
🏙 Поиск по районам Перми
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
    "work": "cafe",
    "random": "restaurant",
}


def _filters_from_state(data: dict[str, object]) -> PlaceFilters:
    return PlaceFilters(
        outdoor_seating=data.get("filter_outdoor_seating") is True,
        wifi=data.get("filter_wifi") is True,
    )


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
    scope = data.get("search_scope")
    filters = _filters_from_state(data)

    if scope == "district":
        relation_id = data.get("district_relation_id")
        district_name = data.get("district_name")
        if not isinstance(relation_id, int) or not isinstance(district_name, str):
            return None

        venues = await search_service.in_district(
            category=category,
            relation_id=relation_id,
            district_name=district_name,
            limit=5,
            filters=filters,
        )
    elif scope == "location":
        latitude = data.get("latitude")
        longitude = data.get("longitude")
        if not isinstance(latitude, (float, int)) or not isinstance(
            longitude, (float, int)
        ):
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
            filters=filters,
        )
    else:
        return None

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
    await state.update_data(
        radius_m=3000,
        filter_outdoor_seating=False,
        filter_wifi=False,
    )
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
        search_scope="location",
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

    if scenario_name == "work":
        await state.update_data(filter_wifi=True)

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
            "Сначала выберите район Перми или отправьте геолокацию.",
            reply_markup=home_keyboard(),
        )
        return
    if not venues:
        await message.answer(
            "В выбранной области ничего не найдено. Попробуйте другую категорию.",
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
async def favorites(
    message: Message,
    state: FSMContext,
    favorites_repository: FavoritesRepository,
) -> None:
    if message.from_user is None:
        return

    venues = await favorites_repository.list_for_user(user_id=message.from_user.id)
    if not venues:
        await message.answer(
            "❤️ <b>Избранное пока пусто.</b>\n\n"
            "Откройте найденное место и нажмите «❤️ В избранное»."
        )
        return

    await state.update_data(
        results=[asdict(venue) for venue in venues],
        result_index=0,
        category="favorites",
    )
    venue = venues[0]
    await message.answer(
        "❤️ <b>Избранное</b>\n\n"
        + render_venue_card(venue, position=1, total=len(venues)),
        reply_markup=results_keyboard(
            venue.id,
            can_previous=False,
            can_next=len(venues) > 1,
        ),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data == "nav:categories")
async def nav_categories(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("Что ищем? 🍴", reply_markup=categories_keyboard())


@router.callback_query(F.data == "nav:filters")
async def nav_filters(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.message:
        return

    data = await state.get_data()
    scope = data.get("search_scope")
    scope_note = (
        "Радиус применяется только в режиме «📍 Рядом со мной»."
        if scope == "district"
        else "Радиус уже работает для поиска рядом."
    )
    await callback.message.edit_text(
        "<b>Настройте фильтры</b>\n\n"
        f"{scope_note}\n"
        "🌿 Веранда и 📶 Wi-Fi применяются только по явным тегам OpenStreetMap.",
        reply_markup=filters_keyboard(
            radius_m=data.get("radius_m") if isinstance(data.get("radius_m"), int) else 3000,
            location_scope=scope != "district",
            outdoor_seating=data.get("filter_outdoor_seating") is True,
            wifi=data.get("filter_wifi") is True,
        ),
    )


@router.callback_query(F.data.startswith("district:"))
async def district_selected(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.message or not callback.data:
        return

    value = callback.data.split(":", 1)[1]
    if value == "all":
        district_name = "Вся Пермь"
        relation_id = PERM_RELATION_ID
    else:
        district = DISTRICT_BY_KEY.get(value)

        # Backward compatibility for keyboards sent by the pre-v0.4 bot.
        if district is None and value.isdigit():
            index = int(value)
            if 0 <= index < len(PERM_DISTRICTS):
                district = PERM_DISTRICTS[index]

        if district is None:
            await callback.message.edit_text(
                "Этот район больше не распознан. Выберите район заново.",
                reply_markup=districts_keyboard(),
            )
            return

        district_name = district.name
        relation_id = district.relation_id

    await state.update_data(
        search_scope="district",
        district_name=district_name,
        district_relation_id=relation_id,
    )
    await callback.message.edit_text(
        f"🏙 <b>{district_name}</b>\n\n"
        "Граница района взята из OpenStreetMap. Теперь выберите категорию:",
        reply_markup=categories_keyboard(),
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
            "Сначала выберите район Перми или отправьте геолокацию.",
        )
        return
    if not venues:
        await callback.message.edit_text(
            f"<b>{label}</b>\n\n"
            "В выбранной области OpenStreetMap не вернул подходящих мест.",
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
async def favorite(
    callback: CallbackQuery,
    state: FSMContext,
    favorites_repository: FavoritesRepository,
) -> None:
    if not callback.data:
        return

    data = await state.get_data()
    results = data.get("results")
    if not isinstance(results, list):
        await callback.answer("Карточка устарела. Запустите поиск снова.")
        return

    venue_id = callback.data.split(":", 1)[1]
    dict_results = [item for item in results if isinstance(item, dict)]
    venue = _find_result(dict_results, venue_id)
    if venue is None:
        await callback.answer("Карточка устарела. Запустите поиск снова.")
        return

    saved = await favorites_repository.toggle(
        user_id=callback.from_user.id,
        venue=venue,
    )
    await callback.answer(
        "Добавлено в избранное ❤️" if saved else "Удалено из избранного"
    )

    if saved or data.get("category") != "favorites":
        return

    updated_results = [
        item
        for item in dict_results
        if item.get("id") != venue_id
    ]
    if not updated_results:
        await state.update_data(results=[], result_index=0)
        if callback.message:
            await callback.message.edit_text(
                "❤️ <b>Избранное пока пусто.</b>\n\n"
                "Сохраните новое место из результатов поиска."
            )
        return

    index = data.get("result_index", 0)
    if not isinstance(index, int):
        index = 0
    index = min(index, len(updated_results) - 1)
    await state.update_data(results=updated_results, result_index=index)
    await _edit_current_result(callback, state)


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
            "Сначала выберите район Перми или отправьте геолокацию."
        )
        return
    if not venues:
        await callback.message.edit_text(
            "Подходящих мест в выбранной области не найдено.",
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
    if len(parts) != 3:
        await callback.answer("Неизвестный фильтр.")
        return

    data = await state.get_data()
    scope = data.get("search_scope")
    action = parts[1]
    value = parts[2]

    if action == "radius":
        if scope == "district" or value == "blocked":
            await callback.answer("Радиус используется только в режиме «Рядом со мной».")
            return

        radius_m = int(value)
        await state.update_data(radius_m=radius_m)
        await callback.answer(f"Радиус: {radius_m / 1000:g} км")

    elif action == "terrace" and value == "toggle":
        enabled = data.get("filter_outdoor_seating") is not True
        await state.update_data(filter_outdoor_seating=enabled)
        await callback.answer("Веранда: включено" if enabled else "Веранда: выключено")

    elif action == "wifi" and value == "toggle":
        enabled = data.get("filter_wifi") is not True
        await state.update_data(filter_wifi=enabled)
        await callback.answer("Wi-Fi: включено" if enabled else "Wi-Fi: выключено")

    elif action == "reset" and value == "all":
        await state.update_data(
            radius_m=3000,
            filter_outdoor_seating=False,
            filter_wifi=False,
        )
        await callback.answer("Фильтры сброшены")

    else:
        await callback.answer("Этот фильтр не поддерживается.")
        return

    if callback.message:
        refreshed = await state.get_data()
        await callback.message.edit_reply_markup(
            reply_markup=filters_keyboard(
                radius_m=(
                    refreshed.get("radius_m")
                    if isinstance(refreshed.get("radius_m"), int)
                    else 3000
                ),
                location_scope=refreshed.get("search_scope") != "district",
                outdoor_seating=refreshed.get("filter_outdoor_seating") is True,
                wifi=refreshed.get("filter_wifi") is True,
            )
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
