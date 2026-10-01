# Favorites identity

PermPlaces stores favorites as provider-backed venue snapshots. The same physical venue may later
be discovered through a different provider identity after OSM/Geoapify dedup. Favorites therefore
use the same alias identity contract as community ratings.

## Identity keys

Every venue has one or more identity keys:

```text
provider:source_id
```

For a merged venue the key set includes the primary provider identity plus every `source_ref`.
When an OSM identity is known it is the canonical identity used by shared identity helpers.

Identity keys are exact provider IDs. PermPlaces does not infer favorite identity from similar
names, addresses, phone numbers or websites at persistence time.

## Alias-aware toggle

When a user presses the favorite action, PermPlaces looks up the selected venue's provider identity
keys in the indexed `favorite_identity_aliases` table for that same Telegram user. It no longer
needs to load and decode every saved favorite to find an alias match.

If any key overlaps, all stored rows representing that aliased venue are removed and the toggle
returns the "removed" state. This means a place favorited earlier as Geoapify can later be removed
from an OSM+Geoapify merged card without creating a duplicate.

The operation runs under one SQLite `BEGIN IMMEDIATE` transaction, preserving the existing
concurrent-toggle serialization contract.

## Historical duplicates

The schema v1 → v2 migration backfills alias rows for existing favorites. Older databases may
already contain two favorite rows that later become aliases of one merged venue. Reads still hide
those duplicate alias rows deterministically: the newest ordered snapshot is returned and
overlapping identities are suppressed.

The historical rows are not rewritten during read. A later favorite toggle for the merged venue
removes every matching alias row in the same transaction.

## Personal notes

A saved favorite can have one private personal note. Notes use the same exact provider identity
keys as favorites, remain separate from the provider-backed favorite snapshot, and are never
treated as venue provenance.

Removing a favorite removes notes attached to all known aliases for that favorite in the same
transaction. See `docs/FAVORITE_NOTES.md`.

## Personal tags

Saved favorites can also carry predefined private organizational tags. Tags use the same exact
provider identity keys, stay separate from the provider-backed favorite snapshot, and never count
as evidence about venue capabilities.

Removing a favorite removes tag rows attached to all known aliases in the same transaction.
Favorites can be filtered locally by those user-selected tags without external requests. See
`docs/FAVORITE_TAGS.md`.

## Local search

The current user's already loaded favorites can be searched locally by saved venue text, personal
note and personal tag labels. This search does not call a places provider, does not change
provider provenance and does not persist a search-history row.

Matching and deterministic ranking are documented in `docs/FAVORITE_SEARCH.md`.

## Local sorting

The visible favorites view can be sorted locally by repository order, normalized name, presence of
a personal note or count of known personal tags. Sorting composes with tag filtering and does not
contact external providers.

External provider ratings are not used as a cross-provider sort key because their scales are not
assumed to be comparable. See `docs/FAVORITE_SORTING.md`.

## Safety

Alias matching is scoped by Telegram user ID. Two different users never affect each other's
favorites.

Different provider identities remain separate even when venue names are identical. This keeps
favorite persistence conservative and avoids merging chain branches based on display text.
