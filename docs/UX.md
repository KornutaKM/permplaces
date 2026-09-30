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
5. Open a venue in a separate detail card; use a provider-backed photo when one is safely available.
6. Send its map location, open it in an external map, share it, open its site/source, or save it to favorites.

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
- 🎲 Удиви меня — randomly selects one result from an expanded mixed food/drink candidate set while preserving the current area and active filters

## Filters

Live:

- radius: 500 m / 1 km / 3 km / 5 km for “Рядом со мной”;
- terrace / outdoor seating only when OSM explicitly provides `outdoor_seating`;
- Wi-Fi only when OSM explicitly provides `internet_access=wlan` or compatible legacy `wifi=yes/free`;
- open now only when a semantic OSM `opening_hours` evaluation returns OPEN for the venue timezone.

Intentionally not active yet:

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

- provider-backed photo when available; absence of a photo is a normal state;
- name;
- provider-backed category;
- calculated distance;
- address when present;
- raw OSM opening_hours when present;
- cuisine tags when present;
- provider/source attribution;
- phone when present in the provider;
- district when known;
- terrace and Wi-Fi badges only when positively confirmed by provider tags;
- an “Открыто сейчас” badge only on a result evaluated OPEN during the current search.

OSM does not supply PermPlaces with a platform rating or review count, so those fields are omitted.

Actions:

- Подробнее
- Маршрут — sends Telegram Location and offers 2GIS, Google Maps and OpenStreetMap links
- Открыть в OSM
- Поделиться — standard Telegram share URL; must not require bot inline-mode
- Сайт, only when the provider supplies a valid HTTP(S) URL
- В избранное
- Следующее / Предыдущее
- Закрыть карточку — detail card is a separate message so result navigation remains intact

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
- “открыто сейчас” intent;
- “без Wi-Fi” / “без веранды” as explicit filter disablement.

Unsupported or ambiguous semantics remain explicit rather than being guessed.

## Visual venue cards

Foursquare photo metadata is accepted only through provider responses and normalized into
provider-backed photo references. PermPlaces does not scrape websites for imagery.

The first safe photo may be sent as the Telegram detail-card media. If the photo URL is absent,
unsafe, the rendered caption would exceed Telegram's photo-caption limit, or Telegram rejects the
remote media fetch, the bot falls back to a normal text detail card without losing any sourced
facts or actions.

## Next UX milestone

Add new scenarios only where provider-backed evidence can support them.
