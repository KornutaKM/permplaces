# PermPlaces

Telegram-ассистент для поиска кафе, ресторанов, баров и других мест в Перми.

## Статус

Сейчас реализуется UI MVP: Telegram-навигация по утверждённому концепту с безопасными демо-данными. Реальные заведения будут подключены отдельным provider-слоем.

## Что уже есть

- стартовый экран;
- запрос геолокации;
- выбор района Перми;
- категории заведений;
- фильтры;
- текстовый поиск;
- готовые сценарии;
- карточка заведения;
- избранное в демо-режиме;
- Docker runtime;
- Ruff + pytest CI.

Подробный UX-контракт: [docs/UX.md](docs/UX.md).

## Локальный запуск

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
```

Запуск:

```bash
python -m app.main
```

Проверки:

```bash
ruff check .
pytest
```

## Docker

```bash
docker build -t permplaces .
docker run --rm --env BOT_TOKEN=your_token permplaces
```

## Следующий milestone

Подключить реальный каталог заведений Перми через provider abstraction, сохранив текущий UX:

```text
Telegram UI
   ↓
Search service
   ↓
Places provider interface
   ├── OpenStreetMap / Overpass
   ├── 2GIS
   └── другие источники
```

Provider-specific данные должны сохранять provenance. Отсутствующие данные нельзя угадывать.
