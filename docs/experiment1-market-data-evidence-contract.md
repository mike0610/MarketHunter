# Experiment 1 Market Data Evidence Contract v1

The generic, provider-independent foundation for non-crypto (and, in principle,
any) market data evidence — built before any provider decision, so it is
never coupled to Tiingo, Alpaca, or any other specific integration. A bare
price (`experiment1.models.MarketQuote`) is never, on its own, sufficient
evidence for a paper fill or a mark; this contract adds the richer record a
real provider adapter is expected to populate, plus the single deterministic,
fail-closed judgment of whether that evidence is good enough to execute
against versus merely good enough to value a position against.

## `MarketDataEvidence` (`experiment1/models.py`)

A frozen dataclass carrying: `provider`, `instrument` (MarketHunter's own
canonical symbol), `provider_symbol` (the provider's raw ticker, preserved
verbatim), `exchange` (listing/venue), `currency` (ISO-4217-style 3-letter
uppercase code), `price`, `price_type` (`TRADE`/`BID`/`ASK`/`MID`/`EOD_CLOSE`/
`DERIVED`), `source_timestamp` (UTC, the provider's own observation time),
`receive_timestamp` (UTC, when this process observed it), `session_state`
(`PRE_MARKET`/`REGULAR`/`POST_MARKET`/`CLOSED`), `mode` (`REALTIME`/`DELAYED`/
`EOD`/`DERIVED`), and `source_reference` (opaque provenance). It only enforces
well-formedness (non-blank identity fields, aware timestamps, a positive
price, a plausible currency code) — it never judges freshness or whether it
matches what a caller expected.

## `evaluate_market_data_evidence` (`experiment1/market_data_evidence.py`)

The single place the fail-closed judgment lives — pure, deterministic, no I/O.
Given a `MarketDataEvidence | None` plus an expected instrument/currency/
(optional) exchange and two freshness bounds, it returns an
`EvidenceEvaluation`:

- `validation_status`: `VALID` / `STALE` / `MISSING` / `INSTRUMENT_MISMATCH` /
  `CURRENCY_MISMATCH` / `LISTING_MISMATCH`.
- `valuation_evidence_ok`: **True whenever `validation_status` is `VALID`** —
  the broad bar. A matched, not-too-stale mark; delayed/EOD/derived modes and
  any session state are all still acceptable for valuing a position.
- `execution_evidence_ok`: True only when, additionally, the evidence is
  within the (normally tighter) `execution_max_age`, its `price_type` is a
  live `TRADE`/`BID`/`ASK`/`MID` observation (never `EOD_CLOSE`/`DERIVED`),
  its `mode` is `REALTIME`, and `session_state` is `REGULAR`. A reference or
  derived feed, or one outside regular trading hours, can never satisfy
  execution-grade evidence no matter how fresh it is.

`MISSING`/`STALE`/a mismatch always yields **both** flags `False` — there is
no case where mismatched or absent evidence is good enough to value a
position either.

## `EvidenceGuardedQuoteSource` (`experiment1/market_data_evidence.py`)

Bridges any `AsyncEvidenceSource` (`async def evidence_for(instrument) ->
MarketDataEvidence | None`) into the existing `AsyncQuoteSource` contract
(`quote_for(intent) -> MarketQuote | None`) that `run_market_cycle` and
`run_mtm_cycle` already consume unmodified — so a future concrete provider
adapter plugs directly into `MultiAssetQuoteSource`'s provider mapping
(`experiment1/market_data_providers.py`) with **no change to either cycle
function**. `grade` (`EvidenceGrade.EXECUTION` / `EvidenceGrade.VALUATION`)
selects which of the two gates above this instance enforces; a caller needing
both for the same instrument constructs two instances around the same
underlying evidence source — mirroring how `FreshnessGuardedQuoteSource`
already composes around any `AsyncQuoteSource` without duplicating the fetch
itself. It never fabricates a price: `quote_for` returns `None` (the existing
`WAITING_EVIDENCE` contract) whenever the evidence doesn't clear this
instance's grade.

## What this closes, and what remains

This is foundation only — no provider integration, no credentials, no
runtime wiring. The existing Binance crypto path
(`experiment1/market_source.py`, `experiment1/market_data_providers.py`) and
`tools/experiment1_runtime/runtime.py`'s scheduler are untouched; this module
adds nothing that either currently calls. A concrete provider adapter (the
next bounded slice — currently pointed at Alpaca SIP / Algo Trader Plus for
US stocks/ETF execution-grade evidence, per the latest GIL research
direction) is expected to implement `AsyncEvidenceSource`, construct
`MarketDataEvidence` from its own raw response, and be wired into the
scheduler via `EvidenceGuardedQuoteSource` + `MultiAssetQuoteSource` — no
change to this contract required.
