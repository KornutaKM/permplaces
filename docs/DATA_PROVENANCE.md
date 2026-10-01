# Data provenance and cross-provider identity

PermPlaces treats external catalogs as independent evidence sources.

## Core rule

A field from one provider must never silently become a fact attributed to another provider.

Every canonical venue may therefore contain:

- a primary identity (`source` + `source_id`);
- `source_refs` for every provider object merged into that venue;
- `field_sources` identifying which provider supplied the selected value for each sourced field.

The primary identity stays stable according to provider priority. Adding a secondary provider must not silently change an existing OSM-backed venue ID.

## Conservative deduplication

Two records are considered the same physical venue only when bounded identity evidence is strong enough:

1. identical provider + source ID;
2. matching phone inside a branch-sized radius or with matching normalized address;
3. shared website host only with matching address or very-close coordinates;
4. exact normalized name with matching address or close coordinates;
5. generic venue-type name variants only with matching address or very-close coordinates.

Records more than 500 m apart never merge.

Otherwise the records remain separate.

This intentionally prefers duplicate cards over falsely merging two branches of the same chain.

## Merge precedence

Provider order is deterministic priority order.

The primary provider keeps its non-empty values. Secondary providers may fill only missing fields.

Special rule:

- `rating` + `review_count` are an atomic pair. A review count from provider B is never displayed next to a rating selected from provider A.

No fuzzy averaging or synthesized rating is allowed.

## Partial provider failure

The composite layer may return results from healthy providers when another provider fails with `ProviderError`.

Programming errors and unexpected exceptions are not downgraded to provider outages; they propagate and fail visibly.

## Persistence

Favorites serialize both source references and field provenance. Time-relative derived state such as distance, `is_open_now`, `is_open_late`, and the current community-rating aggregate remains non-persistent in favorite payloads.

Community votes are stored separately in SQLite. They are local user-generated application data, not provider facts, so they do not receive external `FieldSource` entries. Aggregation reads all known provider aliases for a merged venue and deduplicates historical alias votes by Telegram user ID.

## Current runtime

v0.25 keeps OpenStreetMap/Overpass as the primary provider and exact district-boundary authority. Geoapify Places is the recommended free optional secondary provider for nearby search when `GEOAPIFY_API_KEY` is configured.

2GIS and Foursquare integrations remain optional and disabled without explicit keys. Their absence must not reduce the correctness of the OSM/Geoapify path.

Geoapify records retain `provider=geoapify` even though the underlying Places data is primarily OSM/open data. Cards containing Geoapify data therefore show both the required OpenStreetMap attribution and `Powered by Geoapify` on the free plan.

See `docs/GEOAPIFY.md` for category, filter and credit-budget contracts.

v0.26 adds a static provider capability contract before aggregation. Unsupported categories,
filters and district modes are skipped before an upstream request instead of relying only on
adapter-local no-op behavior. This keeps fail-closed semantics explicit and reduces unnecessary
paid/free quota use.

Dedup v2 keeps provider priority deterministic but records corroborating `FieldSource` entries
when multiple providers return the same retained field value. Different values are never marked
as corroboration. Shared chain websites and generic venue-type names are not sufficient identity
signals by themselves; address/proximity constraints remain mandatory.

See `docs/PROVIDERS.md` for the complete routing and identity contract.


## Community ratings

v0.27 adds a local 1–5 community rating layer. It is rendered explicitly as a PermPlaces user
aggregate and never replaces or modifies an external provider rating. Scenario Engine does not
rank by this signal and does not include it in provider-backed explanation reasons.

See `docs/COMMUNITY_RATINGS.md` for identity, persistence and privacy details.
