from dataclasses import asdict, replace
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from app.data import FieldSource, PhotoRef, SourceRef, Venue
from app.districts import DISTRICT_BY_KEY, PERM_DISTRICTS, PERM_RELATION_ID
from app.filters import PlaceFilters
from app.providers.capabilities import ProviderStatus, render_provider_statuses
from app.providers.overpass import ProviderError
from app.query import parse_search_query, plan_search_query
from app.ratings import RatingsRepository
from app.scenarios import (
    plan_scenario,
    rank_scenario_candidates,
    render_scenario_reasons,
    select_scenario_candidate,
)
from app.search import SearchService
from app.storage import FavoritesRepository
from app.ui import (
    CATEGORY_LABELS,
    categories_keyboard,
    districts_keyboard,
    filters_keyboard,
    home_keyboard,
    primary_photo_url,
    rating_keyboard,
    render_venue_card,
    results_keyboard,
    route_keyboard,
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


def _filters_from_state(data: dict[str, object]) -> PlaceFilters:
    return PlaceFilters(
        outdoor_seating=data.get("filter_outdoor_seating") is True,
        wifi=data.get("filter_wifi") is True,
        open_now=data.get("filter_open_now") is True,
        family_friendly=data.get("filter_family_friendly") is True,
        open_late=data.get("filter_open_late") is True,
    )


def _venue_from_dict(value: dict[str, object]) -> Venue:
    restored = dict(value)

    cuisine = restored.get("cuisine")
    if isinstance(cuisine, list):
        restored["cuisine"] = tuple(str(item) for item in cuisine)

    source_refs = restored.get("source_refs")
    if isinstance(source_refs, (list, tuple)):
        restored["source_refs"] = tuple(
            SourceRef(**item)
            for item in source_refs
            if isinstance(item, dict)
        )

    field_sources = restored.get("field_sources")
    if isinstance(field_sources, (list, tuple)):
        restored["field_sources"] = tuple(
            FieldSource(**item)
            for item in field_sources
            if isinstance(item, dict)
        )

    photos = restored.get("photos")
    if isinstance(photos, (list, tuple)):
        restored["photos"] = tuple(
            PhotoRef(**item)
            for item in photos
            if isinstance(item, dict)
        )

    return Venue(**restored)  # type: ignore[arg-type]


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
    limit: int = 5,
    result_scenario: str | None = None,
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
            limit=limit,
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
            limit=limit,
            filters=filters,
        )
    else:
        return None

    await state.update_data(
        results=[asdict(venue) for venue in venues],
        result_index=0,
        category=category,
        result_scenario=result_scenario,
    )
    return venues


def _render_result_card(
    venue: Venue,
    *,
    position: int,
    total: int,
    scenario_name: str | None = None,
) -> str:
    card = render_venue_card(venue, position=position, total=total)
    if scenario_name is None:
        return card

    plan = plan_scenario(scenario_name)
    if plan is None:
        return card

    parts: list[str] = []
    if plan.heading:
        parts.append(f"<b>{plan.heading}</b>")
    parts.append(card)

    reasons = render_scenario_reasons(plan, venue)
    if reasons:
        parts.append(reasons)
    return "\n\n".join(parts)


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
    scenario_name = data.get("result_scenario")
    await callback.message.edit_text(
        _render_result_card(
            venue,
            position=index + 1,
            total=len(results),
            scenario_name=scenario_name if isinstance(scenario_name, str) else None,
        ),
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
        filter_open_now=False,
        filter_family_friendly=False,
        filter_open_late=False,
    )
    await message.answer(WELCOME, reply_markup=home_keyboard())


@router.message(Command("providers"))
async def provider_diagnostics(
    message: Message,
    provider_statuses: tuple[ProviderStatus, ...],
) -> None:
    await message.answer(
        render_provider_statuses(provider_statuses),
        disable_web_page_preview=True,
    )


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
        "<b>Опишите, что ищете.</b>\n\n"
        "Например:\n"
        "• <i>кофе с Wi-Fi рядом 1 км</i>\n"
        "• <i>ресторан с верандой в Ленинском районе</i>\n"
        "• <i>суши открыто сейчас по всей Перми</i>\n"
        "• <i>ресторан с детьми</i>\n"
        "• <i>кафе поздно вечером</i>",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(SearchState.awaiting_query, F.text)
async def text_search(
    message: Message,
    state: FSMContext,
    search_service: SearchService,
) -> None:
    await state.set_state(None)
    parsed = parse_search_query(message.text or "")

    if parsed.category is None:
        await message.answer(
            "Не удалось определить категорию. Попробуйте, например: "
            "«кофе с Wi-Fi рядом», «ресторан в Ленинском районе» "
            "или выберите категорию кнопкой.",
            reply_markup=categories_keyboard(),
        )
        return

    if parsed.invalid_radius:
        await message.answer(
            "Радиус в текстовом поиске должен быть от 100 м до 10 км. "
            "Например: «кофе рядом 1,5 км»."
        )
        return

    data = await state.get_data()
    plan = plan_search_query(parsed, data)
    await state.update_data(**plan.updates)

    if plan.requires_location:
        await message.answer(
            "Для поиска «рядом» нужна геолокация. "
            "Отправьте её через кнопку «📍 Рядом со мной».",
            reply_markup=home_keyboard(),
        )
        return

    try:
        venues = await _run_search(
            state=state,
            search_service=search_service,
            category=parsed.category,
        )
    except ProviderError:
        await message.answer(
            "Источники мест сейчас не ответили. Попробуйте ещё раз чуть позже."
        )
        return

    if venues is None:
        await message.answer(
            "Укажите область поиска: выберите район Перми или отправьте геолокацию.",
            reply_markup=home_keyboard(),
        )
        return

    if not venues:
        await message.answer(
            "По заданным условиям ничего не найдено. "
            "Попробуйте убрать Wi-Fi/веранду/«Открыто сейчас», "
            "увеличить радиус или выбрать другой район.",
            reply_markup=categories_keyboard(),
        )
        return

    if plan.radius_ignored:
        await message.answer(
            "ℹ️ Радиус из текста не применяется при поиске внутри выбранного района."
        )

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
    ratings_repository: RatingsRepository,
) -> None:
    if message.from_user is None:
        return

    venues = await favorites_repository.list_for_user(user_id=message.from_user.id)
    venues = await ratings_repository.enrich_many(venues)
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
        result_scenario=None,
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
        "🌿/📶/👨‍👩‍👧 фильтры применяются только к источникам, которые умеют "
        "подтверждать соответствующий признак.\n"
        "🟢/🌙 время работы также проверяется только по подтверждаемым данным.",
        reply_markup=filters_keyboard(
            radius_m=(
                data.get("radius_m")
                if isinstance(data.get("radius_m"), int)
                else 3000
            ),
            location_scope=scope != "district",
            outdoor_seating=data.get("filter_outdoor_seating") is True,
            wifi=data.get("filter_wifi") is True,
            open_now=data.get("filter_open_now") is True,
            family_friendly=data.get("filter_family_friendly") is True,
            open_late=data.get("filter_open_late") is True,
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
            "Источники мест сейчас не ответили. Вернитесь к категориям и попробуйте ещё раз.",
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
            "В выбранной области источники не вернули подходящих мест.",
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


async def _send_venue_detail(message: Message, venue: Venue) -> None:
    card = render_venue_card(venue)
    photo_url = primary_photo_url(venue)
    if photo_url and len(card) <= 1024:
        try:
            await message.answer_photo(
                photo=photo_url,
                caption=card,
                reply_markup=venue_keyboard(venue),
            )
            return
        except TelegramBadRequest:
            pass

    await message.answer(
        card,
        reply_markup=venue_keyboard(venue),
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

    await _send_venue_detail(callback.message, venue)


@router.callback_query(F.data == "detail:close")
async def close_venue_detail(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.delete()


@router.callback_query(
    F.data.startswith("favorite:") | F.data.startswith("detail_favorite:")
)
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

    from_detail = callback.data.startswith("detail_favorite:")
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
            if from_detail:
                await callback.message.delete()
                await callback.message.answer(
                    "❤️ <b>Избранное пока пусто.</b>\n\n"
                    "Сохраните новое место из результатов поиска."
                )
            else:
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

    if from_detail and callback.message:
        raw = updated_results[index]
        if isinstance(raw, dict):
            current = _venue_from_dict(raw)
            await callback.message.delete()
            await callback.message.answer(
                render_venue_card(
                    current,
                    position=index + 1,
                    total=len(updated_results),
                ),
                reply_markup=results_keyboard(
                    current.id,
                    can_previous=index > 0,
                    can_next=index < len(updated_results) - 1,
                ),
                disable_web_page_preview=True,
            )
        return

    await _edit_current_result(callback, state)


@router.callback_query(F.data.startswith("rate:"))
async def rate_venue(
    callback: CallbackQuery,
    state: FSMContext,
    ratings_repository: RatingsRepository,
) -> None:
    await callback.answer()
    if not callback.message or not callback.data:
        return

    venue_id = callback.data.split(":", 1)[1]
    data = await state.get_data()
    results = data.get("results")
    if not isinstance(results, list):
        await callback.message.answer("Карточка устарела. Запустите поиск снова.")
        return

    dict_results = [item for item in results if isinstance(item, dict)]
    venue = _find_result(dict_results, venue_id)
    if venue is None:
        await callback.message.answer("Карточка устарела. Запустите поиск снова.")
        return

    current_score = await ratings_repository.user_rating_for_venue(
        user_id=callback.from_user.id,
        venue=venue,
    )
    current_note = (
        f"\nВаша текущая оценка: <b>{current_score}/5</b>."
        if current_score is not None
        else ""
    )
    await callback.message.answer(
        f"⭐ <b>Оцените {escape(venue.name)}</b>\n\n"
        "Оценка хранится как мнение пользователей PermPlaces и не заменяет "
        f"рейтинг внешнего источника.{current_note}",
        reply_markup=rating_keyboard(
            venue.id,
            current_score=current_score,
        ),
    )


@router.callback_query(F.data.startswith("rating:"))
async def rating_selected(
    callback: CallbackQuery,
    state: FSMContext,
    ratings_repository: RatingsRepository,
) -> None:
    if not callback.data:
        return

    parts = callback.data.split(":", 2)
    if len(parts) != 3:
        await callback.answer("Некорректная оценка.")
        return

    action = parts[1]
    score: int | None = None
    if action != "remove":
        try:
            score = int(action)
        except ValueError:
            await callback.answer("Некорректная оценка.")
            return
        if not 1 <= score <= 5:
            await callback.answer("Оценка должна быть от 1 до 5.")
            return

    venue_id = parts[2]
    data = await state.get_data()
    results = data.get("results")
    if not isinstance(results, list):
        await callback.answer("Карточка устарела. Запустите поиск снова.")
        return

    dict_results = [item for item in results if isinstance(item, dict)]
    venue = _find_result(dict_results, venue_id)
    if venue is None:
        await callback.answer("Карточка устарела. Запустите поиск снова.")
        return

    if action == "remove":
        summary = await ratings_repository.remove_rating(
            user_id=callback.from_user.id,
            venue=venue,
        )
    else:
        assert score is not None
        summary = await ratings_repository.set_rating(
            user_id=callback.from_user.id,
            venue=venue,
            score=score,
        )

    updated_venue = replace(
        venue,
        community_rating=summary.average,
        community_rating_count=summary.count or None,
    )
    updated_results = [
        asdict(updated_venue) if item.get("id") == venue_id else item
        for item in dict_results
    ]
    await state.update_data(results=updated_results)

    if action == "remove":
        await callback.answer("Оценка удалена")
        if callback.message:
            aggregate = (
                f"\n👥 PermPlaces: <b>{summary.average:.1f}/5</b> ({summary.count})"
                if summary.average is not None and summary.count > 0
                else ""
            )
            await callback.message.edit_text(
                "🗑 Ваша оценка удалена." + aggregate
            )
        return

    await callback.answer("Оценка сохранена ⭐")
    if callback.message:
        average = summary.average if summary.average is not None else float(score)
        await callback.message.edit_text(
            f"⭐ Ваша оценка: <b>{score}/5</b>\n"
            f"👥 PermPlaces: <b>{average:.1f}/5</b> "
            f"({summary.count})"
        )


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
        reply_markup=route_keyboard(venue),
    )


@router.callback_query(F.data.startswith("menu:"))
async def menu(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "📖 Для этой старой карточки ссылка на меню недоступна. "
            "Запустите поиск снова: новая карточка покажет кнопку только при "
            "подтверждённой ссылке от провайдера."
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
    plan = plan_scenario(scenario_name)
    if plan is None:
        await callback.message.edit_text(
            "Для этого сценария нужны дополнительные подтверждаемые признаки заведений. "
            "Подключим его, когда появится надёжный provider-backed сигнал.",
            reply_markup=categories_keyboard(),
        )
        return

    updates = plan.state_update_dict()
    if updates:
        await state.update_data(**updates)

    try:
        venues = await _run_search(
            state=state,
            search_service=search_service,
            category=plan.category,
            limit=plan.candidate_limit,
            result_scenario=plan.key,
        )
    except ProviderError:
        await callback.message.edit_text(
            "Источники мест сейчас не ответили.",
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

    ranked = rank_scenario_candidates(plan, venues)
    index, venue = select_scenario_candidate(plan, ranked)
    await state.update_data(
        results=[asdict(item) for item in ranked],
        result_index=index,
        result_scenario=plan.key,
    )

    await callback.message.edit_text(
        _render_result_card(
            venue,
            position=index + 1,
            total=len(ranked),
            scenario_name=plan.key,
        ),
        reply_markup=results_keyboard(
            venue.id,
            can_previous=index > 0,
            can_next=index < len(ranked) - 1,
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

    elif action == "open" and value == "toggle":
        enabled = data.get("filter_open_now") is not True
        await state.update_data(filter_open_now=enabled)
        await callback.answer(
            "Открыто сейчас: включено" if enabled else "Открыто сейчас: выключено"
        )

    elif action == "late" and value == "toggle":
        enabled = data.get("filter_open_late") is not True
        await state.update_data(filter_open_late=enabled)
        await callback.answer(
            "Открыто в 23:00: включено" if enabled else "Открыто в 23:00: выключено"
        )

    elif action == "family" and value == "toggle":
        enabled = data.get("filter_family_friendly") is not True
        await state.update_data(filter_family_friendly=enabled)
        await callback.answer(
            "Для детей: включено" if enabled else "Для детей: выключено"
        )

    elif action == "reset" and value == "all":
        await state.update_data(
            radius_m=3000,
            filter_outdoor_seating=False,
            filter_wifi=False,
            filter_open_now=False,
            filter_family_friendly=False,
            filter_open_late=False,
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
                open_now=refreshed.get("filter_open_now") is True,
                family_friendly=refreshed.get("filter_family_friendly") is True,
                open_late=refreshed.get("filter_open_late") is True,
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
