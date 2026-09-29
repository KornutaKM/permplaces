# PermPlaces

Telegram-ассистент для поиска кафе, ресторанов, баров и других мест в Перми.

## Статус

Версия 0.15 закладывает multi-provider foundation: deterministic dedup, source identities и field-level provenance без изменения текущего OSM UX.

Рабочие вертикальные сценарии:

```text
/start
  ├─ 📍 Рядом со мной → категория → ближайшие места по расстоянию
  └─ 🏙 Выбрать район → категория → места внутри OSM-границы района
                                      ↓
                         карточка → следующая/предыдущая → маршрут
```

## Уже работает

- Telegram UI на aiogram 3;
- получение геолокации;
- категории заведений;
- live-поиск OSM вокруг координат пользователя;
- live-поиск внутри семи административных районов Перми;
- режим «📍 Вся Пермь» по границе Пермского городского округа;
- радиус 500 м / 1 км / 3 км / 5 км;
- 🌿 фильтр «С верандой» по `outdoor_seating`;
- 📶 фильтр «Wi-Fi» по `internet_access=wlan` и совместимому `wifi=yes/free`;
- 🟢 фильтр «Открыто сейчас» по семантике OSM `opening_hours`, а не строковым эвристикам;
- сортировка по фактическому расстоянию;
- карточки с адресом, районом, opening_hours, cuisine и телефоном, когда эти поля есть в OSM;
- безопасная кнопка 🌐 «Сайт» для provider URL с http/https;
- переход между результатами;
- отправка точки заведения через Telegram Location;
- ссылка на исходный OSM-объект;
- обязательная атрибуция © OpenStreetMap contributors / ODbL;
- текстовый поиск вида `кофе с Wi-Fi рядом 1 км`, `ресторан с верандой в Ленинском районе` или `суши открыто сейчас по всей Перми`;
- явное переключение scope по словам «рядом», названию района или «по всей Перми»;
- безопасный диапазон свободного радиуса 100 м–10 км с явной ошибкой вне диапазона;
- готовые сценарии для кофе, еды, завтрака, напитков и работы с Wi-Fi;
- 👨‍👩‍👧 «С детьми» по `kids_area`, `highchair` или `changing_table`;
- 🌙 «Поздно вечером» — заведения, открытые сегодня в 23:00 по OSM `opening_hours`;
- 🎲 реальный случайный выбор среди смешанных food & drink категорий;
- bounded TTL-кэш provider-запросов; одинаковые одновременные запросы объединяются в один upstream-call;
- configurable graceful failover: fallback endpoint используется только после `ProviderError` primary;
- runtime-логи provider latency, cache hit/miss/coalescing/eviction и failover без координат пользователя;
- ❤️ постоянное избранное в SQLite, изолированное по Telegram user ID;
- Ruff + pytest;
- Docker Compose build/config/smoke CI;
- multi-provider aggregation foundation с conservative dedup;
- source-level и field-level provenance для объединённых карточек.

## Принцип данных

PermPlaces не придумывает отсутствующие факты.

Если OpenStreetMap не содержит рейтинг, средний чек, адрес, часы работы или меню, бот не подставляет их самостоятельно.

Каждая OSM-карточка сохраняет:

- provider: `osm`;
- тип и ID OSM-объекта;
- исходную ссылку;
- координаты;
- поля, реально присутствующие в тегах OSM.

## Ограничения текущего этапа

При поиске по району расстояние до пользователя не показывается и выдача сортируется по названию, потому что районный поиск не требует геолокацию пользователя.

Если `opening_hours` отсутствует, невалиден или вычисляется как `unknown`, заведение не считается открытым для фильтра «Открыто сейчас». Рейтинг, отзывы, средний чек и полноценное меню OpenStreetMap обычно не предоставляет — для них понадобится второй provider.

## Быстрый запуск через Docker Compose

Для локальной разработки Docker Compose — основной рекомендуемый путь.

Сначала создайте локальный env-файл:

```powershell
Copy-Item .env.example .env
notepad .env
```

Укажите реальный `BOT_TOKEN`. Сам токен не коммитьте и не публикуйте.

Запуск:

```powershell
docker compose up -d --build
```

Проверка:

```powershell
docker compose ps
docker compose logs -f bot
```

SQLite хранится в `./data/permplaces.db` на хосте и переживает пересоздание контейнера.

Остановка:

```powershell
docker compose down
```

Перезапуск после изменений:

```powershell
docker compose up -d --build
```

Если Telegram отвечает `Conflict: terminated by other getUpdates request`, одновременно запущен другой экземпляр бота с тем же токеном. Проверьте `docker ps` и локальные Python-процессы и оставьте только один polling instance.

## Локальный запуск без Docker

Требуется Python 3.12+.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -e ".[dev]"
```

Создайте `.env`:

```env
BOT_TOKEN=your_telegram_bot_token
OVERPASS_URL=https://overpass-api.de/api/interpreter
# Optional; comma-separated and explicitly operator-controlled.
OVERPASS_FALLBACK_URLS=
OVERPASS_TIMEOUT_SECONDS=20
DATABASE_PATH=data/permplaces.db
PROVIDER_CACHE_TTL_SECONDS=120
PROVIDER_CACHE_MAX_ENTRIES=256
```

Запуск:

```bash
python -m app.main
```

Проверки:

```bash
ruff check .
pytest
docker build -t permplaces .
```

## Архитектура

```text
Telegram
   ↓
aiogram handlers
   ↓
SearchService
   ↓
CompositePlacesProvider
   ↓
Cached / failover provider adapters
   ↓
OverpassProvider (+ future providers)
   ↓
OpenStreetMap / future catalogs
```

Provider abstraction теперь включает deterministic aggregation и provenance, поэтому второй источник можно подключать без смешивания фактов или переписывания Telegram UX.

## Следующие этапы

1. Подключить второй provider для рейтингов/отзывов/чека поверх готового provenance/dedup слоя.
2. Добавить provider-specific attribution в UI для рейтинга/отзывов.
3. Сценарий «На свидание» после появления достаточно надёжных признаков.
4. Production deployment profile после стабилизации локального runtime.


## Overpass failover

PermPlaces does not silently send a user's location query to additional Overpass operators.

The primary endpoint remains `OVERPASS_URL`. Additional endpoints are opt-in through
`OVERPASS_FALLBACK_URLS` as a comma-separated ordered list. A fallback is contacted only
when the previous provider returns a provider-level failure; a valid empty result is not
treated as an error.

The OpenStreetMap Wiki maintains the current list and usage policies for public Overpass
instances:

https://wiki.openstreetmap.org/wiki/Overpass_API


## Runtime diagnostics

Во время локального запуска:

```powershell
docker compose logs -f bot
```

можно увидеть безопасные диагностические события:

- `overpass_request status=success|failed ... elapsed_ms=...`;
- `provider_cache event=hit|miss|coalesced|eviction ...`;
- `places_failover event=provider_failed|recovered ...`;
- startup/shutdown summary.

Эти сообщения намеренно не содержат Telegram token, координаты пользователя, текст Overpass query
или полный URL endpoint с path/query/credentials.


## Семантика сценариев

### 👨‍👩‍👧 С детьми

Место попадает в сценарий только если OpenStreetMap явно подтверждает хотя бы один признак:

- `kids_area=yes|designated|limited`;
- `highchair=yes` или положительное количество стульчиков;
- `changing_table=yes|limited`.

Отсутствие этих тегов не трактуется как «не подходит детям» — место просто не включается в
строго подтверждённую выдачу этого сценария.

### 🌙 Поздно вечером

PermPlaces определяет «поздно вечером» как **23:00 текущего дня по часовому поясу Перми
(Asia/Yekaterinburg)**. Заведение включается только если валидный OSM `opening_hours`
показывает состояние open в этот момент. Missing/invalid/unknown график fail-closed и не
попадает в результат.
