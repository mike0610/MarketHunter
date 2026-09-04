# MarketHunter Autonomous Market Automation v1

Status: implementation contract for staged paper-only automation.

## Goal

MarketHunter must operate autonomously in PAPER / SIMULATION mode.

A scanner signal is an event that starts a governed workflow. It is never, by itself, a BUY/SELL/LONG/SHORT.

## Active Trading loop

1. Discovery scanner runs every 30 minutes.
2. Scanner evaluates only approved, deterministic setup families.
3. Candidate must contain enough structured evidence to validate a complete formation/structure.
4. Strategy validation must produce a deterministic entry trigger and structural invalidation.
5. Risk / money management calculates position size from the configured risk budget and stop distance.
6. A canonical TradingDecision is written to the durable trading decision inbox.
7. Experiment1 runtime independently:
   - re-checks fresh execution evidence;
   - waits for or cancels an unsatisfied/invalidated trigger;
   - executes PAPER fills only;
   - manages SL/TP and position lifecycle;
   - records P&L, drawdown and provenance.
8. No manual operator is required for ordinary paper-trading lifecycle.
9. If a strategy cannot be expressed as deterministic rules, it is research-only and must not emit a TradingDecision.

## Investments loop

1. Investment discovery produces a structured investment signal.
2. Cheap deterministic screen decides whether the signal is:
   - automatically decidable by an already-approved investment rule;
   - or requires GIL deep research.
3. For a known approved rule, the system may produce a PAPER GilDecision automatically within portfolio/risk limits.
4. For deep-research cases:
   - MarketHunter creates a research request;
   - GIL performs thesis, valuation, owner-economics, downside, executability and portfolio-fit analysis;
   - GIL returns a canonical GilDecision or WAIT/HOLD/REJECT result;
   - MarketHunter executes/monitors only the machine decision.
5. MarketHunter never manufactures an investment thesis or converts CANDIDATE/WATCH into BUY.

## Safety boundaries

- PAPER / SIMULATION ONLY.
- No live broker order submission.
- Active Trading requires independent execution-grade market evidence.
- Investment reference-close fills remain explicitly labeled simulated reference-close fills.
- Idempotent decision IDs are mandatory.
- Duplicate signals/decisions must not create duplicate fills.
- Any missing evidence, stale evidence, unsupported instrument, malformed decision or broken structure fails closed.
- Strategy rules, risk limits and account boundaries are versioned and auditable.

## Staged delivery

### Stage 1 - cadence and contract

- Discovery cadence: 30 minutes.
- Existing Experiment1 execution runtime remains independent and may keep a tighter cadence.
- Preserve separate TradingDecision and GilDecision boundaries.

### Stage 2 - real discovery evidence source

Replace the current fail-closed `build_ibkr_universe_source() -> None` boundary with a real, testable non-crypto universe/market-data source. Do not fake an IBKR session. If IBKR cannot be used safely, implement a provider adapter behind the existing `AsyncIbkrUniverseSource` protocol or an explicitly renamed generic protocol.

Acceptance:
- one real scan cycle sees real instruments;
- OHLCV/liquidity timestamps are preserved;
- stale/missing data produces DATA_FAIL, not candidates;
- no order is created by scanner code.

### Stage 3 - structure-to-decision engine

Add a deterministic Strategy Automation layer between Trading Candidate Queue and TradingDecision.

Acceptance:
- only complete approved formations can emit decisions;
- each decision includes entry trigger, structural stop/invalidation, target/exit rule, risk budget and provenance;
- no arbitrary prose is interpreted as an entry rule;
- no candidate may bypass the TradingDecision inbox.

### Stage 4 - autonomous order lifecycle

Add explicit pre-fill invalidation/cancellation semantics for pending TradingDecisions and verify SL/TP management after fill.

Acceptance:
- trigger can expire or cancel when structure is invalidated before entry;
- risk budget cannot be exceeded;
- Futures leverage remains capped at 3x;
- Spot remains 1x;
- duplicate decisions remain idempotent;
- paper fill always uses fresh execution evidence.

### Stage 5 - investment discovery router

Implement investment signal discovery and a deterministic router:
- approved simple rule -> paper GilDecision;
- deep-analysis required -> GIL research request;
- no evidence -> WAIT;
- rejected thesis -> no order.

Acceptance:
- MarketHunter never invents BUY;
- GIL provenance survives into decision, fill, position and reports;
- Defensive/Balanced/Growth ledgers remain independent.

### Stage 6 - autonomous reporting and health

Expose automation health:
- last scanner run;
- instruments scanned;
- candidates;
- decisions emitted;
- waiting/cancelled/blocked decisions;
- fills;
- open positions;
- risk usage;
- evidence failures;
- next scheduled cycle.

The Product Owner should need to intervene only for:
- changing strategy/risk policy;
- approving a major phase change;
- deep investment research when requested;
- legal/safety issues;
- enabling real-money execution in a future separately-approved phase.
