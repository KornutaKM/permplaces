# Local favorite sorting

PermPlaces can reorder the current user's already loaded favorites locally without contacting a
places provider.

## Sort modes

The current modes are:

- `recent` — preserve the repository order, newest saved favorites first;
- `name` — normalized venue name;
- `notes` — favorites with a non-empty personal note first;
- `tags` — favorites with more known personal tags first.

All modes are deterministic. Stable ordering preserves the existing favorite order when two venues
have the same sort key.

## Search and filter interaction

Tag filtering and sorting can be combined. The tag filter is applied first, then the selected sort.

Favorite text search has relevance ranking of its own, so an active text search temporarily takes
priority over the selected sort. Choosing a sort while text search is active clears the text search
and applies the selected sort to the current tag-filtered favorite set.

Clearing text search restores the selected favorite sort.

## Data semantics

Sorting never treats personal notes or personal tags as provider facts. The `notes` and `tags`
sort modes only organize the user's own saved list.

Provider ratings are deliberately not used for favorite sorting because PermPlaces can receive
ratings on different provider-specific scales and does not normalize them into a synthetic score.

## Privacy and provider behavior

Sorting performs no OSM, Geoapify, 2GIS or Foursquare request.

The selected sort key exists only in the current aiogram FSM state. It is not written to the SQLite
database and is not included in `/mydata` export.
