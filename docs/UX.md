# PermPlaces UX direction

This document freezes the approved Telegram UX direction for the Perm pilot.

## Product character

PermPlaces should feel like a compact city concierge rather than a database browser.

- Dark Telegram-native presentation.
- Short messages and large action buttons.
- One decision per screen.
- Emoji act as category cues, not decoration.
- Real provider data must never be invented.
- Missing rating, opening-hours, menu or price data is shown as unavailable or omitted.
- Provider attribution and provenance must remain visible.

## Primary flow

1. Start.
2. Choose geolocation, a Perm district, or free-text search.
3. Choose/parse category and supported provider-backed filters.
4. Browse result cards.
5. Open a venue.
6. Send its map location, open its site/OSM source, or save it to favorites.

## Home

Primary actions:

- 📍 Рядом со мной
- 🏙 Выбрать район
- 🔎 Поиск текстом
- ✨ Сценарии
- ❤️ Избранное

District search uses exact governed OSM administrative relations. Free-text search may select a district directly by name.

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

## Filters

Live:

- radius: 500 m / 1 km / 3 km / 5 km for “Рядом со мной”;
- terrace / outdoor seating only when OSM explicitly provides `outdoor_seating`;
- Wi-Fi only when OSM explicitly provides `internet_access=wlan` or compatible legacy `wifi=yes/free`.

Intentionally not active yet:

- open now — requires semantic `opening_hours` parsing;
- price level — no reliable OSM-wide source;
- rating/reviews — not provided by OSM as a platform rating.

Later:

- children;
- parking;
- cuisine;
- delivery;
- accessibility.

## Venue card

The card contains only sourced facts:

- name;
- provider-backed category;
- calculated distance;
- address when present;
- raw OSM opening_hours when present;
- cuisine tags when present;
- provider/source attribution;
- phone when present in the provider;
- district when known;
- terrace and Wi-Fi badges only when positively confirmed by provider tags.

OSM does not supply PermPlaces with a platform rating or review count, so those fields are omitted.

Actions:

- Подробнее
- Маршрут
- Открыть в OSM
- Сайт, only when the provider supplies a valid HTTP(S) URL
- В избранное
- Следующее / Предыдущее

## Data-state rules

The UI must distinguish:

- provider data;
- locally calculated data such as distance;
- unavailable fields;
- future owner-managed data.

The bot must never transform an unavailable field into a guessed value.

## Provider rules

Current provider: OpenStreetMap through Overpass API.

Each venue keeps provider identity and the exact OSM object ID. OSM-derived surfaces must expose attribution to OpenStreetMap contributors and the ODbL license.

## Free-text search

The parser is deterministic and result-blind. It currently understands:

- supported venue categories and common Russian synonyms;
- all seven Perm districts and “Вся Пермь”;
- “рядом” / “поблизости” / “недалеко” as explicit geolocation intent;
- radius from 100 m to 10 km;
- Wi-Fi and terrace/outdoor-seating intent;
- “без Wi-Fi” / “без веранды” as explicit filter disablement.

Unsupported or ambiguous semantics remain explicit rather than being guessed.

## Next UX milestone

Improve result exploration and add new scenarios only where provider-backed evidence can support them.
