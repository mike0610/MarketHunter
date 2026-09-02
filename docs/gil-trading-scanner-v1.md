# GIL Trading Scanner v1

`trading_scanner/`. Discovers, classifies, and persists non-crypto (US stocks/liquid
ETFs) trading setups for GIL's review. **This package never decides LONG/SHORT/WAIT
and never creates a paper `OrderIntent`** — see `tests/test_trading_scanner_boundary.py`
for a structural (AST-level, not just behavioral) proof that no module in this
package imports `experiment1.engine`/`experiment1.gil_decision`/`experiment1.runtime`
or references `submit_intent`/`execute_pending`/`ingest_gil_decision`/`OrderIntent`
by name.

## History — built across two passes on the same PR

This PR's first commit shipped a deliberately reduced first slice (models, the IBKR
boundary, the liquidity gate, one setup family, the queue, and the orchestration) per
explicit direct guidance mid-cycle to keep changes minimal. A follow-up dispatch then
asked to apply the remaining delta **in-place on this same branch** rather than open a
parallel implementation — this doc now describes the complete v1 slice both commits
together produced.

## What v1 now includes

- **Domain models** (`models.py`) — `TradingCandidate` carries every output-contract
  field the dispatch required: IBKR identity (`conid`/`symbol`/`sec_type`/`exchange`/
  `currency`, plus `restricted` provenance on `IbkrContract`), `setup_family`, an
  explainable `reason_stack` (never a magic score), optional required-not-inferred
  `catalyst` evidence, `liquidity`/`volatility` context, `evidence_status`,
  `eligible`, an `invalidation_reference` only where a setup deterministically
  defines one, `reject_reason` (required exactly for the four negative terminal
  states, forbidden for `CANDIDATE`/`WATCH`), full scan-cycle provenance, and a
  deterministic `dedupe_key` (`conid:setup_family:scan_cycle_id`) — never a random
  id, so re-running the same cycle never duplicates a row.
- **The IBKR-universe boundary** (`universe.py`) — injectable
  `AsyncIbkrUniverseSource` Protocol (`resolve_universe`/`market_data_for`/
  `liquidity_context_for`/`catalyst_for`). `build_ibkr_universe_source()` always
  returns `None` today — see the credential-boundary section below.
- **The liquidity/executability gate** (`gates.py`) — conservative, **configurable**
  `LiquidityThresholds` (min price, min average-daily-dollar-volume), regular-session-
  only, and a restricted contract is never eligible regardless of liquidity.
- **All three v1 setup families** (`setups.py`), each a pure, deterministic
  classifier over already-fetched OHLCV history:
  - `MOMENTUM_RELATIVE_STRENGTH` — close above its own 20-day SMA, and the 20-day
    SMA above the 50-day SMA. **Relative-strength aware where evidence allows**: an
    optional `benchmark` market-data series adds a genuine relative-strength leg
    (the symbol's own trailing N-bar return must exceed the benchmark's over the
    same window) — additive only; absent a benchmark, or with insufficient benchmark
    history, the rule behaves exactly as the pure trend-alignment check, never
    fabricating a benchmark comparison that wasn't actually supplied.
  - `ABNORMAL_VOLUME_CATALYST` — today's volume ≥ 3× the prior 20-day average,
    **and** explicit catalyst evidence present. This repo has no news/filing feed of
    its own — `catalyst` is always caller-supplied; absent one, this family cannot
    match no matter how abnormal the volume is.
  - `BREAKOUT_OR_PULLBACK_IN_TREND` — requires the same established-trend context,
    then either a new N-day high (`BREAKOUT`) or a shallow retracement within a
    configurable band of the 20-day SMA (`PULLBACK`) — both sub-cases reported
    explicitly in `reason_stack`.
  Every classifier returns `None` (→ `DATA_FAIL`) rather than a guessed result when
  there isn't enough history to compute its own rule.
- **A persistent SQLite-backed Trading Candidate Queue** (`store.py`) — idempotent on
  `dedupe_key`, restart-safe, mirrors `Experiment1Engine`'s own connect-per-call
  pattern. An eligible contract produces **one row per setup family per cycle** (up
  to three); a gated-out or data-unavailable contract produces exactly one row (there
  is nothing family-specific to say about a contract the gate or data fetch already
  rejected outright).
- **The scan-cycle orchestration** (`scan.py`) — wires universe → gate → all three
  classifiers → persistence, with an optional per-cycle `benchmark_contract` resolved
  once and reused across every symbol, and configurable `liquidity_thresholds`.
- **A read-only API** (`api/trading_scanner_api.py`) — `GET /trading-scanner/candidates`
  (filterable by `queue_state`, `setup_family`, `symbol` — covers both "latest active
  candidates" and "historical rejected/data-fail states" through the same endpoint)
  and `GET /trading-scanner/candidates/{dedupe_key}`. Read-only: this router only ever
  calls `TradingScannerStore.list_candidates`/`get_candidate`.
- **A scheduler/runtime hook** (`tools/gil_trading_scanner_runtime/runtime.py` +
  matching `deploy/systemd/gil-trading-scanner-runtime.{service,timer,env.example}`,
  mirroring `tools/experiment1_runtime/runtime.py`'s own convention exactly). Today
  this is a safe no-op every run — it detects `build_ibkr_universe_source() is None`
  and exits cleanly (`EXIT_OK`) without ever touching the network, proving the wiring
  is correct and installable now, so a future slice supplying a real IBKR source
  needs zero changes here to start actually running scans.

## Hard boundary — proved structurally, not just claimed

`tests/test_trading_scanner_boundary.py` parses the real AST of every module in
`trading_scanner/` and asserts none imports `experiment1.engine`/`gil_decision`/
`runtime`, and none references `submit_intent`/`execute_pending`/
`ingest_gil_decision`/`OrderIntent` by name — anywhere, even in dead code. The
scanner cannot create a paper trade even in principle, not just "doesn't today."

## The IBKR boundary — different in kind from the Alpaca adapter

`build_ibkr_universe_source()` always returns `None`. This is **not** a
credential-env-var check like `experiment1/alpaca_sip_evidence.py`'s or
`experiment1/gil_slack_adapter.py`'s `build_*` functions (both return a real client
the instant an env var is set) — IBKR's API requires an actively-running,
already-logged-in TWS/IB Gateway process this session has no way to reach, verify, or
safely start, plus a funded/entitled account. No real client implementation, and no
new `ib_insync`/`ibapi` dependency, is attempted here — building one with no way to
test it against a genuine session would risk exactly the "fake a live proof" outcome
the dispatch explicitly forbade.

**Terminal state for live IBKR proof: `BLOCKED-IBKR-SESSION`.** Every other module
(gates, all three setup families, the store, the scan orchestration, the API, the
runtime hook) is fully built and fully tested against `AsyncIbkrUniverseSource`
fakes, so a real implementation can be supplied in a future slice with zero change
anywhere else in this package.

## What this does not do

No live IBKR connection, no paid subscription, no OrderIntent, no LONG/SHORT/WAIT
decision, no fabricated entry/stop/target/RR (invalidation references are only ever
the setup's own deterministic structural level — GIL owns actual stop/target/RR/
sizing/thesis). No UI, no Europe/global expansion, no options, no crypto, no ML/LLM
ranking. No architecture beyond this bounded package.
