# Deterministic text search

PermPlaces does not use an LLM to turn free text into venue facts or filters.

The parser only maps a bounded set of user phrases to already-supported search controls.

## Examples

```text
кофе с Wi-Fi рядом 1 км
ресторан с верандой в Ленинском районе
суши по всей Перми
кафе без Wi-Fi в Мотовилихинском районе
```

## Supported dimensions

- category;
- one of the seven Perm districts;
- whole-Perm search;
- explicit nearby intent;
- radius from 100 m to 10 km;
- Wi-Fi on/off;
- terrace/outdoor seating on/off.

## State rules

- an explicitly named district overrides the prior search scope;
- “Вся Пермь” uses the governed Perm Urban Okrug OSM relation;
- “рядом” or an explicit radius switches to saved Telegram coordinates when available;
- if location is required but has never been provided, search stops and asks for Telegram location;
- a radius supplied together with an explicit district is not silently applied and the user is informed;
- negated feature phrases can disable a previously active filter;
- an out-of-range radius is rejected rather than falling back to an older radius.

## Non-goals

The parser does not infer subjective intent such as “уютно”, “романтично”, “лучшее” or “недорого” until a governed source/feature model exists for those dimensions.
