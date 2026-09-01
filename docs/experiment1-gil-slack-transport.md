# Experiment 1 — GIL Slack machine transport

This transport closes the origin gap between GIL and the existing durable MarketHunter GIL Decision Inbox without introducing another decision-maker or another execution path.

## Safety boundary

The runtime reads only the canonical `#global-investment-lab` channel (`C0BNACTF4E4`) and only messages from the canonical GIL Slack user (`U0BMKMQ4U04`). Ordinary Slack prose, evidence packets, `CANDIDATE`, `WATCH`, or any other research text is never interpreted as an order.

A machine-deliverable message must be the entire Slack message and use exactly this shape:

```text
GIL DECISION ENVELOPE v1
```json
{canonical GilDecision JSON}
```
```

The JSON must use the exact canonical schema emitted by `experiment1.gil_decision.decision_to_json()`. The domain model still restricts actions to `BUY | SELL | LONG | SHORT | WAIT | HOLD`; unsupported research states fail closed.

Edited machine envelopes are rejected. To change a decision, GIL must emit a new message with a new `decision_id` rather than edit an already-delivered envelope.

## Runtime path

`Slack history (read-only) -> strict marker/schema/user/channel validation -> Experiment1Engine.receive_gil_decision() -> durable GIL Decision Inbox -> existing drain_gil_decision_inbox() -> canonical OrderIntent/risk validation -> existing paper lifecycle`

`decision_id` remains the final idempotency key. The Slack poller also keeps an atomic timestamp checkpoint so repeated scheduled cycles and process restarts do not re-read old messages. If the process crashes after durable inbox receipt but before checkpoint persistence, replay remains safe because the inbox rejects a conflicting `decision_id` and accepts an identical replay idempotently.

## First activation

The first successful poll intentionally does not backfill historic Slack messages. It records the newest existing message timestamp and starts watching only messages created after that checkpoint.

## Required environment

The transport is off by default. Configure the existing Experiment 1 runtime environment file with:

```text
GIL_SLACK_TRANSPORT_ENABLED=1
GIL_SLACK_BOT_TOKEN=xoxb-REDACTED
GIL_SLACK_CHANNEL_ID=C0BNACTF4E4
GIL_SLACK_ALLOWED_USER_ID=U0BMKMQ4U04
GIL_SLACK_CHECKPOINT_PATH=/home/ubuntu/MarketHunter/data/experiment1_gil_slack_checkpoint.json
```

The token only needs read access to the canonical channel history. Never commit it. If Slack credentials/scopes are missing or invalid, delivery fails closed while the independent paper monitoring/accounting runtime continues.

## Proof rule

End-to-end transport readiness is not inferred from tests or a merge. It requires an observed runtime proof using a synthetic `WAIT` or `HOLD` envelope: Slack message -> durable inbox -> processed `NO_ACTION`, with no intent/fill/position and no duplicate after another scheduled/restart cycle.
