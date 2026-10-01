import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot import router
from app.config import load_settings
from app.database import initialize_database
from app.health import HealthServer
from app.providers.budget import DailyBudgetPlacesProvider, SQLiteDailyRequestBudget
from app.providers.cache import CachedPlacesProvider
from app.providers.capabilities import (
    FOURSQUARE_CAPABILITIES,
    GEOAPIFY_CAPABILITIES,
    OVERPASS_CAPABILITIES,
    TWOGIS_CAPABILITIES,
    ProviderStatus,
)
from app.providers.composite import CompositePlacesProvider
from app.providers.failover import FailoverPlacesProvider
from app.providers.foursquare import FoursquareProvider
from app.providers.geoapify import GeoapifyProvider
from app.providers.overpass import OverpassProvider
from app.providers.twogis import TwoGISProvider
from app.ratings import RatingsRepository
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
    closable_providers: list[
        OverpassProvider | GeoapifyProvider | TwoGISProvider | FoursquareProvider
    ] = [*overpass_providers]

    geoapify_provider: GeoapifyProvider | None = None
    geoapify_budget: SQLiteDailyRequestBudget | None = None
    if settings.geoapify_api_key.strip():
        geoapify_provider = GeoapifyProvider(
            api_key=settings.geoapify_api_key,
            endpoint=settings.geoapify_url,
            timeout_seconds=settings.geoapify_timeout_seconds,
        )
        geoapify_budget = SQLiteDailyRequestBudget(
            settings.database_path,
            provider="geoapify",
            daily_limit=settings.geoapify_daily_request_budget,
        )
        budgeted_geoapify = DailyBudgetPlacesProvider(
            geoapify_provider,
            budget=geoapify_budget,
        )
        geoapify_cache = CachedPlacesProvider(
            budgeted_geoapify,
            ttl_seconds=settings.provider_cache_ttl_seconds,
            max_entries=settings.provider_cache_max_entries,
        )
        aggregate_providers.append(geoapify_cache)
        caches.append(("geoapify", geoapify_cache))
        closable_providers.append(geoapify_provider)

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

    foursquare_provider: FoursquareProvider | None = None
    if settings.foursquare_api_key.strip():
        foursquare_provider = FoursquareProvider(
            api_key=settings.foursquare_api_key,
            endpoint=settings.foursquare_url,
            timeout_seconds=settings.foursquare_timeout_seconds,
        )
        foursquare_cache = CachedPlacesProvider(
            foursquare_provider,
            ttl_seconds=settings.provider_cache_ttl_seconds,
            max_entries=settings.provider_cache_max_entries,
        )
        aggregate_providers.append(foursquare_cache)
        caches.append(("foursquare", foursquare_cache))
        closable_providers.append(foursquare_provider)

    provider_statuses = (
        ProviderStatus(
            key="osm",
            label="OpenStreetMap / Overpass",
            enabled=True,
            capabilities=OVERPASS_CAPABILITIES,
        ),
        ProviderStatus(
            key="geoapify",
            label="Geoapify Places",
            enabled=geoapify_provider is not None,
            capabilities=GEOAPIFY_CAPABILITIES,
            disabled_reason=(
                None
                if geoapify_provider is not None
                else "GEOAPIFY_API_KEY не настроен"
            ),
        ),
        ProviderStatus(
            key="2gis",
            label="2GIS Places",
            enabled=twogis_provider is not None,
            capabilities=TWOGIS_CAPABILITIES,
            disabled_reason=(
                None if twogis_provider is not None else "TWOGIS_API_KEY не настроен"
            ),
        ),
        ProviderStatus(
            key="foursquare",
            label="Foursquare Places",
            enabled=foursquare_provider is not None,
            capabilities=FOURSQUARE_CAPABILITIES,
            disabled_reason=(
                None
                if foursquare_provider is not None
                else "FOURSQUARE_API_KEY не настроен"
            ),
        ),
    )

    composite_provider = CompositePlacesProvider(aggregate_providers)
    favorites_repository = FavoritesRepository(settings.database_path)
    ratings_repository = RatingsRepository(settings.database_path)
    search_service = SearchService(
        composite_provider,
        ratings_repository=ratings_repository,
    )
    health_server = HealthServer(
        host=settings.health_host,
        port=settings.health_port,
    )

    try:
        await health_server.start()
        await initialize_database(settings.database_path)
        health_server.state.mark_ready()

        logger.info(
            "permplaces_start providers=%d overpass_endpoints=%d geoapify_enabled=%s "
            "twogis_enabled=%s foursquare_enabled=%s geoapify_daily_budget=%d "
            "cache_ttl_seconds=%s cache_max_entries=%d health_port=%d",
            len(aggregate_providers),
            len(settings.overpass_endpoints),
            geoapify_provider is not None,
            twogis_provider is not None,
            foursquare_provider is not None,
            settings.geoapify_daily_request_budget,
            settings.provider_cache_ttl_seconds,
            settings.provider_cache_max_entries,
            settings.health_port,
        )

        await dispatcher.start_polling(
            bot,
            search_service=search_service,
            favorites_repository=favorites_repository,
            ratings_repository=ratings_repository,
            provider_statuses=provider_statuses,
        )
    finally:
        health_server.state.mark_not_ready()
        await health_server.close()

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
