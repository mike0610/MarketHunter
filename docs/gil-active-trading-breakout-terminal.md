# GIL Active Trading: Breakout LONG + SMA20 terminal state

Status: **CANONICAL / TERMINAL**  
Owner: **GIL / Active Trading (NON-CRYPTO)**  
Date: 2026-09-08

## Terminal verdict

**REJECTED**

This exact frozen strategy version failed the GIL promotion gate and must not be admitted to the governed paper-strategy manifest.

## Frozen contract evaluated

- direction: LONG
- formation: SMA20 > SMA50
- latest completed daily close > highest completed daily close of the previous 20 trading bars
- conditional trigger: signal-bar high, upward crossing
- no same-signal-bar fill
- expiry: 3 trading bars
- pre-fill invalidation: breakout level
- post-fill structural stop: breakout level
- exit: first completed daily close <= SMA20
- universal fixed 3R exit: REJECTED
- universe: SPY, QQQ, AAPL, MSFT, NVDA
- no parameter tuning
- no new exit hypothesis
- no universe expansion during this gate
- ZERO broker / ZERO IBKR / ZERO live money

## Durable evidence

Research object:

`GIL-BREAKOUT-LONG-SMA20-PROMOTION-GATE-001`

GitHub Actions:

- Research Execution Harness run: `34201075456`
- Harness run number: `213`
- Artifact: `10045820997`
- Harness terminal: `EVIDENCE_READY`
- Research verdict: `REJECTED`

Aggregate OOS:

- trades: 196
- expectancy: +0.2282828886 R
- Profit Factor: 1.2417104167
- stressed-cost expectancy: +0.0781139389 R
- stressed-cost PF: 1.0731572975
- deterministic reproduction: PASS

## Why promotion failed

The GIL promotion rule required all of the following to survive:

- OOS net expectancy > 0 after realistic costs
- PF > 1 after costs
- leave-one-symbol-out must not collapse expectancy sign
- no obvious single-period/regime dependence
- execution assumptions must be feasible and forward-only
- deterministic reproduction must pass

The exact frozen contract failed robustness despite positive aggregate OOS.

Leave-one-symbol-out without MSFT:

- expectancy: -0.4235608625 R
- PF: 0.5749887218

Leave-2025-out:

- expectancy: -0.4393497190 R
- PF: 0.5567046756

Therefore `PROMOTION-ELIGIBLE` is prohibited. `BLOCKED-EVIDENCE` is also incorrect because the required evidence exists and resolves the gate. The correct terminal state is `REJECTED`.

## Negative knowledge

Additional diagnostics from the same immutable artifact:

- high-volatility subset: expectancy +0.3649573545 R, PF 1.3551065291
- false-breakout subset: expectancy -1.3882180795 R, PF 0.0
- sharp-reversal subset: expectancy -1.3102797466 R, PF 0.0

These are preserved as negative knowledge. They are **not** permission to optimize filters after observing the result.

## Do not repeat

Future successors must not:

- restart this strategy family from zero;
- rerun the same frozen contract just to seek a different result;
- cherry-pick MSFT, 2025, or any other favorable subset after seeing outcomes;
- add a new exit or parameter tweak under the same research object;
- infer that positive aggregate OOS overrides failed robustness gates;
- promote this exact version to paper runtime;
- mix this GIL non-crypto research line with STRATEGY LAB Crypto.

## Reopen condition

Reopen only as a genuinely new, pre-specified hypothesis with a new research object and explicit rationale that does not arise from post-outcome cherry-picking.

The rejected version, artifact, terminal verdict, and failure reasons must remain preserved.

## Successor recovery rule

Before creating or rerunning GIL Active Trading research, recover state in this order:

1. Notion for canonical ownership/governance/mandates.
2. GitHub for code, tests, research jobs, issue terminals, workflow runs, artifacts and manifests.
3. MarketHunter runtime/storage for actual queues, fills, positions, ledgers and statistics.
4. Slack for coordination/handoffs only, not as automatic source of truth.

A failed or empty search in one source does **not** prove that state is absent. Continue through the durable sources before declaring `BLOCKED-EVIDENCE` or creating replacement work.

## GIL Active Trading successor recovery map

When recovering the next non-crypto GIL Active Trading lineage, do not assume master contains the complete historical research state.

For the current `MOMENTUM_RELATIVE_STRENGTH -> LONG` recovery:

- first inspect GIL-specific durable branches and historical research evidence;
- the branch `fix/gil-blocked-strategy-contract-status` is a relevant GIL-specific recovery source because it contains the blocked-strategy-contract status work around GIL scanner / research / risk-mm / stage10;
- do **not** use `research-cross-sectional-momentum-001` as GIL evidence: its research jobs are `SL-VAL-...` and belong to STRATEGY LAB, not GIL;
- if a source name contains momentum/relative-strength but ownership is ambiguous, verify owner/domain before reusing any formation, universe, split, entry, exit, or terminal status;
- a missing code-search hit on master is not evidence that the lineage never existed. Search relevant branches, research jobs, workflow runs/artifacts, then runtime/storage before declaring evidence absent.

This recovery path exists specifically to prevent future successors from mixing GIL Active Trading with STRATEGY LAB or rebuilding already-completed work from zero.

## Recovery gap: MOMENTUM_RELATIVE_STRENGTH -> LONG

Current recovery finding for the next GIL Active Trading lineage:

- `MOMENTUM_RELATIVE_STRENGTH` is durably implemented as a GIL non-crypto scanner setup-family.
- Confirmed formation semantics: close > SMA20, SMA20 > SMA50, with an optional benchmark-relative-strength leg only when benchmark evidence exists.
- The setup was designed for GIL review and explicitly did not create paper orders by itself.
- No durable GitHub/Notion/Slack research object was recovered that proves a prior formal `BLOCKED-EVIDENCE` terminal specifically for this lineage.
- No recoverable prior object currently proves a previously frozen trigger, expiry, complete exit contract, historical universe/split, or exact terminal reasoning for this lineage.
- Therefore future successors must **not invent** those missing pieces and must **not claim** they were previously validated.

Working interpretation:

`MOMENTUM_RELATIVE_STRENGTH -> LONG` should be treated as an existing GIL idea/setup lineage with incomplete executable-strategy formalization. The missing part is the executable contract layer, especially conditional-entry semantics. Recovery should preserve the confirmed formation and ownership boundary, then pre-specify any new trigger/invalidation/expiry/exit logic before outcome inspection.

Searches already performed during recovery:

- master code search for `MOMENTUM_RELATIVE_STRENGTH`, `MOMENTUM-RS`, `BLOCKED-EVIDENCE`;
- GIL-specific branch search;
- commit history for `momentum`, `relative strength`, and blocked strategy contract work;
- Notion searches for `SMA20 SMA50`, `relative strength`, `conditional entry`, `momentum LONG`;
- Slack searches for exact-name and concept-level variants;
- branch-level inspection that distinguished GIL evidence from STRATEGY LAB `SL-VAL-...` evidence.

Do not repeat this archaeology unless a genuinely new durable source becomes available.
