# Experiment 1 GIL Decision Inbox

Canonical delivery target: `POST /experiment1/gil-decisions`.

This endpoint is a durable receipt only - it never submits an intent or executes a fill itself. Every accepted envelope is processed automatically, once per cycle, by `experiment1.gil_decision.drain_gil_decision_inbox`, which the recurring `tools/experiment1_runtime` scheduler runs before its market-fill step (see `deploy/systemd/README-experiment1-runtime.md`). There is no manual operator step and no parallel execution path - draining is the only way an inbox envelope ever becomes a canonical `OrderIntent`.

## Contract

`POST /experiment1/gil-decisions` accepts exactly the existing `GilDecision` semantics (see `experiment1/models.py`). GIL owns thesis, action, sizing, invalidation, and risk parameters; MarketHunter never manufactures or reinterprets any of them. `action` is restricted to the already-decided `DecisionAction` enum (`BUY`/`SELL`/`LONG`/`SHORT`/`WAIT`/`HOLD`) - a research state like `CANDIDATE` or `WATCH` is rejected by schema validation (`422`) before any domain logic runs, never coerced into a trade.

`decision_id` is the idempotency key. Resubmitting the identical payload under the same `decision_id` is a no-op that returns the already-recorded state; resubmitting a different payload under the same `decision_id` is a `409` conflict.

Exactly one of `quantity` (a fixed amount GIL already decided) or `sizing` (resolved from fresh evidence, see below) must be provided.

### Example request - immediate, fixed quantity (unchanged from the original contract)

```json
POST /experiment1/gil-decisions
{
  "decision_id": "gil-2026-09-01-001",
  "decided_at": "2026-09-01T12:00:00+00:00",
  "account": "FUTURES",
  "action": "LONG",
  "symbol": "BTCUSDT",
  "thesis": "breakout confirmed above resistance with volume expansion",
  "quantity": "0.05",
  "leverage": "2",
  "stop_loss": "58000",
  "take_profit": "65000"
}
```

### Example request - price buy-zone plus a max-notional tranche

No `quantity` up front - GIL specifies a price range and a notional cap; MarketHunter derives the exact quantity once a fresh quote lands inside the range.

```json
POST /experiment1/gil-decisions
{
  "decision_id": "gil-2026-09-01-croix-tranche-1",
  "decided_at": "2026-09-01T12:00:00+00:00",
  "account": "INVESTMENTS_GROWTH",
  "action": "BUY",
  "symbol": "CROXUSDT",
  "thesis": "first Growth tranche in the CROX buy zone",
  "trigger": {
    "trigger_type": "PRICE_IN_RANGE",
    "trigger_price_low": "115",
    "trigger_price_high": "120"
  },
  "sizing": {
    "mode": "MAX_NOTIONAL",
    "max_notional": "500"
  }
}
```

### Example request - Futures sized from a stop-distance risk budget

```json
POST /experiment1/gil-decisions
{
  "decision_id": "gil-2026-09-01-btc-risk-budget",
  "decided_at": "2026-09-01T12:00:00+00:00",
  "account": "FUTURES",
  "action": "LONG",
  "symbol": "BTCUSDT",
  "thesis": "BTC Futures long, sized to ~0.5% planned loss of the Futures ledger",
  "leverage": "2",
  "stop_loss": "58000",
  "sizing": {
    "mode": "RISK_BUDGET_FROM_STOP",
    "risk_budget_amount": "10"
  }
}
```

`quantity = risk_budget_amount / abs(evidence_price - stop_loss)` - deterministic from GIL's own `stop_loss` plus fresh, approved market evidence only. If evidence price ever equals `stop_loss` exactly (zero stop distance), this cannot resolve and stays `WAITING_EVIDENCE`/watchable rather than dividing by zero or guessing.

### Example response (`200`, durable receipt only - not yet processed)

```json
{
  "decision_id": "gil-2026-09-01-001",
  "received_at": "2026-09-01T12:00:03.481000+00:00",
  "status": "PENDING_DRAIN",
  "outcome": null,
  "outcome_reason": null,
  "intent_id": null,
  "processed_at": null,
  "simulation_only": true
}
```

## Status query / readback

`GET /experiment1/gil-decisions/{decision_id}` returns the same envelope shape at its current state, so GIL/Control Tower can verify delivery without depending on Slack text as a transport - Slack remains the human evidence/audit log, never the machine ingestion path. `404` for an unknown `decision_id`.

Once a drain cycle has run:

```json
{
  "decision_id": "gil-2026-09-01-001",
  "received_at": "2026-09-01T12:00:03.481000+00:00",
  "status": "PROCESSED",
  "outcome": "PENDING",
  "outcome_reason": null,
  "intent_id": "gil-decision:gil-2026-09-01-001",
  "processed_at": "2026-09-01T12:04:47.112000+00:00",
  "simulation_only": true
}
```

`status` is the inbox envelope's own lifecycle: `PENDING_DRAIN` (received, not yet resolved - see "watchable decisions" below), `PROCESSED` (a drain cycle resolved it terminally), or `MALFORMED` (had a `decision_id` but failed `GilDecision`'s own domain validation - e.g. a non-timezone-aware `decided_at`, or a trigger/sizing shape missing its required field - and never reaches drain).

`outcome`, once `PROCESSED`, is one of:

| outcome | meaning |
|---|---|
| `PENDING` | accepted, submitted as a pending intent - existing risk validation passed, awaiting a paper fill through the existing market cycle |
| `NO_ACTION` | a `WAIT`/`HOLD` decision - recorded, never executable |
| `BLOCKED` | rejected by MarketHunter's existing account/leverage/margin policy (see `outcome_reason` for the exact reason) - no fill created |
| `WAITING_EVIDENCE` (terminal) | the decision carried an `execution_condition` - a subjective condition GIL could not structure (e.g. "confirmed reclaim with continuation evidence"). No evaluator exists anywhere in this codebase that can objectively verify arbitrary text against market evidence, so it is never guessed into an executable order - the condition is preserved in the stored envelope for a future evaluator, not discarded |

`intent_id` is the deterministic mapping `gil-decision:{decision_id}` - the full audit provenance trail back to the originating GIL decision, recoverable in either direction without a separate lookup table (see `experiment1.gil_decision.intent_id_for` / `decision_id_from`).

## Structured execution triggers and sizing

`trigger` (optional `ExecutionTrigger`) is a closed, structured, objectively-evaluable-from-evidence gate - `trigger_type` is one of `IMMEDIATE` (default when omitted - existing behavior, submit as soon as risk-validated), `PRICE_AT_OR_ABOVE`, `PRICE_AT_OR_BELOW`, or `PRICE_IN_RANGE`. A `note` field carries any richer free-text context GIL wants attached for human readability - it is **never** evaluated, only the structured price field(s) gate execution.

`sizing` (optional `SizingIntent`, mutually exclusive with `quantity`) is one of:

| mode | resolves to |
|---|---|
| `EXACT_QUANTITY` | `exact_quantity` verbatim - no evidence needed |
| `MAX_NOTIONAL` | `max_notional / evidence_price`, once a fresh quote exists |
| `RISK_BUDGET_FROM_STOP` | `risk_budget_amount / abs(evidence_price - stop_loss)` - requires the decision's own `stop_loss` |

### Watchable decisions

A decision whose trigger is not yet satisfied, or whose sizing needs a fresh quote that isn't currently available, **stays `PENDING_DRAIN`** rather than becoming a terminal outcome - `outcome_reason` is updated each cycle to explain the current wait (e.g. `"trigger PRICE_IN_RANGE not yet satisfied at price 108"`), but `status`/`outcome`/`intent_id` are left alone. The next scheduled drain cycle re-checks it against fresh evidence automatically - no resubmission needed. Once the trigger is satisfied and (if applicable) a quantity is deterministically resolved, it is submitted exactly once, moving to `status: PROCESSED`.

A stale, missing, or unsupported quote for the decision's symbol produces the same watchable `WAITING_EVIDENCE` result as an unmet trigger - never a fabricated mark, never a guess.

## GIL-declared reference-close fill (Investments buy-and-hold only)

`reference_close_price` (optional `Decimal`, positive) is the narrow, explicitly-labeled exception to "MarketHunter independently verifies evidence before a fill": GIL's own claimed reference/closing price for a decision it has already priced itself. It exists because this repository has no live non-crypto quote provider wired into the runtime (see `docs/experiment1-market-data-evidence-contract.md`) - without it, a non-crypto Investments decision would stay `WAITING_EVIDENCE` forever, even for buy-and-hold research sizing that doesn't need execution-grade evidence the way Active Trading does.

**Only valid for `INVESTMENTS_DEFENSIVE`/`INVESTMENTS_BALANCED`/`INVESTMENTS_GROWTH`.** `GilDecision.__post_init__` rejects it outright for `SPOT`/`FUTURES` (Active Trading) - a `400`/persisted-`MALFORMED` response, the same fail-closed path as any other domain-validation error, never a silent downgrade of `EXECUTION_EVIDENCE_OK`. It also requires a fixed `quantity` (not `sizing`) and, if a `trigger` is present, only `IMMEDIATE`.

When present, `drain_gil_decision_inbox` fills the resulting intent immediately once it reaches `PENDING`, using GIL's own declared price rather than a live quote - no `AsyncQuoteSource` lookup happens at all for this decision. The resulting fill's `source` is explicitly `"GIL_SIMULATED_REFERENCE_CLOSE_FILL"` (never a live-provider name) and `source_reference` is `"gil-decision:{decision_id}:reference-close"` - so no downstream reader (audit, statistics, a future readiness verdict) can mistake this for independently-verified live execution. `outcome` is reported as `FILLED` (see `IntentStatus`) rather than the usual `PENDING`.

### Example request - Investments reference-close fill

```json
POST /experiment1/gil-decisions
{
  "decision_id": "gil-2026-09-02-crox-tranche-1",
  "decided_at": "2026-09-02T00:00:00+00:00",
  "account": "INVESTMENTS_GROWTH",
  "action": "BUY",
  "symbol": "CROX",
  "thesis": "first Growth tranche in the CROX buy zone",
  "quantity": "4",
  "reference_close_price": "115.28"
}
```

## What this closes, and what remains

Closed by this contract: GIL now has a fixed, machine-addressable HTTP endpoint to deliver a decision to, with durable receipt, automatic processing, full audit provenance, and idempotent replay - no manual copy/paste step exists in MarketHunter's side of the pipeline once a request reaches this endpoint.

**Final transport-origin blocker, isolated explicitly rather than pretending otherwise:** whether the GIL agent itself has a machine caller that issues this `POST` request is outside this repository's scope and this session's visibility. If GIL currently only produces Slack text for a human to relay, that human relay step - not anything in this contract - is the remaining link between a GIL decision and this endpoint.
