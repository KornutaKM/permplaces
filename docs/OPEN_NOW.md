# Semantic “Open now” filtering

PermPlaces evaluates the OpenStreetMap `opening_hours` expression instead of
using string heuristics.

## Dependency

The Python package `opening-hours-py` provides bindings for the Rust
`opening-hours` implementation.

PermPlaces passes the venue coordinates to the parser so the venue timezone and
country context can be inferred where needed.

## Fail-closed rule

A venue is returned by the “Открыто сейчас” filter only when evaluation returns
an explicit OPEN state.

These states do **not** pass the filter:

- CLOSED;
- UNKNOWN;
- missing `opening_hours`;
- syntactically invalid `opening_hours`.

This avoids presenting an uncertain venue as currently open.

## Query stages

1. Overpass prefilters to objects that contain an `opening_hours` tag.
2. PermPlaces parses each expression locally.
3. Only OPEN venues remain.
4. Returned cards receive ephemeral `is_open_now=True`.

`is_open_now` is intentionally stripped before saving a venue to favorites,
because it is a time-sensitive observation rather than durable venue data.
