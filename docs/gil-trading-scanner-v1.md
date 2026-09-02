# GIL Trading Scanner v1 — First Minimal Bounded Slice

`trading_scanner/`. Discovers, classifies, and persists non-crypto (US stocks/liquid
ETFs) trading setups for GIL's review. **This package never decides LONG/SHORT/WAIT
and never creates a paper `OrderIntent`** — see `tests/test_trading_scanner_boundary.py`
for a structural (AST-level, not just behavioral) proof that no module in this
package imports `experiment1.engine`/`experiment1.gil_decision`/`experiment1.runtime`
or references `submit_intent`/`execute_pending`/`ingest_gil_decision`/`OrderIntent`
by name.

## Scope of this PR — deliberately reduced

The original dispatch asked for a 7-part slice (universe resolver, liquidity gate,
all 3 v1 setup families, persistent queue, read API, scheduler hook, tests). Per
explicit direct guidance mid-cycle to keep changes minimal, this PR ships a smaller
vertical slice instead:

**Included:** domain models (`models.py`), the IBKR-universe boundary
(`universe.py`), the liquidity/executability gate (`gates.py`), exactly one of the
three setup families — `MOMENTUM_RELATIVE_STRENGTH` (`setups.py`) — a persistent
SQLite-backed queue (`store.py`), and the orchestration wiring them together
(`scan.py`), plus the structural execution-boundary proof.

**Deliberately deferred to a follow-up slice:** the other two setup families
(`ABNORMAL_VOLUME_CATALYST`, `BREAKOUT_OR_PULLBACK_IN_TREND`), a read API
(`api/trading_scanner_api.py`), and a scheduler/systemd runtime hook. None of the
deferred pieces are referenced anywhere in this PR's code — they are pure follow-up
work, not partially-built.

## The IBKR boundary — genuinely different from Alpaca's

`build_ibkr_universe_source()` always returns `None` today. This is *not* a
credential-env-var check like `experiment1/alpaca_sip_evidence.py`'s or
`experiment1/gil_slack_adapter.py`'s `build_*` functions (both return a real client
the moment an env var is set) — IBKR's API requires an actively-running,
already-logged-in TWS/IB Gateway process this session cannot reach, verify, or
safely start, plus a funded/entitled account. No real client implementation (and no
new `ib_insync`/`ibapi` dependency) is attempted in this PR — building one with no
way to test it against a genuine session would risk exactly the "fake a live proof"
outcome the dispatch explicitly forbade. **Terminal state for live IBKR proof:
`BLOCKED-IBKR-SESSION`.**

Every other module (gates, the wired setup family, the store, the scan
orchestration) is fully built and fully tested against `AsyncIbkrUniverseSource`
fakes, so a future slice can supply a real implementation with zero change
anywhere else in this package.

## Domain contract

`TradingCandidate` carries every field the dispatch's output contract required:
IBKR identity (`conid`/`symbol`/`sec_type`/`exchange`/`currency`), `setup_family`,
an explainable `reason_stack` (never a magic score), optional `catalyst` evidence
(required, never inferred — a setup needing one simply cannot classify without it),
`liquidity`/`volatility` context, `evidence_status`, `eligible`, an
`invalidation_reference` only when the setup itself deterministically defines one,
`reject_reason` (required exactly for `INELIGIBLE`/`DATA_FAIL`/`EXECUTION_BLOCKED`/
`REJECTED`, forbidden for `CANDIDATE`/`WATCH`), `discovered_at`/`scan_cycle_id`, and
a deterministic `dedupe_key` (`conid:setup_family:scan_cycle_id`) — never a randomly
generated id, so re-running the same scan cycle never duplicates a row.

`MOMENTUM_RELATIVE_STRENGTH`'s v1 rule: close above its own 20-day SMA, and the
20-day SMA above the 50-day SMA — a standard, explainable trend-alignment check, not
an invented indicator. Returns `None` (→ `DATA_FAIL`) rather than a guessed result
when fewer than 50 closes are available.

## What this does not do

No live IBKR connection, no paid subscription, no OrderIntent, no LONG/SHORT/WAIT
decision, no fabricated entry/stop/target/RR (invalidation references are only ever
the setup's own deterministic structural level — GIL owns actual stop/target/RR/
sizing/thesis). No architecture beyond this bounded package.
