import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot import router
from app.config import load_settings
from app.providers.cache import CachedPlacesProvider
from app.providers.failover import FailoverPlacesProvider
from app.providers.overpass import OverpassProvider
from app.search import SearchService
from app.storage import FavoritesRepository


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = load_settings()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    overpass_providers = [
        OverpassProvider(
            endpoint=endpoint,
            timeout_seconds=settings.overpass_timeout_seconds,
        )
        for endpoint in settings.overpass_endpoints
    ]
    failover_provider = FailoverPlacesProvider(overpass_providers)
    cached_provider = CachedPlacesProvider(
        failover_provider,
        ttl_seconds=settings.provider_cache_ttl_seconds,
        max_entries=settings.provider_cache_max_entries,
    )
    search_service = SearchService(cached_provider)
    favorites_repository = FavoritesRepository(settings.database_path)
    await favorites_repository.initialize()

    try:
        await dispatcher.start_polling(
            bot,
            search_service=search_service,
            favorites_repository=favorites_repository,
        )
    finally:
        await asyncio.gather(*(provider.close() for provider in overpass_providers))
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
