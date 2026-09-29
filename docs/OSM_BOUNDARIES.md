# Perm OSM administrative boundaries

PermPlaces uses explicit OpenStreetMap administrative-boundary relations for district search.
The IDs are treated as governed data rather than inferred coordinates.

| Search area | OSM relation |
| --- | ---: |
| Perm Urban Okrug | 1084793 |
| Дзержинский | 1268696 |
| Индустриальный | 1268694 |
| Кировский | 1268698 |
| Ленинский | 1268697 |
| Мотовилихинский | 1268693 |
| Орджоникидзевский | 1268692 |
| Свердловский | 1268699 |

## Query semantics

The Overpass provider loads the selected relation and applies `map_to_area`.
Venue queries then use `nwr(area.searchArea)`, so search is bounded by the
administrative polygon rather than an approximate center/radius.

## Verification sources

- OpenStreetMap relation 1084793 — Perm Urban Okrug:
  https://www.openstreetmap.org/relation/1084793
- OpenStreetMap relation 1268693 — Мотовилихинский район:
  https://www.openstreetmap.org/relation/1268693
- Wikidata / OSM identifiers for Perm districts:
  https://www.wikidata.org/wiki/Q4160819
  https://www.wikidata.org/wiki/Q4200942
  https://www.wikidata.org/wiki/Q3924191
  https://www.wikidata.org/wiki/Q3497234
  https://www.wikidata.org/wiki/Q3831507
- Cross-check for the remaining district relation identities:
  https://gis-lab.info/qa/duma2016.html
- Overpass `map_to_area` semantics:
  https://wiki.openstreetmap.org/wiki/OverpassQL

If OSM changes an administrative relation identity, update this document,
`app/districts.py`, and the pinned tests together.
