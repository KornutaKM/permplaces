# Foursquare provider contract

PermPlaces can optionally enrich nearby results through the Foursquare Places API (New).

The adapter is disabled unless `FOURSQUARE_API_KEY` is non-empty.

## Why this provider exists

OpenStreetMap does not provide a consumer rating system. 2GIS Places API 3.0 can filter by the
presence of ratings or reviews, but its documented public search response does not expose rating
values or review text. Foursquare Places exposes rich place fields such as rating, rating-count
statistics, price, hours and attributes depending on the account's field entitlement.

PermPlaces stores Foursquare ratings with `rating_scale=10` and field provenance. A rating,
its scale and its rating-count metadata are never combined across providers.

## Request contract

The adapter uses:

- `GET https://places-api.foursquare.com/places/search`;
- `Authorization: Bearer <service key>`;
- `X-Places-Api-Version: 2025-06-17`;
- explicit response fields only;
- `ll` plus a bounded radius;
- `sort=DISTANCE`;
- at most 50 results per upstream call.

The service key is never logged or committed.

## Supported filters

- nearby category search;
- Wi-Fi when the provider explicitly returns a positive Wi-Fi attribute;
- outdoor seating when explicitly true;
- open now through the provider's `open_now` filter;
- open at 23:00 through `open_at`, using the Perm local weekday.

Fail-closed cases:

- family-friendly semantics are not inferred from unrelated attributes;
- `open_now + open_late` in one request is not synthesized;
- district mode stays OSM-authoritative because Foursquare cannot consume the exact OSM relation
  identity used by PermPlaces;
- unsupported categories return no Foursquare candidates.

## Data semantics

- rating: Foursquare 0–10 scale;
- rating count: `stats.total_ratings`;
- price: Foursquare 1–4 tier, rendered as `₽` through `₽₽₽₽`;
- menu: accepted only as an explicit `http`/`https` URL returned by Foursquare;
- missing or malformed values remain missing;
- Foursquare is shown in card attribution whenever it contributes data.

The deployment operator remains responsible for the active Foursquare license, account
entitlements, pricing, attribution and branding requirements. The adapter is optional; if a
Foursquare request fails at provider level, the composite provider can continue with other
configured sources.

Official API references:

- https://docs.foursquare.com/fsq-developers-places/reference/place-search
- https://docs.foursquare.com/fsq-developers-places/reference/place-details
- https://docs.foursquare.com/fsq-developers-places/reference/authentication


## Visual attribution

Any Telegram card that contains Foursquare Places Data must display the branded credit
`Powered by Foursquare`. Provider provenance is therefore also a display-compliance signal:
if Foursquare contributes any merged field, the card keeps a Foursquare source reference and
renders the credit.


## Menu links

The adapter requests the documented `menu` field. PermPlaces exposes a Telegram `📖 Меню`
button only when that field is a syntactically valid HTTP(S) URL.

No menu URL is inferred from the venue website, search-engine results, venue name or address.
If the provider omits the field, the button is absent. When an OSM-primary card is enriched with
a Foursquare menu URL, field-level provenance records Foursquare as the source and the card keeps
the required `Powered by Foursquare` credit.
