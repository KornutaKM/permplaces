# Community ratings

PermPlaces can collect a lightweight 1–5 score from Telegram users without depending on a
paid places provider.

## Data model

Community ratings are local application data. They are not external provider facts and are
therefore stored separately from provider `rating`, `rating_scale` and `review_count`.

Each vote stores:

- Telegram user ID;
- a provider-backed venue identity key;
- integer score from 1 to 5;
- update timestamp.

One user has one current vote per canonical venue key. Submitting another score updates that
vote.

## Venue identity and aliases

A merged venue may have several `source_refs`. Rating reads consider all known provider keys so
votes collected before a later OSM/Geoapify merge remain visible.

When an OSM source reference is available, new votes use that OSM identity as the canonical key.
Otherwise the current primary provider identity is used.

If one user has historical votes under more than one alias, only the newest vote contributes to
the aggregate. This prevents a provider merge from double-counting one Telegram account.

## Presentation

Cards label the aggregate explicitly as:

```text
👥 PermPlaces: 4.3/5 (7)
```

External provider ratings remain separate. Community ratings are not copied into provider
provenance and are not used by Scenario Engine ranking or the “Почему подходит” block.

## Persistence and privacy

Votes live in the same SQLite database as favorites and are included in the existing SQLite
backup/restore procedure.

Telegram user IDs are used only to enforce one current vote per user and venue identity. They are
not shown in cards, diagnostics or rating summaries and are not sent to places providers.

The current MVP stores numeric ratings only. It does not collect free-text reviews.
