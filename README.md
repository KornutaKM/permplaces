# PermPlaces

Telegram-ассистент для поиска кафе, ресторанов, баров и других мест в Перми.

## Статус

Версия 0.37 добавляет локальный поиск по избранному: название, адрес, категория, район, cuisine, личная заметка и личные метки ищутся детерминированно без внешних provider requests и без постоянной истории запросов.

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
- provider-backed кнопка 📖 «Меню» только для явного http/https URL, без эвристик;
- provider-backed Foursquare photos с безопасной HTTP(S) нормализацией и provenance;
- отдельная визуальная detail-card с фото и fallback на текстовую карточку;
- переход между результатами;
- отправка точки заведения через Telegram Location;
- быстрые ссылки на 2ГИС, Google Maps и OpenStreetMap из карточки маршрута;
- «↗️ Поделиться» через стандартный Telegram share URL без зависимости от inline-mode;
- ссылка на исходный OSM-объект;
- обязательная атрибуция © OpenStreetMap contributors / ODbL;
- текстовый поиск вида `кофе с Wi-Fi рядом 1 км`, `ресторан с верандой в Ленинском районе` или `суши открыто сейчас по всей Перми`;
- явное переключение scope по словам «рядом», названию района или «по всей Перми»;
- безопасный диапазон свободного радиуса 100 м–10 км с явной ошибкой вне диапазона;
- готовые сценарии для кофе, еды, завтрака, напитков и работы с Wi-Fi;
- единый Scenario Engine v1 для coffee/eat/breakfast/drink/work/family/late/random с явными filter/ranking/selection contracts;
- блок «Почему подходит» только из подтверждённых данных: расстояние, Wi-Fi, family features, open now/late, provider rating и price tier;
- 👨‍👩‍👧 «С детьми» по `kids_area`, `highchair` или `changing_table`;
- 🌙 «Поздно вечером» — заведения, открытые сегодня в 23:00 по OSM `opening_hours`;
- 🎲 реальный случайный выбор среди смешанных food & drink категорий;
- bounded TTL-кэш provider-запросов; одинаковые одновременные запросы объединяются в один upstream-call;
- configurable graceful failover: fallback endpoint используется только после `ProviderError` primary;
- runtime-логи provider latency, cache hit/miss/coalescing/eviction и failover без координат пользователя;
- ❤️ постоянное избранное в SQLite, изолированное по Telegram user ID;
- favorites используют provider aliases: одна физическая карточка не дублируется только из-за смены primary source после OSM/Geoapify merge;
- provider aliases избранного индексируются в SQLite; legacy favorites автоматически backfill-ятся при startup migration;
- 📝 личные заметки до 500 символов доступны только для сохранённых favorites, не отправляются провайдерам и следуют exact provider aliases;
- удаление favorite транзакционно удаляет связанные personal notes и personal tags;
- 🏷 пять фиксированных личных меток для организации favorites; это user intent, а не provider-backed свойства места;
- favorites можно локально фильтровать по личной метке без внешних provider requests;
- 🔎 локальный поиск по уже загруженному избранному использует название, адрес, категорию, район, cuisine, личные заметки и labels личных меток; запрос живёт только в in-memory FSM;
- ⭐ собственные оценки пользователей PermPlaces 1–5 без платного rating API;
- community rating агрегируется по provider aliases без двойного учёта одного пользователя;
- пользователь видит свою текущую оценку, может изменить или удалить её;
- community aggregates для списка мест читаются batch-запросом вместо N+1 SQLite queries;
- Ruff + pytest;
- Docker Compose build/config/smoke CI;
- multi-provider aggregation с capability-aware routing: неподходящий provider не вызывается;
- conservative dedup v2 с branch-safe phone/site/name/address matching;
- corroborating field provenance: одинаковый сохранённый факт может иметь несколько источников;
- безопасная команда `/providers` показывает активные источники, возможности и текущий local Geoapify budget без секретов;
- `/mydata` показывает только агрегированные counts текущего пользователя, даёт скачать versioned JSON export и подтверждаемое удаление favorites+community ratings+personal notes+personal tags;
- экспорт генерируется в памяти, не содержит Telegram user ID/секретов и документирован в `docs/DATA_EXPORT.md`;
- удаление пользовательских данных выполняется одной SQLite-транзакцией и очищает текущий in-memory search state;
- source-level и field-level provenance для объединённых карточек;
- рекомендуемый бесплатный Geoapify Places provider для nearby-поиска при заданном `GEOAPIFY_API_KEY`;
- Geoapify-запрос ограничен 20 результатами, чтобы один provider-call укладывался в один Places credit по текущей публичной модели Geoapify;
- persistent app-side Geoapify budget guard по UTC-дню: по умолчанию 2500 upstream calls, чтобы оставлять запас относительно free quota;
- Wi-Fi через Geoapify включается только по provider condition `internet_access`; неподдерживаемые filter-сигналы fail-closed;
- обязательная `Powered by Geoapify` + OpenStreetMap attribution для карточек с Geoapify data;
- опциональный 2GIS Places provider для nearby-поиска при заданном `TWOGIS_API_KEY`;
- опциональный Foursquare Places API (New) provider при заданном `FOURSQUARE_API_KEY`;
- provider-backed Foursquare rating, `stats.total_ratings` и price tier 1–4;
- явная rating scale, чтобы оценки разных провайдеров нельзя было спутать;
- provider-aware source attribution в карточке, включая `Powered by Foursquare` для Foursquare Places Data;
- `/health/live` и `/health/ready` внутри контейнера;
- Docker HEALTHCHECK, который показывает `healthy` только после runtime + SQLite initialization;
- hardened container runtime: UID 10001, read-only root FS, `cap_drop: ALL`, `no-new-privileges`, resource limits.
- versioned SQLite schema v4 через `PRAGMA user_version` и централизованный startup migration;
- SQLite admin CLI: `python -m app.db_admin backup|verify|inspect|audit|repair-aliases|restore` с fail-closed guards;
- `db_admin audit` проверяет derived favorite alias index без изменения данных; repair требует остановленного бота и создаёт pre-repair backup;
- production runbook для secrets, exact-SHA deploy, backup/restore drill и application rollback: `docs/PRODUCTION.md`.

## Принцип данных

PermPlaces не придумывает отсутствующие факты.

Если OpenStreetMap не содержит рейтинг, средний чек, адрес, часы работы или меню, бот не подставляет их самостоятельно. Собственная оценка пользователей PermPlaces показывается отдельно и никогда не маскируется под provider rating.

Каждая OSM-карточка сохраняет:

- provider: `osm`;
- тип и ID OSM-объекта;
- исходную ссылку;
- координаты;
- поля, реально присутствующие в тегах OSM.

## Ограничения текущего этапа

При поиске по району расстояние до пользователя не показывается и выдача сортируется по названию, потому что районный поиск не требует геолокацию пользователя.

Если `opening_hours` отсутствует, невалиден или вычисляется как `unknown`, заведение не считается открытым для фильтра «Открыто сейчас». Рейтинг, отзывы, средний чек и полноценное меню OpenStreetMap обычно не предоставляет. Nearby-поиск может дополняться бесплатным Geoapify provider для базовых POI/address данных и подтверждённого Wi-Fi. Рейтинг/price/menu остаются доступны только из явно подключённых источников, которые действительно возвращают эти поля.

## Бесплатный provider stack

Рекомендуемая конфигурация разработки и небольшого запуска: **OSM/Overpass + Geoapify Free**. Geoapify не заменяет платные каталоги по рейтингам/отзывам/фото: отсутствующие поля остаются неизвестными. Подробный контракт: `docs/GEOAPIFY.md`.

## Production operations

Production deploy, backup, restore and rollback procedures are documented in `docs/PRODUCTION.md`. Schema/migration contract: `docs/DATABASE.md`. Live SQLite backups must use `python -m app.db_admin backup`; copying only the WAL-mode database file while the bot is running is not a supported backup method.

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

SQLite хранится в Docker named volume `permplaces-data` и переживает пересоздание контейнера. `docker compose down -v` удалит этот volume вместе с локальным избранным и оценками пользователей.

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

# Recommended free secondary provider; empty means OSM-only.
GEOAPIFY_API_KEY=
GEOAPIFY_URL=https://api.geoapify.com/v2/places
GEOAPIFY_TIMEOUT_SECONDS=10
GEOAPIFY_DAILY_REQUEST_BUDGET=2500

# Optional: no 2GIS requests are made while this is empty.
TWOGIS_API_KEY=
TWOGIS_URL=https://catalog.api.2gis.com/3.0/items
TWOGIS_TIMEOUT_SECONDS=10

# Optional Foursquare enrichment.
FOURSQUARE_API_KEY=
FOURSQUARE_URL=https://places-api.foursquare.com/places/search
FOURSQUARE_TIMEOUT_SECONDS=10

HEALTH_HOST=0.0.0.0
HEALTH_PORT=8080
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
OverpassProvider + optional GeoapifyProvider + optional paid catalog providers
   ↓
OpenStreetMap + Geoapify Places + optional 2GIS/Foursquare
```

Provider abstraction теперь включает deterministic aggregation, capability routing и provenance. Community ratings, favorites, personal notes и personal tags используют общий provider identity contract. Контракты: `docs/PROVIDERS.md`, `docs/COMMUNITY_RATINGS.md`, `docs/FAVORITES.md`, `docs/FAVORITE_NOTES.md`, `docs/FAVORITE_TAGS.md`, `docs/FAVORITE_SEARCH.md`; privacy/data controls: `docs/PRIVACY.md`, export format: `docs/DATA_EXPORT.md`.

## Следующие этапы

1. Получить бесплатный Geoapify API key и выполнить live-проверку покрытия кафе/ресторанов по Перми через `/providers` и реальный nearby-поиск; budget guard не должен превышать настроенный UTC-day лимит.
2. Добавить Place Details enrichment только после измерения credit-бюджета и только для полей с явным provenance.
3. Добавить average-check enrichment только после region-specific attribute discovery и provenance.
4. Расширять Scenario Engine только новыми provider-backed сигналами; сценарий «На свидание» остаётся выключенным без подтверждаемой модели атмосферы.
5. Выполнить первый production restore drill по `docs/PRODUCTION.md` и зафиксировать конкретный hosting/secret-manager choice.


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

Scenario Engine v1 хранит определения сценариев отдельно от Telegram handlers. Каждый план явно задаёт категорию, обязательные provider-backed filters, candidate limit, ranking и selection strategy. Для обычных сценариев сохраняется deterministic порядок SearchService; «Куда-нибудь» остаётся отдельной явно случайной стратегией.

Блок «Почему подходит» fail-closed: неизвестные факты не превращаются в причины. Он может использовать только уже подтверждённые данные карточки или локально вычисленное расстояние. Rating показывается в объяснении только вместе с явной шкалой.

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


## 2GIS provider (optional)

PermPlaces does **not** call 2GIS by default. The provider is enabled only when
`TWOGIS_API_KEY` is non-empty.

Current v0.16 scope:

- nearby search by category and coordinates;
- exact radius passed to Places API;
- active organization branches only;
- provider-backed `work_time=now` and `work_time=today,23:00`;
- address and WGS84 coordinates;
- deterministic merge with OSM through the v0.15 provenance layer.

Deliberately unsupported in the 2GIS adapter:

- district mode: OSM polygon relations remain authoritative;
- Wi-Fi, terrace and family filters: 2GIS attribute codes vary by region/request, so the
  adapter returns no candidates instead of silently ignoring those filters;
- combined «open now + open at 23:00» in one request;
- `food_drink` surprise query;
- rating values and review text. Current Places API 3.0 can filter by the *presence* of
  ratings/reviews, but standard retrieval of their values/content is not supported.

Official documentation:

- https://docs.2gis.com/en/api/search/places/overview
- https://docs.2gis.com/en/api/search/places/reference/3.0/items
- https://docs.2gis.com/en/api/search/places/examples/filtering


## Health and readiness

PermPlaces starts an internal HTTP health server inside the container.

- `GET /health/live` returns 200 while the health server/event loop is alive.
- `GET /health/ready` returns 503 during initialization.
- After SQLite initialization succeeds, readiness becomes 200.
- Before graceful shutdown, readiness switches back to 503.

The Docker image uses `/health/ready` for its built-in `HEALTHCHECK`.

Compose does not publish this port to the host. It is an internal runtime signal rather than a
public HTTP API. `docker compose ps` shows the resulting container health state.


## Container security profile

The default Compose runtime uses defense-in-depth controls:

- dedicated non-root UID/GID `10001:10001`;
- read-only container root filesystem;
- `/tmp` as a small tmpfs;
- SQLite stored in the writable `permplaces-data` named volume;
- all Linux capabilities dropped;
- `no-new-privileges:true`;
- `pids_limit: 128`;
- `mem_limit: 256m`;
- `cpus: 1.0`.

CI verifies the image user is non-root, the data volume remains writable, and writes to the
container root filesystem fail as expected.


## Foursquare enrichment

Foursquare отключён по умолчанию. Если `FOURSQUARE_API_KEY` пуст, ни одного запроса к
Foursquare не выполняется.

Включённый adapter работает только для nearby-поиска и может добавить к совпавшему месту:

- Foursquare rating с явной шкалой;
- число оценок `stats.total_ratings`;
- price tier 1–4;
- provider-backed photos;
- provider-backed Wi-Fi, outdoor seating и opening-state признаки.

Рейтинг хранится вместе со шкалой и provenance; PermPlaces не смешивает score одного provider
с rating-count другого. Районный поиск остаётся OSM-authoritative. Полный контракт и
fail-closed ограничения описаны в `docs/FOURSQUARE.md`.
