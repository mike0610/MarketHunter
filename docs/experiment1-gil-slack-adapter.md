# Experiment 1 GIL Decision Slack Envelope Adapter

The final transport-origin adapter for `docs/experiment1-gil-decision-inbox.md`'s
own remaining blocker: "whether the GIL agent itself has a machine caller that
issues this `POST` request." This module gives GIL a second, Slack-native way
to reach the exact same durable inbox, without inventing a second execution
path.

## What it reads, and what it never reads

Reads only the allowlisted `#global-investment-lab` channel (verified
`channel_id` `C0BNACTF4E4`), and only inspects a message for a decision at all
if it contains the literal marker line:

```
GIL DECISION ENVELOPE v1
```

immediately followed, anywhere later in the same message, by a single closed
fenced JSON code block. Everything else in `#global-investment-lab` -
CANDIDATE/WATCH research packets, evidence packets, contract descriptions,
status updates, ordinary human discussion - is read as plain Slack history but
never parsed for a decision. Slack remains the human evidence/audit surface;
only a marked block is ever treated as a machine origin event.

## The envelope itself

The fenced JSON block uses exactly the same schema `POST /experiment1/gil-decisions`
already accepts - `experiment1.gil_decision.decision_to_json`/`decision_from_json`,
the identical canonical serialization the HTTP endpoint's stored envelope
uses. This is deliberate: GIL does not need a second schema to learn, and a
decision delivered via Slack idempotency-compares identically to the same
decision delivered via the HTTP endpoint, because both paths serialize through
the same function before ever reaching the durable inbox.

```
GIL DECISION ENVELOPE v1
```json
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
  "take_profit": "65000",
  "execution_condition": null,
  "trigger": null,
  "sizing": null
}
```
```

## Forwarding: no second execution path

A well-formed envelope is forwarded verbatim to
`Experiment1Engine.receive_gil_decision(decision.decision_id, decision_to_json(decision))`
- the exact same durable-receipt-only method `POST /experiment1/gil-decisions`
calls. This module never calls `submit_intent`/`ingest_gil_decision` itself.
Processing into an `OrderIntent` still happens only through the existing,
unmodified `experiment1.gil_decision.drain_gil_decision_inbox` cycle, which
the runtime scheduler already runs every pass (see
`tools/experiment1_runtime/runtime.py`) - now immediately after this Slack
ingest step, so a Slack-delivered decision is eligible for a fill in the same
pass it was received, exactly like an HTTP-delivered one.

## Fail-closed conditions

| condition | result | persisted? |
|---|---|---|
| channel_id does not match the allowlist | ignored (defensive only) | no |
| marker literal absent | `IGNORED_NO_MARKER` - ordinary prose | no |
| marker present, no closed fenced JSON block follows | `MALFORMED_SHAPE` | no - no `decision_id` is recoverable |
| fenced block is not valid JSON | `MALFORMED` | no - no `decision_id` is recoverable |
| JSON parses, has a `decision_id`, but fails `GilDecision`'s own domain validation (e.g. a non-timezone-aware `decided_at`, a free-text `action` like `CANDIDATE`, a trigger/sizing shape missing its required field) | `MALFORMED` | **yes** - via `Experiment1Engine.record_malformed_gil_decision`, the identical audit path `api/experiment1_api.py` already uses for a malformed HTTP submission, readable back via `GET /experiment1/gil-decisions/{decision_id}` |
| message was edited after posting | `EDITED_AMBIGUOUS` | no - never processed. This adapter cannot know whether the edit changed a decision it may have already read differently on a prior poll, so it never guesses which version is authoritative. GIL must post a fresh envelope under a new `decision_id` instead of relying on an edit being picked up. |
| well-formed envelope | `RECEIVED` | yes - the same `PENDING_DRAIN` inbox row `POST /experiment1/gil-decisions` would have produced |

A `CANDIDATE`/`WATCH` research state, or any other value outside the existing
`DecisionAction` enum, is rejected the same way it already is at the HTTP
layer - `GilDecision.__post_init__`/the `DecisionAction(...)` enum lookup
itself raises before anything is treated as executable.

## Checkpoint / cursor restart safety

`Experiment1Engine` persists a per-channel cursor
(`get_slack_ingest_cursor`/`set_slack_ingest_cursor`, table
`experiment1_slack_ingest_cursor`) - the last Slack message `ts` this
channel's adapter has fully handled, whatever the outcome. Every poll only
asks the reader for messages strictly after that cursor
(`SlackWebApiChannelReader` passes it as Slack's own `oldest` parameter and
additionally filters the cursor message itself back out, since `oldest` is
inclusive), and the cursor only advances once a message has been fully
handled - ignored, malformed, edited-ambiguous, or forwarded. A restart
mid-poll can, at worst, reprocess the single message the cursor had not yet
advanced past; `decision_id` idempotency in `receive_gil_decision`/
`record_malformed_gil_decision` is the final guard against that becoming a
duplicate, exactly as already relied on throughout the GIL Decision Inbox
contract.

## Credential boundary - the exact one-time setup, if not already done

`experiment1.gil_slack_adapter.build_gil_slack_reader()` returns a real,
network-calling `SlackWebApiChannelReader` **only** when
`EXPERIMENT1_GIL_SLACK_BOT_TOKEN` is actually set in the runtime process's
environment. `tools/experiment1_runtime/runtime.py`'s scheduler cycle skips
the entire Slack ingest step - a normal, successful no-op, not an error -
whenever that reader is `None`.

MarketHunter's only existing Slack credential today,
`OUTCOME_INTELLIGENCE_SLACK_WEBHOOK_URL` (see
`tools/outcome_intelligence/runtime.py`,
`tools/outcome_intelligence/slack_delivery.py`), is a write-only **incoming
webhook URL** - it can only `POST` a message to one fixed channel and has no
read API at all, regardless of scope. It is architecturally incapable of
listing `#global-investment-lab`'s message history. No other Slack credential
exists anywhere in this repository's deploy configuration.

**Therefore: no usable read-scoped Slack credential exists yet.** The exact
one-time setup required, before this adapter can ever run for real against
production Slack:

1. Create (or reuse, if one already exists outside this repo's visibility) a
   Slack app/bot in the MarketHunter workspace with the `channels:history`
   scope (or `groups:history` if `#global-investment-lab` is ever made
   private) - read-only, nothing more.
2. Install the app to the workspace and invite the bot user into
   `#global-investment-lab`.
3. Provision the resulting Bot User OAuth Token (`xoxb-...`) as
   `EXPERIMENT1_GIL_SLACK_BOT_TOKEN` in the VPS deploy's secret/environment
   configuration - parallel to how `MARKETHUNTER_VPS_SSH_PRIVATE_KEY` and
   `OUTCOME_INTELLIGENCE_SLACK_WEBHOOK_URL` are already provisioned (see
   `deploy/systemd/experiment1-runtime.env.example`).

Until that one-time setup happens, this module's parser, forwarding path,
cursor/restart safety, and every fail-closed condition above are fully built
and fully tested (`tests/test_experiment1_gil_slack_adapter.py`) against an
injectable `SlackChannelReader` - but the recurring runtime has nothing real
to poll, and correctly reports that by skipping rather than fabricating a
connection.

## What this does not change

`GilDecision` semantics, `DecisionAction` scope (`BUY`/`SELL`/`LONG`/`SHORT`/
`WAIT`/`HOLD` only), risk validation, paper execution, and the GIL Decision
Inbox contract itself are all unchanged - this module only adds a second
*origin* for the same envelope, reusing every existing step downstream of
`receive_gil_decision` unmodified.
