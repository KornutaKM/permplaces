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

Two records are considered the same physical venue only when at least one bounded signal is strong enough:

1. identical provider + source ID;
2. same normalized phone within 500 m;
3. same normalized website host within 500 m;
4. same normalized name + same normalized address within 500 m;
5. same normalized name within 40 m.

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

Favorites serialize both source references and field provenance. Time-relative derived state such as distance, `is_open_now`, and `is_open_late` remains non-persistent.

## Current runtime

v0.15 still activates only OpenStreetMap. The composite layer runs with one provider so current user-visible behavior stays unchanged.

The purpose of this milestone is to make the next external catalog integration safe before adding rating/review/check data.
