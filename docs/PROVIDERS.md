# Provider contracts

PermPlaces uses a free-first provider stack. OpenStreetMap/Overpass is always the primary
provider; Geoapify Places is the recommended optional second provider for nearby search.
2GIS and Foursquare remain optional integrations and are never required for the core bot.

## Capability routing

Each adapter publishes a conservative `ProviderCapabilities` contract. The composite
provider checks this contract before making an upstream request.

A capability means that the adapter can prove the requested signal. It does not mean that
every returned venue contains the field.

| Capability | OSM / Overpass | Geoapify | 2GIS | Foursquare |
| --- | --- | --- | --- | --- |
| Nearby search | yes | yes | yes | yes |
| Exact OSM district search | yes | no | no | no |
| Wi-Fi filter | yes | yes | no | yes |
| Outdoor seating filter | yes | no | no | yes |
| Open now | yes | no | yes | yes |
| Open at 23:00 | yes | no | yes | yes |
| Family filter | yes | no | no | no |
| Opening-hours field | yes | no | no | yes |
| Rating/review metadata | no | no | no | optional field | 
| Photos/menu | no | no | no | optional field |

2GIS and Foursquare cannot currently prove `open_now + open_late` in one request, so that
combination is routed away from those adapters. Geoapify does not claim breakfast support.

Unknown third-party/test adapters remain routable for backwards compatibility, but the
compatibility contract does not claim enrichment capabilities such as ratings, photos or menu.

## Runtime diagnostics

The Telegram command:

```text
/providers
```

shows which adapters are enabled and the capabilities they advertise. The output never
contains API keys, tokens, endpoint query strings or user coordinates.

## Dedup v2

Cross-provider merging stays intentionally conservative:

1. Same provider + same source ID always matches.
2. Results more than 500 m apart never match.
3. Matching phone numbers are accepted only within a branch-sized radius or with a matching
   normalized address.
4. Shared website host alone does not merge chain branches unless coordinates/address also
   support the match.
5. Exact normalized names merge only with matching address or close coordinates.
6. Generic venue-type words such as `кафе`, `кофейня`, `cafe`, `restaurant` may be
   removed for identity comparison only when address or very-close coordinates provide
   independent evidence.

Address comparison normalizes common Perm/street designators, so `ул. Ленина, 10` and
`улица Ленина 10, Пермь` can corroborate the same entity without rewriting the displayed
provider value.

When two providers return the same retained field value, field-level provenance keeps both
sources. When values disagree, provider priority remains deterministic: the primary value is
kept and the secondary value is not presented as corroboration.

Rating + scale + review count and photo collections remain atomic provider-backed groups.
PermPlaces never synthesizes those groups from different sources.
