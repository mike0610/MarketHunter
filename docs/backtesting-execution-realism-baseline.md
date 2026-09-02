# Execution Realism Baseline v1

`backtesting/execution_policy.py`. The smallest execution-realism layer requested
by Strategy Lab, kept explicitly separate from `StrategyVersion` (alpha/signal)
logic — this module never generates a signal, never mutates a strategy's rules,
and never retroactively changes a backtest's own verdict. It only decides how
an already-chosen entry attempt would actually have been filled.

## Required separation

- **StrategyVersion** — alpha/signal logic, entirely outside this module.
- **ExecutionPolicyVersion** (this module) — how an already-approved order would
  be attempted: `ExecutionMode.AGGRESSIVE_TAKER` or `ExecutionMode.PASSIVE_MAKER_SIMPLE`.
- Execution outcome never mutates strategy rules or a signal's own verdict.

## The two baseline modes

**`AGGRESSIVE_TAKER`** matches `backtesting.trade_simulator.TradeSimulator`'s own
existing, already-tested assumption exactly: a requested entry always fills,
adjusted by adverse slippage. This is not new logic — it is today's existing
default behavior, now explicitly labeled and measured through
`summarize_execution_policy` rather than silently assumed. `FULL_FILL` here
reflects `TradeSimulator`'s own existing assumption, not a verified guarantee
against real depth evidence (none exists in this repository).

**`PASSIVE_MAKER_SIMPLE`** never treats touch as fill. The only OHLC-derivable
rule that doesn't fabricate queue position or liquidity: a resting limit price
is filled only if the candle's range genuinely **traded through** it (a strict
inequality — an exact touch at the boundary is `NO_FILL`, since a bar that only
touches a level offers no real evidence a resting order ahead of ours in the
queue would have let ours fill at all). A maker fill never incurs the adverse
*entry* slippage a taker fill does — the exit leg (a market action once
stop/target is breached) still does, via the same `resolve_exit()` logic both
modes share. A maker/taker fee-rate differential is **not** modeled — the same
`fee_bps_per_side` is reused for both, a documented simplification, never a
fabricated fee schedule.

## `FillOutcome`

`FULL_FILL` / `NO_FILL` are genuinely produced by this OHLC-only baseline.
**`PARTIAL_FILL` is never returned** — it exists as a structurally-supported case
for a *future* execution policy backed by L2/event-replay evidence. Queue-aware
partial-fill probability cannot be derived from OHLC data alone (no book depth,
no queue position exists anywhere in this repository — see the venue-dependence
research inventory from the prior cycle), so this module reports that as a real
gap rather than inventing a number. `EXECUTION_BLOCKED` means the required
candle evidence was missing.

A `NO_FILL` is a missed-opportunity counterfactual only — `simulation` stays
`None`, and `summarize_execution_policy` never counts it toward realized P&L.

## `resolve_exit()` — a pure, behavior-preserving extraction

`backtesting/trade_simulator.py`'s stop-first/target-first ambiguity scan was
extracted, unchanged, into a standalone `resolve_exit()` function so both
`TradeSimulator.long/short` **and** this module's own entry-fill/fee model
(which differs for a maker fill) can reuse the exact same, already-tested exit
logic rather than duplicating it. `TradeSimulator.long/short` now delegate to
it — behavior is identical to before this extraction (verified in
`tests/test_backtesting_execution_policy.py`'s `ResolveExitParityTests` and a
direct numeric parity check against `TradeSimulator` in
`AggressiveTakerEntryTests`). **The existing simulator remains the simple
comparator — nothing about it was deleted or behaviorally changed.**

## `compute_post_fill_markout`

A predeclared-horizon forward price check — execution-**quality** evidence
only, per the dispatch's own "not alpha" framing. Never fed back into a
strategy's signal/rules. Returns `None` (not a fabricated partial-horizon
number) when fewer than `horizon_bars` candles remain.

## What this does not, and cannot yet, do

**None of the specific candidates named in the dispatch — Quiet-RV, Trend
Pullback BTC/ETH, or the Turtle Soup/pullback/level-reclaim limit-entry family —
exist as runnable signal-generation code in this repository.** A full-repo
search (`git grep -niE "quiet[-_ ]?rv"` and equivalents) returns zero matches;
`strategies/` contains a different set of real, working pattern strategies
(`breaker.py`, `breakout.py`, `choch.py`, `compression.py`, `daily_levels.py`,
`false_breakout.py`, `fvg.py`, `liquidity_pool.py`, `liquidity_sweep.py`,
`mitigation.py`, `order_block.py`, `premium_discount.py`) that don't obviously
correspond 1:1 to the dispatch's named candidates — no mapping was assumed or
invented. Applying this baseline to any of the dispatch's specifically-named
candidates is therefore not executable in this repository today; it either
requires those strategies to be implemented here first, or requires running
this module against MarketHunter's own existing strategy library instead
(the recommended next bounded step, not performed in this PR).

No committed historical candle data exists either (see the prior venue-
dependence research cycle) — a live run of this baseline against any real
strategy would need a fresh `BinanceClient.get_klines()` fetch at run time.
