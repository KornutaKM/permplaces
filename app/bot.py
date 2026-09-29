from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from app.data import DEMO_VENUES, find_venues
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
🗺 Маршруты, контакты и меню
❤️ Избранные места

Как хотите искать заведение?"""


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(WELCOME, reply_markup=home_keyboard())


@router.message(F.location)
async def location_received(message: Message) -> None:
    await message.answer(
        "<b>Геолокация получена.</b> Теперь выберите, что хотите найти:",
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
        "Напишите, что хочется. Например: <i>кофе</i>, <i>завтрак</i> или <i>бар</i>.",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(SearchState.awaiting_query, F.text)
async def text_search(message: Message, state: FSMContext) -> None:
    await state.clear()
    venues = find_venues(query=message.text or "")
    if not venues:
        await message.answer(
            "Пока в демо-каталоге ничего не нашлось. Выберите категорию:",
            reply_markup=categories_keyboard(),
        )
        return
    venue = venues[0]
    await message.answer(
        render_venue_card(venue, position=1, total=len(venues)),
        reply_markup=results_keyboard(venue.id),
    )


@router.message(F.text == "✨ Сценарии")
async def scenarios(message: Message) -> None:
    await message.answer("Выберите готовый сценарий:", reply_markup=scenarios_keyboard())


@router.message(F.text == "❤️ Избранное")
async def favorites(message: Message) -> None:
    await message.answer(
        "❤️ <b>Избранное</b>\n\nЗдесь появятся сохранённые места. "
        "Персистентное хранение подключим на следующем этапе."
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
            "Радиус · средний чек · открыто сейчас · веранда",
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
        f"📍 <b>{district}</b>\n\nТеперь выберите категорию:",
        reply_markup=categories_keyboard(),
    )


@router.callback_query(F.data.startswith("category:"))
async def category_selected(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.message or not callback.data:
        return
    category = callback.data.split(":", 1)[1]
    venues = find_venues(category=category)
    label = CATEGORY_LABELS.get(category, "Заведения")
    if not venues:
        await callback.message.edit_text(
            f"<b>{label}</b>\n\n"
            "Для этой категории демо-карточки ещё нет. "
            "После подключения каталога здесь появятся реальные места.",
            reply_markup=categories_keyboard(),
        )
        return
    venue = venues[0]
    await callback.message.edit_text(
        render_venue_card(venue, position=1, total=len(venues)),
        reply_markup=results_keyboard(venue.id),
    )


@router.callback_query(F.data.startswith("venue:"))
async def venue_detail(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.message or not callback.data:
        return
    venue_id = callback.data.split(":", 1)[1]
    venue = next((item for item in DEMO_VENUES if item.id == venue_id), None)
    if venue is None:
        await callback.message.edit_text("Карточка не найдена.")
        return
    await callback.message.edit_text(
        render_venue_card(venue),
        reply_markup=venue_keyboard(venue.id),
    )


@router.callback_query(F.data.startswith("favorite:"))
async def favorite(callback: CallbackQuery) -> None:
    await callback.answer("Добавлено в избранное — пока только в демо-режиме ❤️")


@router.callback_query(F.data.startswith("route:"))
async def route(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "📍 Маршрут будет открываться в выбранном картографическом сервисе "
            "после подключения реальных координат."
        )


@router.callback_query(F.data.startswith("menu:"))
async def menu(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "📖 Меню появится здесь, если его предоставляет источник данных или владелец места."
        )


@router.callback_query(F.data.startswith("scenario:"))
async def scenario(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            "✨ <b>Сценарий выбран.</b>\n\n"
            "На следующем этапе он будет преобразован в реальные параметры поиска. "
            "Сейчас можно перейти к категориям.",
            reply_markup=categories_keyboard(),
        )


@router.callback_query(F.data.startswith("filter:"))
async def filter_selected(callback: CallbackQuery) -> None:
    await callback.answer("Фильтр выбран — сохранение параметров добавим следующим шагом.")


@router.callback_query(F.data.startswith("results:"))
async def result_navigation(callback: CallbackQuery) -> None:
    await callback.answer("Навигация по выдаче подключается вместе с реальным каталогом.")
