# Favorites overview

PermPlaces can build a compact overview of the current Telegram user's already loaded favorites.

## What is counted

The overview is computed only from saved favorite cards plus the user's own local metadata:

- total saved favorites;
- favorites with a non-empty personal note;
- favorites with at least one known personal tag;
- counts for the fixed personal tag set;
- top saved-card category labels;
- top districts when a district is actually present in the saved card;
- count of saved cards where the district field is absent.

The overview does not infer missing districts or categories and does not enrich stale favorites from
an external provider.

## Ordering

Category and district sections are ordered deterministically:

1. larger count first;
2. normalized label as a deterministic tie-breaker.

Only the first five labels are displayed in each of those sections.

Personal tag counts follow the application's fixed tag order.

## Telegram flow

From a favorite result card choose `📊 Обзор избранного`.

The overview exposes navigation to:

- tag filtering;
- category/district facets;
- local favorite search;
- local favorite sorting;
- the current favorite result card.

It always uses the full `favorite_all_results` set rather than the currently filtered or searched
subset, so counts represent the loaded favorites list.

## Data semantics

Personal notes and tags are user-authored local organization data. Their counts must not be
presented as provider-backed venue characteristics.

Category labels and districts are shown only as fields already present in saved cards. A missing
district stays explicitly missing.

## Privacy and provider behavior

The overview performs no OSM, Geoapify, 2GIS or Foursquare request and does not create a new
persistent analytics table.

No note text, Telegram user ID, exact provider identity or search query is included in the
overview. Only aggregate counts and saved-card labels are rendered.
