# PermPlaces UX direction

This document freezes the first approved Telegram UX direction for the Perm pilot.

## Product character

PermPlaces should feel like a compact city concierge rather than a database browser.

- Dark Telegram-native presentation.
- Short messages and large action buttons.
- One decision per screen.
- Emoji act as category cues, not decoration.
- Real provider data must never be invented.
- Missing rating, opening-hours, menu or price data is shown as unavailable rather than guessed.

## Primary flow

1. Start.
2. Choose location: current geolocation, Perm district, or text search.
3. Choose category or a ready-made scenario.
4. Optionally apply filters.
5. Browse result cards.
6. Open a venue.
7. Route, menu, favorite, share.

## Home

Primary actions:

- 📍 Рядом со мной
- 🏙 Выбрать район
- 🔎 Поиск текстом
- ✨ Сценарии
- ❤️ Избранное

## Categories

- 🍽 Рестораны
- ☕ Кофейни
- 🍺 Бары
- 🥐 Завтраки
- 🍕 Пицца
- 🍣 Суши
- 🍔 Фастфуд
- 🧁 Десерты
- 🎲 Удиви меня

## Perm districts

- Дзержинский
- Индустриальный
- Кировский
- Ленинский
- Мотовилихинский
- Орджоникидзевский
- Свердловский

## Filters

First iteration:

- radius: 500 m / 1 km / 3 km / 5 km;
- price level;
- open now;
- terrace.

Later:

- rating;
- children;
- Wi-Fi;
- parking;
- cuisine;
- delivery;
- accessibility.

## Venue card

The card should contain only sourced facts:

- name;
- provider rating + review count;
- categories / cuisine;
- price level;
- distance;
- opening status;
- address;
- optional photo.

Actions:

- Подробнее
- Маршрут
- Меню
- В избранное
- Поделиться
- Следующее / Предыдущее

## Ready-made scenarios

- ☕ Выпить кофе
- 🍽 Поесть
- 🥐 Позавтракать
- 🍺 Выпить
- ❤️ На свидание
- 👨‍👩‍👧 С детьми
- 💻 Поработать (Wi-Fi)
- 🌙 Поздно вечером
- 🎲 Куда-нибудь

Scenarios are search presets. They must remain explainable and resolve into explicit filters.

## Data-state rules

The UI must distinguish:

- verified provider data;
- owner-managed data;
- unavailable fields;
- demo/development fixtures.

Demo fixtures must be visibly marked and must never look like verified Perm establishments.

## Next UX milestone

Replace demo fixtures with a provider abstraction returning real Perm venues while preserving the same screens and callbacks.
