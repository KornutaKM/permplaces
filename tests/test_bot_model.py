from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendPhoto

from app.bot import _send_venue_detail, _venue_from_dict
from app.data import FieldSource, PhotoRef, SourceRef, Venue


def test_bot_state_restores_nested_provider_objects() -> None:
    venue = Venue(
        id="osm:node/visual",
        name="Visual",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id="node/visual",
        source_refs=(
            SourceRef("osm", "node/visual"),
            SourceRef("foursquare", "fsq-visual"),
        ),
        field_sources=(
            FieldSource("name", "osm", "node/visual"),
            FieldSource("photos", "foursquare", "fsq-visual"),
        ),
        photos=(
            PhotoRef(
                provider="foursquare",
                source_id="photo-visual",
                url="https://images.example.test/original/visual.jpg",
                attribution="Powered by Foursquare",
            ),
        ),
        cuisine=("coffee_shop",),
    )

    restored = _venue_from_dict(asdict(venue))

    assert restored == venue
    assert restored.source_refs[1].provider == "foursquare"
    assert restored.field_sources[1].field_name == "photos"
    assert restored.photos[0].source_id == "photo-visual"



@pytest.mark.asyncio
async def test_visual_detail_falls_back_to_text_when_telegram_rejects_photo() -> None:
    photo_url = "https://images.example.test/original/fallback.jpg"
    venue = Venue(
        id="foursquare:fallback",
        name="Fallback place",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="foursquare",
        source_id="fallback",
        photos=(
            PhotoRef(
                provider="foursquare",
                source_id="photo-fallback",
                url=photo_url,
                attribution="Powered by Foursquare",
            ),
        ),
    )
    answer_photo = AsyncMock(
        side_effect=TelegramBadRequest(
            method=SendPhoto(chat_id=1, photo=photo_url),
            message="Bad Request: failed to get HTTP URL content",
        )
    )
    answer = AsyncMock()
    message = SimpleNamespace(answer_photo=answer_photo, answer=answer)

    await _send_venue_detail(message, venue)

    answer_photo.assert_awaited_once()
    answer.assert_awaited_once()
    assert answer.await_args.kwargs["disable_web_page_preview"] is True
    assert "Fallback place" in answer.await_args.args[0]


@pytest.mark.asyncio
async def test_visual_detail_does_not_send_text_when_photo_succeeds() -> None:
    venue = Venue(
        id="foursquare:photo-ok",
        name="Photo place",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="foursquare",
        source_id="photo-ok",
        photos=(
            PhotoRef(
                provider="foursquare",
                source_id="photo-ok",
                url="https://images.example.test/original/ok.jpg",
                attribution="Powered by Foursquare",
            ),
        ),
    )
    answer_photo = AsyncMock()
    answer = AsyncMock()
    message = SimpleNamespace(answer_photo=answer_photo, answer=answer)

    await _send_venue_detail(message, venue)

    answer_photo.assert_awaited_once()
    answer.assert_not_awaited()
