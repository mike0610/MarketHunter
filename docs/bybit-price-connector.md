# Bybit Public Price Connector — Cross-Venue Data Unblocker

`exchange/bybit_client.py`. A narrow, free, public, read-only price connector —
the smallest bounded slice that unblocks the already-requested Quiet-RV
cross-venue PRICE portability research object, under the current standing
"no paid services" constraint. It requires no API key, no account, and no
payment: Bybit's V5 kline endpoint is public market data.

## Why Bybit, and why this narrow

The prior venue-dependence research cycle established that **zero** cross-venue
price connectors or historical data existed anywhere in this repository — every
candidate strategy's evidence is Binance-only, making it structurally
impossible to distinguish real market edge from Binance-specific edge. This
module is exactly, and only, the missing piece that inventory identified:
one read-only public venue connector, price data only. No funding rate, basis,
or open-interest data is requested or substituted anywhere here — the prior
research packet was explicit that those must stay venue-specific and never be
silently substituted across venues, and this slice doesn't touch them at all.

## What it is

- **`BybitClient`** — a thin, real HTTP client (`GET https://api.bybit.com/v5/market/kline`),
  mirroring `exchange/binance_client.py`'s `BinanceClient` exactly: no
  authentication, no order/trading endpoint, matching this repo's existing
  convention that the raw HTTP layer itself carries no direct test coverage.
- **`BybitPerpetualCandle`** — the normalized record, UTC-aware, with explicit
  provenance (`venue`, `category`, raw `symbol`). Deliberately **not**
  `models.candle.Candle`: Bybit's public kline response doesn't include a trade
  count or a taker-buy volume breakdown the way Binance's does, and fabricating
  those as `0` would misrepresent "not provided by this venue" as "genuinely
  zero." This module defines its own honest, minimal shape instead — no
  existing model was touched.
- **`BybitPerpetualCandleLoader`** — the composable, fully-testable layer,
  mirroring `experiment1.market_source.BinanceExperiment1QuoteSource`'s own
  injectable-client pattern exactly (a fake client double in tests, never an
  HTTP-level mock or a live call). This is what every test in
  `tests/test_bybit_client.py` actually exercises.
- **`detect_gaps_and_duplicates`** — explicit missing/duplicate detection over
  one fetched, ascending-sorted batch: any consecutive gap wider than the
  declared interval is reported as a `(before, after)` window, and any repeated
  timestamp is reported as a duplicate. Never interpolates a missing candle,
  never silently drops a duplicate. An empty report is itself meaningful
  evidence the batch is clean.

## Real Bybit-specific details handled correctly

- Bybit's V5 API returns **HTTP 200 even for many logical errors** (bad symbol,
  bad interval), embedding the real failure in a `retCode`/`retMsg` pair in the
  response body — `BaseClient.get()`'s own `raise_for_status()` only catches
  genuine HTTP-level failures, so this module checks `retCode` explicitly and
  raises `BybitAPIError` rather than silently returning a guessed/partial
  result.
- Bybit returns kline rows **newest-first** — `BybitPerpetualCandleLoader`
  always sorts ascending before returning, never leaving ordering implicit for
  a downstream consumer (including `detect_gaps_and_duplicates`, which assumes
  and verifies ascending order).
- The endpoint's documented cap of 1000 rows per request is enforced with a
  `ValueError`, not silently truncated.

## What this does not do

Not wired into any production runtime, scheduler, or live trading path.
`MultiAssetQuoteSource`'s execution-grade provider mapping
(`experiment1/market_data_providers.py`) is completely untouched — this is a
research-only price connector, not an execution-evidence provider, and makes
no `EXECUTION_EVIDENCE_OK` claim of any kind. No funding/OI data, no live
orders, no real capital, no scraping (this is Bybit's own public, documented
REST API), no broad architecture change — one new file, zero existing files
touched.

## What it unblocks next

With this connector available, the actual Quiet-RV cross-venue PRICE
portability comparison (frozen signal timestamps/rules replayed against
synchronized Binance vs. Bybit 4h price history) becomes executable research —
not performed in this PR, since that is the strategy-research object itself,
not the data-connector foundation it depends on.
