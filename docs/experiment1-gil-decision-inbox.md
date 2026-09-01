# Experiment 1 GIL Decision Inbox

Canonical delivery target: `POST /experiment1/gil-decisions`.

This endpoint is a durable receipt only - it never submits an intent or executes a fill itself. Every accepted envelope is processed automatically, once per cycle, by `experiment1.gil_decision.drain_gil_decision_inbox`, which the recurring `tools/experiment1_runtime` scheduler runs before its market-fill step (see `deploy/systemd/README-experiment1-runtime.md`). There is no manual operator step and no parallel execution path - draining is the only way an inbox envelope ever becomes a canonical `OrderIntent`.

## Contract

`POST /experiment1/gil-decisions` accepts exactly the existing `GilDecision` semantics (see `experiment1/models.py`). GIL owns thesis, action, sizing, invalidation, and risk parameters; MarketHunter never manufactures or reinterprets any of them. `action` is restricted to the already-decided `DecisionAction` enum (`BUY`/`SELL`/`LONG`/`SHORT`/`WAIT`/`HOLD`) - a research state like `CANDIDATE` or `WATCH` is rejected by schema validation (`422`) before any domain logic runs, never coerced into a trade.

`decision_id` is the idempotency key. Resubmitting the identical payload under the same `decision_id` is a no-op that returns the already-recorded state; resubmitting a different payload under the same `decision_id` is a `409` conflict.

### Example request

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

`status` is the inbox envelope's own lifecycle: `PENDING_DRAIN` (received, not yet processed), `PROCESSED` (a drain cycle ran it), or `MALFORMED` (had a `decision_id` but failed `GilDecision`'s own domain validation - e.g. a non-timezone-aware `decided_at` - and never reaches drain).

`outcome`, once `PROCESSED`, is one of:

| outcome | meaning |
|---|---|
| `PENDING` | accepted, submitted as a pending intent - existing risk validation passed, awaiting a paper fill through the existing market cycle |
| `NO_ACTION` | a `WAIT`/`HOLD` decision - recorded, never executable |
| `BLOCKED` | rejected by MarketHunter's existing account/leverage/margin policy (see `outcome_reason` for the exact reason) - no fill created |
| `WAITING_EVIDENCE` | the decision carried an `execution_condition`; no evaluator exists anywhere in this codebase that can objectively verify an arbitrary condition against approved market evidence, so it is never guessed into an executable order - the condition is preserved in the stored envelope for a future evaluator, not discarded |

`intent_id` is the deterministic mapping `gil-decision:{decision_id}` - the full audit provenance trail back to the originating GIL decision, recoverable in either direction without a separate lookup table (see `experiment1.gil_decision.intent_id_for` / `decision_id_from`).

## What this closes, and what remains

Closed by this contract: GIL now has a fixed, machine-addressable HTTP endpoint to deliver a decision to, with durable receipt, automatic processing, full audit provenance, and idempotent replay - no manual copy/paste step exists in MarketHunter's side of the pipeline once a request reaches this endpoint.

**Final transport-origin blocker, isolated explicitly rather than pretending otherwise:** whether the GIL agent itself has a machine caller that issues this `POST` request is outside this repository's scope and this session's visibility. If GIL currently only produces Slack text for a human to relay, that human relay step - not anything in this contract - is the remaining link between a GIL decision and this endpoint.
