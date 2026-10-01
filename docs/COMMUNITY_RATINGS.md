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
vote. The rating dialog shows the user's current score when one exists and allows the user to
remove it. Removal deletes that user's vote across every known provider alias for the merged venue.

## Venue identity and aliases

A merged venue may have several `source_refs`. Ratings and favorites share the same
`provider:source_id` identity-key contract. Rating reads consider all known provider keys so votes
collected before a later OSM/Geoapify merge remain visible.

When an OSM source reference is available, new votes use that OSM identity as the canonical key.
Otherwise the current primary provider identity is used.

If one user has historical votes under more than one alias, only the newest vote contributes to
the aggregate. This prevents a provider merge from double-counting one Telegram account.

List enrichment is batched: provider aliases for the selected venues are loaded in bounded SQLite
chunks and aggregated in memory. This avoids one query per card, stays below conservative SQLite
parameter limits, and preserves the same alias/per-user deduplication rules.

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

Telegram user IDs are used only to scope local user data and enforce one current vote per user and
venue identity. They are not shown in cards, diagnostics or rating summaries and are not sent to
places providers.

Users can inspect their own persistent row counts and delete all of their community ratings through
`/mydata`. The same confirmed transaction also deletes their favorites. Historical provider
aliases for that user are removed because deletion is keyed by Telegram user ID, not by one venue
alias.

The current MVP stores numeric ratings only. It does not collect free-text reviews. See
`docs/PRIVACY.md` for the complete application-data contract.
