"""
MarketHunter

tools/outcome_intelligence

Outcome Intelligence V1 - a research-local, read-only tool that
captures immutable snapshots of the existing `GET /research/statistics`
and `GET /research/statistics/setup-reasons` endpoints and produces
bounded daily/weekly analysis reports with sample-size guardrails.

Non-goals:
- No new API endpoint, DB table, worker job, dashboard change, or
  production/VPS wiring of any kind. This package is invoked manually
  (or by an external scheduler outside this repo) as a CLI tool.
- No trading action, strategy enable/disable, or any write to
  canonical MarketHunter state. Output is local report artifacts only.
- No fabricated metrics: acquisition fails closed on a non-200
  response or invalid JSON; analysis fails closed when required
  fields are absent from the source payload rather than defaulting
  to zero.
"""
