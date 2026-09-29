import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot import router
from app.config import load_settings
from app.providers.cache import CachedPlacesProvider
from app.providers.composite import CompositePlacesProvider
from app.providers.failover import FailoverPlacesProvider
from app.providers.overpass import OverpassProvider
from app.providers.twogis import TwoGISProvider
from app.search import SearchService
from app.storage import FavoritesRepository

logger = logging.getLogger(__name__)


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
    osm_cache = CachedPlacesProvider(
        failover_provider,
        ttl_seconds=settings.provider_cache_ttl_seconds,
        max_entries=settings.provider_cache_max_entries,
    )

    aggregate_providers = [osm_cache]
    caches = [("osm", osm_cache)]
    closable_providers: list[OverpassProvider | TwoGISProvider] = [
        *overpass_providers
    ]

    twogis_provider: TwoGISProvider | None = None
    if settings.twogis_api_key.strip():
        twogis_provider = TwoGISProvider(
            api_key=settings.twogis_api_key,
            endpoint=settings.twogis_url,
            timeout_seconds=settings.twogis_timeout_seconds,
        )
        twogis_cache = CachedPlacesProvider(
            twogis_provider,
            ttl_seconds=settings.provider_cache_ttl_seconds,
            max_entries=settings.provider_cache_max_entries,
        )
        aggregate_providers.append(twogis_cache)
        caches.append(("2gis", twogis_cache))
        closable_providers.append(twogis_provider)

    composite_provider = CompositePlacesProvider(aggregate_providers)
    search_service = SearchService(composite_provider)
    favorites_repository = FavoritesRepository(settings.database_path)
    await favorites_repository.initialize()

    logger.info(
        "permplaces_start providers=%d overpass_endpoints=%d twogis_enabled=%s "
        "cache_ttl_seconds=%s cache_max_entries=%d",
        len(aggregate_providers),
        len(settings.overpass_endpoints),
        twogis_provider is not None,
        settings.provider_cache_ttl_seconds,
        settings.provider_cache_max_entries,
    )

    try:
        await dispatcher.start_polling(
            bot,
            search_service=search_service,
            favorites_repository=favorites_repository,
        )
    finally:
        for provider_name, cache in caches:
            cache_stats = cache.stats()
            logger.info(
                "permplaces_stop provider=%s cache_hits=%d cache_misses=%d "
                "cache_coalesced=%d cache_evictions=%d cache_entries=%d",
                provider_name,
                cache_stats.hits,
                cache_stats.misses,
                cache_stats.coalesced,
                cache_stats.evictions,
                cache_stats.entries,
            )

        await asyncio.gather(
            *(provider.close() for provider in closable_providers)
        )
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
