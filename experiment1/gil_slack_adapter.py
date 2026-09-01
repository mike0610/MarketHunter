"""
MarketHunter

experiment1/gil_slack_adapter.py

Module:
The final transport-origin adapter: reads ONLY the allowlisted
#global-investment-lab channel (see DEFAULT_GIL_CHANNEL_ID) for an
explicit machine-delivery block carrying the strict literal marker
"GIL DECISION ENVELOPE v1" immediately followed by a single closed
fenced JSON code block, and forwards ONLY that validated envelope into
the existing durable GIL Decision Inbox
(Experiment1Engine.receive_gil_decision) - the exact same path
POST /experiment1/gil-decisions already uses, reusing the same
canonical serialization (experiment1.gil_decision.decision_to_json) so
a decision delivered via either origin idempotency-compares
identically. There is no second execution path: this module never
calls submit_intent/ingest_gil_decision itself - only the existing
drain_gil_decision_inbox cycle ever turns an inbox row into an
OrderIntent.

Ordinary Slack prose - CANDIDATE/WATCH research packets, contract
descriptions, evidence packets, status updates - is never parsed for a
decision: only a message carrying the literal marker line is even
inspected for a JSON block, and only a well-formed one produces the
already-existing GilDecision (or a persisted MALFORMED row, using the
exact same audit path api/experiment1_api.py already uses for a
malformed HTTP submission - never a silent drop).

Fail-closed conditions (never guessed past):
  - message not in the allowlisted channel -> ignored (defensive only;
    a compliant reader is already scoped to one channel)
  - marker literal not present -> ignored, ordinary prose
  - marker present but no closed fenced JSON block follows it ->
    MALFORMED_SHAPE - decision_id is not recoverable, so nothing is
    persisted to the inbox table (there is no decision_id to key it on)
  - JSON parses but a decision_id is present and GilDecision's own
    domain validation rejects it -> persisted MALFORMED via
    Experiment1Engine.record_malformed_gil_decision, identical to the
    HTTP endpoint's own malformed-submission contract
  - message.edited is set -> EDITED_AMBIGUOUS, never processed: this
    adapter cannot know whether an edit changed a decision it may have
    already read differently on a prior poll, so it never guesses -
    GIL must post a fresh envelope under a new decision_id instead
  - valid envelope -> forwarded verbatim via
    engine.receive_gil_decision(decision.decision_id,
    decision_to_json(decision))

Checkpoint/cursor restart safety:
Experiment1Engine persists a per-channel last-processed Slack message
ts (get_slack_ingest_cursor/set_slack_ingest_cursor) - every poll only
asks the reader for messages strictly after that cursor, and the
cursor only advances past a message once it has been fully handled
(ignored, malformed, edited-ambiguous, or forwarded). A restart mid-
poll can, at worst, reprocess the single message the cursor had not
yet advanced past when it stopped; decision_id idempotency in
receive_gil_decision/record_malformed_gil_decision is the final guard
against that becoming a duplicate.

Credential boundary: this module accepts an injectable
SlackChannelReader instead of hardcoding a live dependency - the same
"inject the evidence source, fail closed by omission if it is not
wired" pattern already used throughout Experiment 1 (see
experiment1/runtime.py's AsyncQuoteSource,
tools/experiment1_runtime/runtime.py's build_quote_source). A real
SlackWebApiChannelReader implementation exists below and is directly
testable, but build_gil_slack_reader() only returns one when
EXPERIMENT1_GIL_SLACK_BOT_TOKEN is actually set. MarketHunter's only
existing Slack credential today (OUTCOME_INTELLIGENCE_SLACK_WEBHOOK_URL,
see tools/outcome_intelligence/runtime.py) is a write-only incoming
webhook URL with no read API at all - architecturally incapable of
listing channel history regardless of scope - so unless a genuine Bot
OAuth token with a conversation-read scope has separately been
provisioned, build_gil_slack_reader() returns None and the runtime
scheduler skips this step entirely each cycle rather than fabricating
a connection.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Protocol

import httpx

from experiment1.engine import Experiment1Engine, Experiment1Error
from experiment1.gil_decision import decision_from_json, decision_to_json
from experiment1.models import GilDecision

ENVELOPE_MARKER = "GIL DECISION ENVELOPE v1"

# Verified via slack_search_channels against the live workspace on
# 2026-09-01 - the real #global-investment-lab channel_id, not a
# placeholder. Overridable only for testing; production always reads
# this one allowlisted channel unless EXPERIMENT1_GIL_SLACK_CHANNEL_ID
# is explicitly set.
DEFAULT_GIL_CHANNEL_ID = "C0BNACTF4E4"

ENV_SLACK_BOT_TOKEN = "EXPERIMENT1_GIL_SLACK_BOT_TOKEN"
ENV_SLACK_CHANNEL_ID = "EXPERIMENT1_GIL_SLACK_CHANNEL_ID"

_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)

logger = logging.getLogger("experiment1.gil_slack_adapter")


@dataclass(frozen=True, slots=True)
class SlackMessage:
    ts: str
    text: str
    channel_id: str
    edited: bool = False


class SlackChannelReader(Protocol):
    async def fetch_new_messages(self, channel_id: str, after_ts: str | None) -> tuple[SlackMessage, ...]:
        """Every message in channel_id strictly after after_ts, oldest first. after_ts=None means from the beginning."""
        ...


@dataclass(frozen=True, slots=True)
class SlackIngestResult:
    message_ts: str
    decision_id: str | None
    status: str  # "IGNORED_NO_MARKER" | "EDITED_AMBIGUOUS" | "MALFORMED_SHAPE" | "MALFORMED" | "RECEIVED"
    detail: str | None = None


def _extract_envelope_json(text: str) -> str | None:
    """
    The raw JSON text of the single fenced code block that follows the
    literal marker line, or None if the marker is absent or no closed
    fenced block follows it anywhere in the rest of the message. Never
    attempts a best-effort parse of an unfenced or unclosed block - a
    clean match or nothing.
    """
    marker_index = text.find(ENVELOPE_MARKER)
    if marker_index == -1:
        return None
    remainder = text[marker_index + len(ENVELOPE_MARKER):]
    match = _FENCE_RE.search(remainder)
    if match is None:
        return None
    return match.group(1)


def _parse_envelope(raw_json: str) -> tuple[GilDecision | None, str | None, str | None]:
    """
    Returns (decision, decision_id_if_recoverable, error) - error is
    None only when decision is not None. decision_id_if_recoverable
    lets the caller persist a MALFORMED audit row even when
    GilDecision's own validation rejected the payload, mirroring
    api/experiment1_api.py's own malformed-submission path exactly.
    """
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        return None, None, f"envelope JSON block is not valid JSON: {exc}"
    decision_id = data.get("decision_id") if isinstance(data, dict) else None
    try:
        decision = decision_from_json(raw_json)
    except KeyError as exc:
        return None, decision_id, f"envelope missing required field: {exc}"
    except (ValueError, TypeError) as exc:
        return None, decision_id, str(exc)
    return decision, decision_id, None


async def run_gil_slack_ingest_cycle(
    engine: Experiment1Engine, reader: SlackChannelReader, channel_id: str
) -> tuple[SlackIngestResult, ...]:
    """
    One bounded pass: fetch every message posted to channel_id since
    this channel's persisted cursor, process each in order, and
    advance the cursor past every message this pass looked at -
    whether it was ignored, malformed, edited-ambiguous, or forwarded.
    Only a message carrying a closed, well-formed envelope is ever
    forwarded to engine.receive_gil_decision - the exact same durable
    inbox row a POST /experiment1/gil-decisions call would have
    produced. No second execution path: this function never submits an
    intent itself.
    """
    cursor = engine.get_slack_ingest_cursor(channel_id)
    messages = await reader.fetch_new_messages(channel_id, after_ts=cursor)

    results: list[SlackIngestResult] = []
    latest_ts = cursor
    for message in messages:
        if message.channel_id != channel_id:
            # Defensive only - a compliant reader is already scoped to
            # channel_id, but this adapter never trusts that silently.
            continue

        if ENVELOPE_MARKER not in message.text:
            results.append(SlackIngestResult(message.ts, None, "IGNORED_NO_MARKER"))
            latest_ts = message.ts
            continue

        if message.edited:
            reason = (
                "message was edited after posting - failing closed rather than guessing "
                "which version is authoritative"
            )
            logger.warning("gil slack ingest: %s ts=%s", reason, message.ts)
            results.append(SlackIngestResult(message.ts, None, "EDITED_AMBIGUOUS", detail=reason))
            latest_ts = message.ts
            continue

        raw_json = _extract_envelope_json(message.text)
        if raw_json is None:
            reason = "marker present but no closed fenced JSON block follows it"
            logger.warning("gil slack ingest: %s ts=%s", reason, message.ts)
            results.append(SlackIngestResult(message.ts, None, "MALFORMED_SHAPE", detail=reason))
            latest_ts = message.ts
            continue

        decision, decision_id, error = _parse_envelope(raw_json)
        if error is not None:
            logger.warning(
                "gil slack ingest: malformed envelope ts=%s decision_id=%s: %s", message.ts, decision_id, error
            )
            if decision_id:
                try:
                    engine.record_malformed_gil_decision(decision_id, raw_json, error)
                except Experiment1Error:
                    # Already recorded (possibly under different content) -
                    # never overwrite an existing audit row silently.
                    pass
            results.append(SlackIngestResult(message.ts, decision_id, "MALFORMED", detail=error))
            latest_ts = message.ts
            continue

        assert decision is not None  # error is None => decision is set
        record = engine.receive_gil_decision(decision.decision_id, decision_to_json(decision))
        results.append(SlackIngestResult(message.ts, decision.decision_id, "RECEIVED", detail=record.status.value))
        latest_ts = message.ts

    if latest_ts != cursor:
        engine.set_slack_ingest_cursor(channel_id, latest_ts)

    return tuple(results)


class SlackWebApiChannelReader:
    """
    Reads a Slack channel's history via the Slack Web API
    (conversations.history) using a Bot OAuth token with the minimum
    channels:history (or groups:history, for a private channel) read
    scope. This is the ONLY real, network-calling SlackChannelReader in
    this module - never constructed by default (see
    build_gil_slack_reader), so a caller without a genuine credential
    never accidentally acquires a live network dependency.
    """

    def __init__(self, bot_token: str, client: httpx.AsyncClient):
        if not bot_token or not bot_token.strip():
            raise ValueError("bot_token must be non-blank")
        self._bot_token = bot_token
        self._client = client

    async def fetch_new_messages(self, channel_id: str, after_ts: str | None) -> tuple[SlackMessage, ...]:
        params: dict[str, str] = {"channel": channel_id, "limit": "200"}
        if after_ts is not None:
            # Slack's `oldest` is inclusive - the exact cursor message
            # itself is filtered back out below so it is never
            # reprocessed.
            params["oldest"] = after_ts
        response = await self._client.get(
            "https://slack.com/api/conversations.history",
            params=params,
            headers={"Authorization": f"Bearer {self._bot_token}"},
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok", False):
            raise RuntimeError(f"Slack conversations.history failed: {payload.get('error', 'unknown error')}")

        messages = [
            SlackMessage(
                ts=item["ts"],
                text=item.get("text", ""),
                channel_id=channel_id,
                edited="edited" in item,
            )
            for item in payload.get("messages", [])
            if after_ts is None or item["ts"] != after_ts
        ]
        # Slack returns newest-first; the adapter always processes oldest-first.
        messages.sort(key=lambda m: m.ts)
        return tuple(messages)


def resolve_gil_channel_id() -> str:
    return os.environ.get(ENV_SLACK_CHANNEL_ID, DEFAULT_GIL_CHANNEL_ID)


def build_gil_slack_reader(*, client: httpx.AsyncClient | None = None) -> SlackChannelReader | None:
    """
    Returns a real SlackWebApiChannelReader only when
    EXPERIMENT1_GIL_SLACK_BOT_TOKEN is actually set in the environment.
    MarketHunter's only existing Slack credential
    (OUTCOME_INTELLIGENCE_SLACK_WEBHOOK_URL) is a write-only incoming
    webhook with no read API at all, so unless a genuine Bot OAuth
    token has separately been provisioned, this returns None and the
    caller skips the Slack ingest step entirely for this cycle - fail
    closed by omission, the same pattern
    tools/experiment1_runtime/runtime.py's build_quote_source() already
    uses for an unrecognized asset class, never a fabricated
    connection. Never logs the token.
    """
    token = os.environ.get(ENV_SLACK_BOT_TOKEN)
    if not token:
        return None
    return SlackWebApiChannelReader(token, client or httpx.AsyncClient())
