# Alpaca SIP Read-Only Execution-Evidence Adapter

`experiment1/alpaca_sip_evidence.py` — the first concrete US stocks/ETF
execution-grade provider behind the generic Market Data Evidence Contract v1
(`experiment1/market_data_evidence.py`, `experiment1/models.MarketDataEvidence`),
per the latest GIL research direction: Alpaca SIP / Algo Trader Plus supersedes
the earlier Tiingo direction for execution evidence (Tiingo remains a
valuation/trigger-grade candidate elsewhere, per the same research checkpoint).

## What it is

`AlpacaSipEvidenceSource` implements `AsyncEvidenceSource.evidence_for(instrument)`
exactly as any other provider would — nothing in the generic contract changed to
accommodate it. It calls Alpaca's read-only Market Data API
(`GET https://data.alpaca.markets/v2/stocks/{symbol}/quotes/latest?feed=sip`)
and normalizes the response into a `MarketDataEvidence`:

- `provider` = `"ALPACA_SIP"`, `exchange` = `"ALPACA_SIP"` (SIP consolidates every
  US exchange into one feed — no single-exchange listing code is meaningful for a
  SIP quote).
- `provider_symbol` = Alpaca's own echoed symbol (falls back to the requested
  instrument if omitted); `instrument` = the requested canonical MarketHunter
  symbol, kept structurally distinct.
- `currency` = `"USD"` (hardcoded — Alpaca US equities are always USD).
- `price` = the mid of bid/ask (`(bp + ap) / 2`), `price_type` = `MID`. The
  evidence contract carries one price field; since a quote isn't yet tied to a
  trade direction at lookup time, a symmetric mid is the only non-biased choice
  without inventing side-aware fields the contract doesn't have.
- `source_timestamp` = Alpaca's own `t` field (RFC3339, nanosecond precision —
  truncated to microseconds since Python's `datetime.fromisoformat` doesn't
  support finer, an honest precision loss, not a fabrication).
- `session_state` = derived from NYSE/Nasdaq's own well-established regular
  session hours (9:30–16:00 ET) and standard pre/post-market windows, computed
  in `America/New_York` local time (correctly DST-aware via `zoneinfo`) — **not**
  read from Alpaca's market-clock endpoint, which lives on the Trading API host
  this module never touches (see boundary below). Does not account for market
  holidays — a documented gap, not silently hidden.
- `mode` = `REALTIME`.

## Fail-closed, exactly as dispatched

Every acquisition failure returns `None` (the existing `WAITING_EVIDENCE`
contract) rather than raising or guessing: a network/transport error, any
non-200 response — including a `403` for missing SIP entitlement/subscription
and a `404` for an unknown symbol — malformed JSON, a missing or non-positive
bid/ask, or an unparseable timestamp. None of these are distinguished further
than "evidence not obtainable this cycle"; a `403` specifically is never
retried against a cheaper feed (that would silently downgrade evidence quality
without saying so).

## Hard boundaries

- **Read-only Market Data API only.** `data.alpaca.markets` is the only host
  this module ever calls. Alpaca's market-clock endpoint (`/v2/clock`) lives on
  the *Trading* API host (`api.alpaca.markets`/`paper-api.alpaca.markets`) —
  this module deliberately never calls it, deriving session state from public
  market-structure facts instead (see above), so there is no ambiguity about
  touching a trading endpoint at all.
- **No Alpaca order/trading endpoint is ever called** — this module only
  produces `MarketDataEvidence`; nothing here calls `submit_intent`/
  `execute_pending`.
- **No fabricated quotes, ever.**
- **Credentials are secret/env driven only** — `EXPERIMENT1_ALPACA_API_KEY_ID`
  / `EXPERIMENT1_ALPACA_API_SECRET_KEY`, never logged, never committed (see
  `deploy/systemd/experiment1-runtime.env.example`).
- **Integration alone never creates a fill.** This PR does not wire
  `AlpacaSipEvidenceSource` into `tools/experiment1_runtime/runtime.py`'s
  scheduler or `MultiAssetQuoteSource`'s provider mapping — doing so would also
  require solving non-crypto symbol classification (there is no evidence-backed
  ticker-to-`AssetClass` taxonomy anywhere in this repository — the same gap
  `market_data_providers.py`'s own `AssetClass` docstring already documents),
  which is outside this bounded adapter's scope. The Binance crypto path
  (`experiment1/market_source.py`, `build_quote_source()`) is completely
  untouched — verified with a regression test.

## Credential boundary — checked, not assumed

**Product Owner has NOT authorized any paid Alpaca subscription/account
purchase.** `build_alpaca_sip_evidence_source()` returns `None` — the same
fail-closed-by-omission pattern already used for the Slack GIL adapter and
every unregistered non-crypto asset class — unless both
`EXPERIMENT1_ALPACA_API_KEY_ID` and `EXPERIMENT1_ALPACA_API_SECRET_KEY` are
genuinely set. Until that changes, this module ships fully built and fully
tested against a fake HTTP transport (`httpx.MockTransport`); it has never
been exercised against a live Alpaca account, and this PR does not claim
otherwise. **Terminal status for live provider proof: NEEDS-CREDENTIALS.**
