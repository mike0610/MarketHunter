# Strategy Lab public statistics endpoint

The production public read-only route is expected to use the existing Nginx `/api` reverse proxy:

`GET /api/strategy-lab/statistics`

The backend route remains `GET /strategy-lab/statistics` on `127.0.0.1:8000`.

Deployment is complete only when an external GitHub-hosted runner receives HTTP 200 and valid JSON containing `research_track: SL`, `summary`, and `strategies` from the public route.

No strategy, execution, risk, sizing, paper-trading, or database behavior is changed by this routing proof.
