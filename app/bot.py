import sqlite3
from dataclasses import asdict, replace
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message, ReplyKeyboardRemove

from app.data import FieldSource, PhotoRef, SourceRef, Venue
from app.districts import DISTRICT_BY_KEY, PERM_DISTRICTS, PERM_RELATION_ID
from app.filters import PlaceFilters
from app.notes import MAX_PERSONAL_NOTE_LENGTH, NotesRepository
from app.privacy import USER_DATA_EXPORT_FILENAME, UserDataRepository
from app.providers.budget import SQLiteDailyRequestBudget, render_daily_budget_status
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
from app.tags import (
    FAVORITE_TAG_LABELS,
    FavoriteTagsRepository,
    favorite_tag_counts,
)
from app.ui import (
    CATEGORY_LABELS,
    categories_keyboard,
    delete_data_confirmation_keyboard,
    districts_keyboard,
    favorite_filter_keyboard,
    favorite_note_keyboard,
    favorite_tags_keyboard,
    filters_keyboard,
    home_keyboard,
    mydata_keyboard,
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


class FavoriteNoteState(StatesGroup):
    awaiting_text = State()


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

    personal_tags = restored.get("personal_tags")
    if isinstance(personal_tags, (list, tuple)):
        restored["personal_tags"] = tuple(str(item) for item in personal_tags)

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
            favorites_mode=data.get("category") == "favorites",
            active_favorite_tag=(
                data.get("favorite_filter")
                if isinstance(data.get("favorite_filter"), str)
                else None
            ),
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
    provider_budgets: dict[str, SQLiteDailyRequestBudget],
) -> None:
    runtime_notes: dict[str, str] = {}
    for key, budget in provider_budgets.items():
        try:
            runtime_notes[key] = render_daily_budget_status(await budget.status())
        except sqlite3.Error:
            runtime_notes[key] = "локальный лимит: статус временно недоступен"

    await message.answer(
        render_provider_statuses(
            provider_statuses,
            runtime_notes=runtime_notes,
        ),
        disable_web_page_preview=True,
    )


@router.message(Command("mydata"))
async def my_data(
    message: Message,
    user_data_repository: UserDataRepository,
) -> None:
    if message.from_user is None:
        return

    summary = await user_data_repository.summary_for_user(
        user_id=message.from_user.id,
    )
    await message.answer(
        "<b>Мои данные в PermPlaces</b>\n\n"
        f"❤️ Избранное: <b>{summary.favorites}</b>\n"
        f"⭐ Мои оценки: <b>{summary.ratings}</b>\n"
        f"📝 Личные заметки: <b>{summary.notes}</b>\n"
        f"🏷 Мои метки: <b>{summary.tags}</b>\n\n"
        "Геолокация и текущие результаты поиска хранятся только в памяти "
        "текущего процесса и не входят в постоянную SQLite-базу.\n\n"
        "Удаление ниже касается постоянных данных PermPlaces: избранного, "
        "community-оценок, личных заметок и ваших меток.",
        reply_markup=mydata_keyboard(
            has_persistent_data=summary.total_rows > 0,
        ),
    )


@router.callback_query(F.data == "privacy:export")
async def export_my_data(
    callback: CallbackQuery,
    user_data_repository: UserDataRepository,
) -> None:
    await callback.answer("Готовлю экспорт…")
    if callback.message is None:
        return

    export = await user_data_repository.export_for_user(
        user_id=callback.from_user.id,
    )
    await callback.message.answer_document(
        BufferedInputFile(
            export.content,
            filename=USER_DATA_EXPORT_FILENAME,
        ),
        caption=(
            "<b>Экспорт данных PermPlaces</b>\n"
            f"❤️ Избранное: {export.favorites}\n"
            f"⭐ Оценки: {export.ratings}\n"
            f"📝 Заметки: {export.notes}\n"
            f"🏷 Метки: {export.tags}\n\n"
            "Файл не содержит Telegram user ID, API-ключей или истории геолокации."
        ),
    )


@router.callback_query(F.data == "privacy:delete")
async def delete_my_data_requested(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            "<b>Удалить мои данные PermPlaces?</b>\n\n"
            "Будут удалены все ваши сохранённые места, community-оценки, "
            "личные заметки и метки. Это действие нельзя отменить.",
            reply_markup=delete_data_confirmation_keyboard(),
        )


@router.callback_query(F.data == "privacy:delete:cancel")
async def delete_my_data_cancelled(callback: CallbackQuery) -> None:
    await callback.answer("Удаление отменено")
    if callback.message:
        await callback.message.edit_text(
            "Удаление отменено. Ваши постоянные данные не изменены."
        )


@router.callback_query(F.data == "privacy:delete:confirm")
async def delete_my_data_confirmed(
    callback: CallbackQuery,
    state: FSMContext,
    user_data_repository: UserDataRepository,
) -> None:
    deleted = await user_data_repository.delete_for_user(
        user_id=callback.from_user.id,
    )
    await state.clear()
    await callback.answer("Данные удалены")
    if callback.message:
        await callback.message.edit_text(
            "<b>Данные PermPlaces удалены.</b>\n\n"
            f"Удалено избранных мест: <b>{deleted.favorites}</b>\n"
            f"Удалено оценок: <b>{deleted.ratings}</b>\n"
            f"Удалено заметок: <b>{deleted.notes}</b>\n"
            f"Удалено меток: <b>{deleted.tags}</b>\n\n"
            "Также очищено текущее состояние поиска в памяти бота."
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
            favorites_mode=True,
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
    notes_repository: NotesRepository,
    tags_repository: FavoriteTagsRepository,
) -> None:
    if message.from_user is None:
        return

    venues = await favorites_repository.list_for_user(user_id=message.from_user.id)
    venues = await ratings_repository.enrich_many(venues)
    venues = await notes_repository.enrich_many(
        user_id=message.from_user.id,
        venues=venues,
    )
    venues = await tags_repository.enrich_many(
        user_id=message.from_user.id,
        venues=venues,
    )
    if not venues:
        await message.answer(
            "❤️ <b>Избранное пока пусто.</b>\n\n"
            "Откройте найденное место и нажмите «❤️ В избранное»."
        )
        return

    all_results = [asdict(venue) for venue in venues]
    await state.update_data(
        results=all_results,
        favorite_all_results=all_results,
        favorite_filter=None,
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


async def _send_venue_detail(
    message: Message,
    venue: Venue,
    *,
    allow_note: bool = False,
    allow_tags: bool = False,
) -> None:
    card = render_venue_card(venue)
    photo_url = primary_photo_url(venue)
    if photo_url and len(card) <= 1024:
        try:
            await message.answer_photo(
                photo=photo_url,
                caption=card,
                reply_markup=venue_keyboard(
                    venue,
                    allow_note=allow_note,
                    allow_tags=allow_tags,
                ),
            )
            return
        except TelegramBadRequest:
            pass

    await message.answer(
        card,
        reply_markup=venue_keyboard(
            venue,
            allow_note=allow_note,
            allow_tags=allow_tags,
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

    favorite_mode = data.get("category") == "favorites"
    await _send_venue_detail(
        callback.message,
        venue,
        allow_note=favorite_mode,
        allow_tags=favorite_mode,
    )


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
    all_results_raw = data.get("favorite_all_results")
    all_results = (
        [item for item in all_results_raw if isinstance(item, dict)]
        if isinstance(all_results_raw, list)
        else dict_results
    )
    updated_all_results = [
        item
        for item in all_results
        if item.get("id") != venue_id
    ]
    if not updated_results:
        await state.update_data(
            results=[],
            favorite_all_results=updated_all_results,
            result_index=0,
        )
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
    await state.update_data(
        results=updated_results,
        favorite_all_results=updated_all_results,
        result_index=index,
    )

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
                    favorites_mode=True,
                    active_favorite_tag=(
                        data.get("favorite_filter")
                        if isinstance(data.get("favorite_filter"), str)
                        else None
                    ),
                ),
                disable_web_page_preview=True,
            )
        return

    await _edit_current_result(callback, state)


@router.callback_query(F.data.startswith("favorite_note:edit:"))
async def edit_favorite_note(
    callback: CallbackQuery,
    state: FSMContext,
    notes_repository: NotesRepository,
) -> None:
    await callback.answer()
    if not callback.data or callback.message is None:
        return

    data = await state.get_data()
    results = data.get("results")
    if data.get("category") != "favorites" or not isinstance(results, list):
        await callback.message.answer(
            "Заметка доступна только для актуального списка избранного."
        )
        return

    venue_id = callback.data.removeprefix("favorite_note:edit:")
    dict_results = [item for item in results if isinstance(item, dict)]
    venue = _find_result(dict_results, venue_id)
    if venue is None:
        await callback.message.answer(
            "Карточка устарела. Откройте избранное снова."
        )
        return

    current = await notes_repository.get_for_venue(
        user_id=callback.from_user.id,
        venue=venue,
    )
    await state.set_state(FavoriteNoteState.awaiting_text)
    await state.update_data(note_venue_id=venue.id)

    current_text = (
        f"\n\nТекущая заметка: <i>{escape(current.text)}</i>"
        if current is not None
        else ""
    )
    await callback.message.answer(
        "<b>Личная заметка</b>\n\n"
        f"Отправьте новый текст до {MAX_PERSONAL_NOTE_LENGTH} символов. "
        "Заметка хранится только в PermPlaces и не отправляется провайдерам."
        f"{current_text}",
        reply_markup=favorite_note_keyboard(
            venue.id,
            has_note=current is not None,
        ),
    )


@router.callback_query(F.data.startswith("favorite_note:remove:"))
async def remove_favorite_note(
    callback: CallbackQuery,
    state: FSMContext,
    notes_repository: NotesRepository,
) -> None:
    if not callback.data:
        return

    data = await state.get_data()
    results = data.get("results")
    if not isinstance(results, list):
        await callback.answer("Карточка устарела.")
        return

    venue_id = callback.data.removeprefix("favorite_note:remove:")
    dict_results = [item for item in results if isinstance(item, dict)]
    venue = _find_result(dict_results, venue_id)
    if venue is None:
        await callback.answer("Карточка устарела.")
        return

    removed = await notes_repository.remove_note(
        user_id=callback.from_user.id,
        venue=venue,
    )
    updated_venue = replace(venue, personal_note=None)
    updated_results = [
        asdict(updated_venue) if item.get("id") == venue_id else item
        for item in dict_results
    ]
    all_results_raw = data.get("favorite_all_results")
    updated_all_results = (
        [
            asdict(updated_venue) if item.get("id") == venue_id else item
            for item in all_results_raw
            if isinstance(item, dict)
        ]
        if isinstance(all_results_raw, list)
        else updated_results
    )
    await state.update_data(
        results=updated_results,
        favorite_all_results=updated_all_results,
        note_venue_id=None,
    )
    await state.set_state(None)
    await callback.answer("Заметка удалена" if removed else "Заметки уже нет")
    if callback.message:
        await callback.message.edit_text(
            "📝 Заметка удалена." if removed else "📝 Заметка уже отсутствует."
        )


@router.callback_query(F.data == "favorite_note:cancel")
async def cancel_favorite_note(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.set_state(None)
    await state.update_data(note_venue_id=None)
    await callback.answer("Редактирование отменено")
    if callback.message:
        await callback.message.edit_text("Редактирование заметки отменено.")


@router.message(FavoriteNoteState.awaiting_text, F.text)
async def favorite_note_text(
    message: Message,
    state: FSMContext,
    notes_repository: NotesRepository,
) -> None:
    if message.from_user is None:
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("Заметка не может быть пустой.")
        return
    if len(text) > MAX_PERSONAL_NOTE_LENGTH:
        await message.answer(
            f"Заметка слишком длинная. Максимум {MAX_PERSONAL_NOTE_LENGTH} символов."
        )
        return

    data = await state.get_data()
    venue_id = data.get("note_venue_id")
    results = data.get("results")
    if not isinstance(venue_id, str) or not isinstance(results, list):
        await state.set_state(None)
        await message.answer("Карточка устарела. Откройте избранное снова.")
        return

    dict_results = [item for item in results if isinstance(item, dict)]
    venue = _find_result(dict_results, venue_id)
    if venue is None:
        await state.set_state(None)
        await message.answer("Карточка устарела. Откройте избранное снова.")
        return

    try:
        saved = await notes_repository.set_note(
            user_id=message.from_user.id,
            venue=venue,
            text=text,
        )
    except ValueError as exc:
        if str(exc) != "note requires a saved favorite":
            raise
        await state.update_data(note_venue_id=None)
        await state.set_state(None)
        await message.answer(
            "Избранное изменилось. Откройте сохранённое место заново "
            "и повторите редактирование заметки."
        )
        return

    updated_venue = replace(venue, personal_note=saved.text)
    updated_results = [
        asdict(updated_venue) if item.get("id") == venue_id else item
        for item in dict_results
    ]
    all_results_raw = data.get("favorite_all_results")
    updated_all_results = (
        [
            asdict(updated_venue) if item.get("id") == venue_id else item
            for item in all_results_raw
            if isinstance(item, dict)
        ]
        if isinstance(all_results_raw, list)
        else updated_results
    )
    await state.update_data(
        results=updated_results,
        favorite_all_results=updated_all_results,
        note_venue_id=None,
    )
    await state.set_state(None)
    await message.answer(
        "📝 Заметка сохранена. Она будет видна только в вашем избранном."
    )


@router.callback_query(F.data.startswith("ft:menu:"))
async def favorite_tags_menu(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()
    if not callback.data or callback.message is None:
        return

    data = await state.get_data()
    results = data.get("results")
    if data.get("category") != "favorites" or not isinstance(results, list):
        await callback.message.answer(
            "Метки доступны только для актуального списка избранного."
        )
        return

    venue_id = callback.data.removeprefix("ft:menu:")
    dict_results = [item for item in results if isinstance(item, dict)]
    venue = _find_result(dict_results, venue_id)
    if venue is None:
        await callback.message.answer(
            "Карточка устарела. Откройте избранное снова."
        )
        return

    await callback.message.answer(
        "<b>Ваши метки</b>\n\n"
        "Это ваши личные категории для организации избранного. "
        "Они не являются характеристиками заведения и не отправляются провайдерам.",
        reply_markup=favorite_tags_keyboard(
            venue.id,
            current_tags=venue.personal_tags,
        ),
    )


@router.callback_query(F.data == "ft:close")
async def close_favorite_tags(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.delete()


@router.callback_query(F.data.startswith("ft:"))
async def favorite_tag_toggle(
    callback: CallbackQuery,
    state: FSMContext,
    tags_repository: FavoriteTagsRepository,
) -> None:
    if not callback.data:
        return

    parts = callback.data.split(":", 2)
    if len(parts) != 3 or parts[1] not in FAVORITE_TAG_LABELS:
        await callback.answer("Неизвестная метка.")
        return

    tag = parts[1]
    venue_id = parts[2]
    data = await state.get_data()
    results = data.get("results")
    if data.get("category") != "favorites" or not isinstance(results, list):
        await callback.answer("Список избранного устарел.")
        return

    dict_results = [item for item in results if isinstance(item, dict)]
    all_results_raw = data.get("favorite_all_results")
    all_results = (
        [item for item in all_results_raw if isinstance(item, dict)]
        if isinstance(all_results_raw, list)
        else dict_results
    )
    venue = _find_result(all_results, venue_id)
    if venue is None:
        await callback.answer("Карточка устарела. Откройте избранное снова.")
        return

    try:
        added = await tags_repository.toggle_tag(
            user_id=callback.from_user.id,
            venue=venue,
            tag=tag,
        )
    except ValueError as exc:
        if str(exc) != "tag requires a saved favorite":
            raise
        await callback.answer("Избранное изменилось. Откройте его снова.")
        return

    current_tags = set(venue.personal_tags)
    if added:
        current_tags.add(tag)
    else:
        current_tags.discard(tag)
    ordered_tags = tuple(
        key for key in FAVORITE_TAG_LABELS if key in current_tags
    )
    updated_venue = replace(venue, personal_tags=ordered_tags)
    updated_all_results = [
        asdict(updated_venue) if item.get("id") == venue_id else item
        for item in all_results
    ]

    active_filter = (
        data.get("favorite_filter")
        if isinstance(data.get("favorite_filter"), str)
        else None
    )
    filtered_results = (
        [
            item
            for item in updated_all_results
            if active_filter in tuple(item.get("personal_tags", ()))
        ]
        if active_filter in FAVORITE_TAG_LABELS
        else updated_all_results
    )
    if not filtered_results and active_filter in FAVORITE_TAG_LABELS:
        active_filter = None
        filtered_results = updated_all_results

    index = data.get("result_index", 0)
    if not isinstance(index, int):
        index = 0
    index = max(0, min(index, max(0, len(filtered_results) - 1)))
    await state.update_data(
        favorite_all_results=updated_all_results,
        results=filtered_results,
        result_index=index,
        favorite_filter=active_filter,
    )

    await callback.answer(
        f"{'Добавлена' if added else 'Снята'}: {FAVORITE_TAG_LABELS[tag]}"
    )
    if callback.message:
        await callback.message.edit_reply_markup(
            reply_markup=favorite_tags_keyboard(
                venue_id,
                current_tags=ordered_tags,
            )
        )


@router.callback_query(F.data == "ff:menu")
async def favorite_filter_menu(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()
    if not callback.message:
        return

    data = await state.get_data()
    all_results_raw = data.get("favorite_all_results")
    if data.get("category") != "favorites" or not isinstance(all_results_raw, list):
        return

    all_results = [
        _venue_from_dict(item)
        for item in all_results_raw
        if isinstance(item, dict)
    ]
    if not all_results:
        return

    active = (
        data.get("favorite_filter")
        if isinstance(data.get("favorite_filter"), str)
        else None
    )
    await callback.message.edit_reply_markup(
        reply_markup=favorite_filter_keyboard(
            total=len(all_results),
            counts=favorite_tag_counts(all_results),
            active_tag=active,
        )
    )


@router.callback_query(F.data.startswith("ff:"))
async def favorite_filter_selected(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    if not callback.data:
        return

    selected = callback.data.split(":", 1)[1]
    if selected != "all" and selected not in FAVORITE_TAG_LABELS:
        await callback.answer("Неизвестный фильтр.")
        return

    data = await state.get_data()
    all_results_raw = data.get("favorite_all_results")
    if data.get("category") != "favorites" or not isinstance(all_results_raw, list):
        await callback.answer("Список избранного устарел.")
        return

    all_results = [
        item
        for item in all_results_raw
        if isinstance(item, dict)
    ]
    active = None if selected == "all" else selected
    filtered = (
        [
            item
            for item in all_results
            if active in tuple(item.get("personal_tags", ()))
        ]
        if active is not None
        else all_results
    )

    if not filtered:
        await callback.answer("С этой меткой пока нет мест.")
        return

    await state.update_data(
        results=filtered,
        result_index=0,
        favorite_filter=active,
    )
    await callback.answer(
        "Показаны все избранные"
        if active is None
        else f"Фильтр: {FAVORITE_TAG_LABELS[active]}"
    )
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
