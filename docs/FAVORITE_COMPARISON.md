# Favorite comparison

PermPlaces can compare two places from the current user's already loaded favorites without calling
an external places provider.

## Flow

From a favorite result card choose `⚖️ Сравнить с другим избранным`.

The current visible favorite becomes the primary comparison item. PermPlaces then offers up to 20
other favorites in repository order. Option callbacks contain only deterministic SHA-256-derived
tokens; raw venue IDs are not embedded in the comparison option callback.

A stale or unknown option token fails closed.

## Fields

The comparison is built from saved favorite snapshots and local user data. It can show:

- category label;
- saved address;
- saved district;
- saved cuisine values;
- saved opening-hours expression;
- saved Wi-Fi and outdoor-seating values;
- confirmed saved family features;
- saved provider price label;
- provider rating only when an explicit rating scale is also saved;
- PermPlaces community rating on its native 1–5 scale;
- the current user's personal tag labels.

Missing fields remain explicit unknown values. The comparison does not infer an address, district,
cuisine, price, family suitability or any other venue fact.

## Deliberately excluded

The comparison does not rank the two places and does not produce a winner or synthetic score.

`distance_m` is excluded because a saved favorite may contain a distance from an older search
context.

`is_open_now` and `is_open_late` are excluded because those booleans are time-contextual saved
snapshot values and should not be presented as current truth later.

Provider ratings are displayed only with their explicit saved scale. Ratings from different
providers are not normalized or compared as if they shared one scale.

Personal note text is not repeated in the comparison card. Personal tags may be shown because they
are explicit user-authored organization data, not provider facts.

## Attribution

The comparison takes the union of providers contributing to the two saved cards.

- OSM data keeps the required OpenStreetMap contributors / ODbL attribution.
- Geoapify contribution keeps both OSM attribution and `Powered by Geoapify`.
- Foursquare contribution keeps `Powered by Foursquare`.
- 2GIS contribution is identified as 2GIS.

## Privacy and provider behavior

Comparison runs entirely in memory over the already loaded favorites set. It creates no persistent
comparison-history table and makes no OSM, Geoapify, 2GIS or Foursquare request.

Only the selected primary favorite ID is kept temporarily in the aiogram FSM state for the running
process. Opening the favorites list again resets this comparison state.
