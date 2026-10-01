# Local favorite search

PermPlaces can search inside the current Telegram user's saved favorites without contacting an
external places provider.

## Searchable data

The local index is built in memory from the already loaded favorite view. Search can match:

- venue name;
- saved address;
- category label;
- saved district;
- cuisine values;
- the user's private personal note;
- the user-facing labels of the user's private favorite tags.

Provider identities, API keys and other users' data are not search fields.

## Matching

The query is normalized with Unicode case folding, punctuation-to-space normalization and
Russian `ё` → `е` normalization.

Every query token must be present somewhere in the combined searchable fields. Tokens may match
different fields, for example an address token plus a personal-note token.

Results are deterministic:

1. exact normalized venue-name match;
2. venue name starts with the complete normalized query;
3. all tokens are present in the venue name;
4. matches through the remaining searchable fields;
5. original favorites order is retained inside the same rank.

## Telegram flow

From the favorites result keyboard choose `🔎 Поиск в избранном`, then enter up to 100
characters.

A successful query replaces only the visible in-memory favorite result set. The full loaded
favorites list remains available for clearing search or switching to a tag filter.

`🧹 Сбросить поиск` restores the complete favorite list using the currently selected local
favorite sort mode.

Text-search relevance ranking takes priority while a query is active. A successful new text search
clears personal-tag/category/district/cuisine filters so the visible result set cannot disagree
with local filter state. Choosing an explicit sort or category/district/cuisine facet clears the
text query before applying that local view. See `docs/FAVORITE_SORTING.md` and
`docs/FAVORITE_FACETS.md`.

## Privacy and provider behavior

Favorite search performs no OSM, Geoapify, 2GIS or Foursquare request.

The search query is stored only in the current aiogram FSM state for the running process. PermPlaces
does not add a persistent search-history table and does not include favorite-search queries in the
`/mydata` export.

Personal notes and tags remain local user-authored data and are not converted into provider facts
by search matching.
