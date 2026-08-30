# Outcome Intelligence read path

Outcome Intelligence consumes a durable, read-only full trade snapshot published from the production API.

Source endpoint: `/research/trades`, read through an SSH local-forward from GitHub Actions to production `127.0.0.1:8000`.

Published branch: `outcome-intelligence-snapshots`.

Latest files:

- `data/outcome_intelligence/latest/trades.json`
- `data/outcome_intelligence/latest/manifest.json`

The snapshot is fail-closed: pagination totals must remain stable during capture, trade IDs must be unique, the full population must be present, and the manifest SHA-256 must match the artifact. The workflow does not mutate the production database, trading state, services, or repository checkout.
