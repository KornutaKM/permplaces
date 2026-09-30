# Geoapify free Places provider

Geoapify is the recommended optional second provider for the zero-cost PermPlaces setup.

## Why it is optional

OpenStreetMap/Overpass remains the primary source and the authority for exact Perm district relation searches. Geoapify is enabled only when `GEOAPIFY_API_KEY` is configured.

The provider currently participates only in nearby searches. It never approximates an OSM district relation with a text name or bounding box.

## Free-plan budget

PermPlaces caps one Geoapify Places request at 20 results. Geoapify prices Places requests in 20-result credit blocks, so this keeps each bot provider call bounded to one Places credit under the current public pricing model.

The application cache still applies before the provider adapter, so repeated identical searches within the configured TTL do not consume another upstream request.

## Supported categories

The adapter maps only categories that can be expressed without inventing semantics:

- restaurant -> `catering.restaurant`;
- cafe -> `catering.cafe`;
- bar -> `catering.bar,catering.pub`;
- fastfood -> `catering.fast_food`;
- pizza -> restaurant/fast-food pizza categories;
- sushi -> `catering.restaurant.sushi`;
- dessert -> explicit dessert/cake/ice-cream categories;
- food_drink -> `catering`.

The app's `breakfast` category is intentionally OSM-only because the current Geoapify category contract does not prove that a generic cafe or restaurant serves breakfast.

## Filters and fail-closed behavior

Geoapify's `internet_access` condition is used for the Wi-Fi filter. A result returned through that filtered request is marked `wifi=True`.

Terrace, family, open-now and open-at-23:00 filters currently stay OSM-only. The Geoapify adapter returns no candidates for those filtered searches rather than pretending that an unsupported signal is true.

## Data and provenance

Geoapify search results currently contribute only fields directly returned by the Places response:

- name;
- coordinates;
- address;
- district, when present;
- Wi-Fi only when proven by the provider condition/category;
- Geoapify `place_id` as provider identity.

No rating, review count, price, menu, photo, opening-hours or contact field is synthesized.

Merged records retain field-level provenance through the existing conservative dedup layer.

## Attribution

Any card containing Geoapify data displays both:

- OpenStreetMap attribution, because Geoapify Places is based on OSM/open data;
- `Powered by Geoapify`, required on the free plan.

## Configuration

```env
GEOAPIFY_API_KEY=
GEOAPIFY_URL=https://api.geoapify.com/v2/places
GEOAPIFY_TIMEOUT_SECONDS=10
```

When the key is empty, no Geoapify request is made.
