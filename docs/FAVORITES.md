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

When a user presses the favorite action, PermPlaces compares the selected venue's provider identity
keys with every stored favorite for that same Telegram user.

If any key overlaps, all stored rows representing that aliased venue are removed and the toggle
returns the "removed" state. This means a place favorited earlier as Geoapify can later be removed
from an OSM+Geoapify merged card without creating a duplicate.

The operation runs under one SQLite `BEGIN IMMEDIATE` transaction, preserving the existing
concurrent-toggle serialization contract.

## Historical duplicates

Older databases may already contain two favorite rows that later become aliases of one merged
venue. Reads hide those duplicate alias rows deterministically: the newest ordered snapshot is
returned and overlapping identities are suppressed.

The historical rows are not rewritten during read. A later favorite toggle for the merged venue
removes every matching alias row in the same transaction.

## Safety

Alias matching is scoped by Telegram user ID. Two different users never affect each other's
favorites.

Different provider identities remain separate even when venue names are identical. This keeps
favorite persistence conservative and avoids merging chain branches based on display text.
