# Local favorite facets

PermPlaces can filter the current user's already loaded favorites by saved category and district
fields without contacting an external places provider.

## Facets

Two local facets are available:

- saved-card category;
- saved-card district.

Category filtering compares the internal category key stored in each favorite snapshot.

District filtering compares only the district text already present in the saved card. Missing or
blank district data can be selected explicitly as `Район не указан`. PermPlaces does not infer,
geocode or repair a missing district while applying this filter.

## Option construction

Facet counts are built from the full loaded favorites set, not from the currently visible subset.

Options are ranked deterministically by:

1. larger count first;
2. normalized user-facing label;
3. raw stable value.

At most 30 category or district options are rendered in one menu. This keeps Telegram keyboards
bounded. Perm's normal administrative-district set is well below that bound, while unusual provider
labels still remain deterministic.

Callback payloads do not contain raw district text. Each option uses a deterministic SHA-256-derived
token and the handler resolves that token only against the current in-memory option set. A stale or
unknown token fails closed.

## Composition with other local favorite tools

Category/district facets compose with:

- personal-tag filtering;
- local deterministic sorting.

Selecting a category or district clears an active text-search query because text search has its own
relevance ordering. The current personal-tag filter and sort mode remain active.

Starting a successful text search clears tag/category/district filters so the result set and the
visible local state cannot disagree.

`🧹 Сбросить категорию и район` clears only those two facets, plus any active text-search query;
it preserves the personal-tag filter and local sort.

If a favorite mutation removes the last visible result under the active local filters, PermPlaces
falls back to the unfiltered loaded favorites set rather than leaving an inconsistent empty view.

## Data semantics

These facets organize saved snapshots. They do not prove that the current external provider still
classifies a venue the same way.

A missing district remains unknown. No district name is synthesized from coordinates, address text
or another venue.

## Privacy and provider behavior

Facet construction and filtering run entirely in memory. They perform no OSM, Geoapify, 2GIS or
Foursquare request and create no persistent analytics/history table.

The selected facet values live only in the current aiogram FSM state for the running process.
