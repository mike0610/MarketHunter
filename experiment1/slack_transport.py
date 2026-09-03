from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from experiment1.engine import Experiment1Engine, Experiment1Error
from experiment1.gil_decision import decision_from_json, decision_to_json


logger = logging.getLogger("experiment1.slack_transport")

MARKER = "GIL DECISION ENVELOPE v1"
CANONICAL_CHANNEL_ID = "C0BNACTF4E4"
CANONICAL_GIL_USER_ID = "U0BMKMQ4U04"
CHATGPT_SLACK_APP_USER_ID = "U0BME2V91TQ"
# Slack Web API stores mentions in raw <@USER_ID> form. Some connector/read
# surfaces enrich that same mention as <@USER_ID|DisplayName>. Accept exactly
# these two deterministic provenance renderings and no arbitrary footer.
CHATGPT_CONNECTOR_FOOTER = f"*Sent using* <@{CHATGPT_SLACK_APP_USER_ID}>"
CHATGPT_CONNECTOR_RENDERED_FOOTER = f"*Sent using* <@{CHATGPT_SLACK_APP_USER_ID}|ChatGPT>"\n# Some Slack history reads render the same connector provenance as a bare app\n# mention without a display label. Keep this exact suffix allowlisted too.\nCHATGPT_CONNECTOR_BARE_FOOTER = f"*Sent using* <@{CHATGPT_SLACK_APP_USER_ID}>"

ENV_ENABLED = "GIL_SLACK_TRANSPORT_ENABLED"
ENV_TOKEN = "GIL_SLACK_BOT_TOKEN"
ENV_CHANNEL_ID = "GIL_SLACK_CHANNEL_ID"
ENV_ALLOWED_USER_ID = "GIL_SLACK_ALLOWED_USER_ID"
ENV_CHECKPOINT_PATH = "GIL_SLACK_CHECKPOINT_PATH"

DEFAULT_CHECKPOINT_PATH = Path("data/experiment1_gil_slack_checkpoint.json")
SLACK_HISTORY_URL = "https://slack.com/api/conversations.history"

# Native/manual Slack form: preserve the original strict contract.
_CANONICAL_ENVELOPE_RE = re.compile(
    r"\A\s*GIL DECISION ENVELOPE v1\s*\n```json\s*\n(?P<payload>\{.*\})\s*\n```\s*\Z",
    re.DOTALL,
)

# ChatGPT's Slack connector can persist code formatting in a fenced block, a
# single-backtick inline code span, or as plain text after markdown
# normalization. All accepted forms remain machine-only envelopes: the marker
# must be first, the JSON object must consume the complete payload, and any
# trailer must be the exact ChatGPT provenance footer. Arbitrary prose remains
# rejected.
_CONNECTOR_FOOTER_RE = rf"(?:{re.escape(CHATGPT_CONNECTOR_FOOTER)}|{re.escape(CHATGPT_CONNECTOR_RENDERED_FOOTER)}|{re.escape(CHATGPT_CONNECTOR_BARE_FOOTER)})"
_CONNECTOR_ENVELOPE_RE = re.compile(
    rf"\A\s*GIL DECISION ENVELOPE v1\s*\n```(?:json\s*\n?)?\s*(?P<payload>\{{.*\}})\s*```\s*\n{_CONNECTOR_FOOTER_RE}\s*\Z",
    re.DOTALL,
)
_CONNECTOR_INLINE_ENVELOPE_RE = re.compile(
    rf"\A\s*GIL DECISION ENVELOPE v1\s*\n`(?P<payload>\{{[^\r\n`]*\}})`\s*\n{_CONNECTOR_FOOTER_RE}\s*\Z"
)
_PLAIN_ENVELOPE_RE = re.compile(
    rf"\A\s*GIL DECISION ENVELOPE v1\s*\n(?P<payload>\{{.*\}})(?:\s*\n{_CONNECTOR_FOOTER_RE})?\s*\Z",
    re.DOTALL,
)

_TOP_LEVEL_KEYS = {
    "decision_id",
    "decided_at",
    "account",
    "action",
    "symbol",
    "thesis",
    "quantity",
    "leverage",
    "stop_loss",
    "take_profit",
    "execution_condition",
    "trigger",
    "sizing",
    "reference_close_price",
}
_TRIGGER_KEYS = {
    "trigger_type",
    "trigger_price",
    "trigger_price_low",
    "trigger_price_high",
    "note",
}
_SIZING_KEYS = {
    "mode",
    "exact_quantity",
    "max_notional",
    "risk_budget_amount",
}


class SlackTransportError(RuntimeError):
    pass


class SlackHistoryClient(Protocol):
    def history(
        self, *, channel: str, oldest: str | None = None, limit: int = 100, cursor: str | None = None
    ) -> dict:
        ...


class SlackWebApiHistoryClient:
    """Minimal read-only Slack Web API client using only the Python standard library."""

    def __init__(self, token: str, *, timeout_seconds: int = 10) -> None:
        if not token or not token.strip():
            raise SlackTransportError("Slack token is blank")
        self._token = token
        self._timeout_seconds = timeout_seconds

    def history(
        self, *, channel: str, oldest: str | None = None, limit: int = 100, cursor: str | None = None
    ) -> dict:
        params: dict[str, str] = {"channel": channel, "limit": str(limit)}
        if oldest is not None:
            params["oldest"] = oldest
            params["inclusive"] = "false"
        if cursor:
            params["cursor"] = cursor
        request = Request(
            f"{SLACK_HISTORY_URL}?{urlencode(params)}",
            headers={"Authorization": f"Bearer {self._token}", "User-Agent": "MarketHunter-Experiment1/1"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise SlackTransportError(f"Slack history request failed: {type(exc).__name__}") from exc
        if not payload.get("ok"):
            error = payload.get("error", "unknown_error")
            raise SlackTransportError(f"Slack history API rejected request: {error}")
        return payload


@dataclass(frozen=True, slots=True)
class SlackTransportConfig:
    channel_id: str = CANONICAL_CHANNEL_ID
    allowed_user_id: str = CANONICAL_GIL_USER_ID
    checkpoint_path: Path = DEFAULT_CHECKPOINT_PATH

    def __post_init__(self) -> None:
        if self.channel_id != CANONICAL_CHANNEL_ID:
            raise SlackTransportError(
                f"channel allowlist violation: expected {CANONICAL_CHANNEL_ID}, got {self.channel_id}"
            )
        if self.allowed_user_id != CANONICAL_GIL_USER_ID:
            raise SlackTransportError(
                f"GIL sender allowlist violation: expected {CANONICAL_GIL_USER_ID}, got {self.allowed_user_id}"
            )


@dataclass(frozen=True, slots=True)
class SlackTransportSummary:
    enabled: bool
    bootstrapped: bool
    messages_seen: int
    ordinary_ignored: int
    accepted: int
    rejected: int
    checkpoint: str | None


def transport_enabled_from_env() -> bool:
    return os.getenv(ENV_ENABLED, "").strip().lower() in {"1", "true", "yes", "on"}


def config_from_env() -> SlackTransportConfig:
    return SlackTransportConfig(
        channel_id=os.getenv(ENV_CHANNEL_ID, CANONICAL_CHANNEL_ID).strip(),
        allowed_user_id=os.getenv(ENV_ALLOWED_USER_ID, CANONICAL_GIL_USER_ID).strip(),
        checkpoint_path=Path(os.getenv(ENV_CHECKPOINT_PATH, str(DEFAULT_CHECKPOINT_PATH))),
    )


def client_from_env() -> SlackWebApiHistoryClient:
    token = os.getenv(ENV_TOKEN, "")
    if not token.strip():
        raise SlackTransportError(f"{ENV_TOKEN} is not configured")
    return SlackWebApiHistoryClient(token)


def _validate_exact_schema(data: object) -> dict:
    if not isinstance(data, dict):
        raise ValueError("envelope JSON must be an object")
    keys = set(data)
    if keys != _TOP_LEVEL_KEYS:
        missing = sorted(_TOP_LEVEL_KEYS - keys)
        extra = sorted(keys - _TOP_LEVEL_KEYS)
        raise ValueError(f"envelope keys mismatch: missing={missing} extra={extra}")

    trigger = data["trigger"]
    if trigger is not None:
        if not isinstance(trigger, dict) or set(trigger) != _TRIGGER_KEYS:
            raise ValueError("trigger must use the exact canonical trigger schema")

    sizing = data["sizing"]
    if sizing is not None:
        if not isinstance(sizing, dict) or set(sizing) != _SIZING_KEYS:
            raise ValueError("sizing must use the exact canonical sizing schema")
    return data


def parse_structured_envelope(text: str) -> str | None:
    """
    Return canonical decision JSON only when the entire Slack message is one
    of the explicitly supported machine forms: the original canonical fenced
    JSON form, connector fenced/inline forms, or Slack's observed plain-text
    normalization of the same strict envelope. Ordinary GIL research text is
    always ignored.
    """
    raw = (text or "").replace("\r\n", "\n")
    match = _CANONICAL_ENVELOPE_RE.match(raw)
    if match is None:
        match = _CONNECTOR_ENVELOPE_RE.match(raw)
    if match is None:
        match = _CONNECTOR_INLINE_ENVELOPE_RE.match(raw)
    if match is None:
        match = _PLAIN_ENVELOPE_RE.match(raw)
    if match is None:
        return None
    data = json.loads(match.group("payload"))
    _validate_exact_schema(data)
    decision = decision_from_json(json.dumps(data, sort_keys=True))
    return decision_to_json(decision)


def _diagnostic_text_repr(text: object, *, limit: int = 4000) -> str:
    """Escaped, bounded representation of rejected Slack text for transport diagnostics."""
    rendered = repr(text)
    if len(rendered) <= limit:
        return rendered
    return rendered[:limit] + f"...<truncated {len(rendered) - limit} chars>"


def _load_checkpoint(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SlackTransportError(f"invalid Slack transport checkpoint: {path}") from exc
    ts = data.get("last_ts")
    if not isinstance(ts, str) or not ts:
        raise SlackTransportError(f"invalid Slack transport checkpoint last_ts: {path}")
    return ts


def _save_checkpoint(path: Path, ts: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps({"last_ts": ts}, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _next_cursor(payload: dict) -> str | None:
    metadata = payload.get("response_metadata") or {}
    cursor = metadata.get("next_cursor")
    return cursor if isinstance(cursor, str) and cursor else None


def _history_since(client: SlackHistoryClient, channel_id: str, oldest: str) -> list[dict]:
    messages: list[dict] = []
    cursor: str | None = None
    for _ in range(10):
        page = client.history(channel=channel_id, oldest=oldest, limit=100, cursor=cursor)
        page_messages = page.get("messages", [])
        if not isinstance(page_messages, list):
            raise SlackTransportError("Slack history response has invalid messages payload")
        messages.extend(m for m in page_messages if isinstance(m, dict))
        cursor = _next_cursor(page)
        if not cursor:
            break
    else:
        raise SlackTransportError("Slack history exceeded bounded 10-page poll window")
    return sorted(messages, key=lambda m: m.get("ts", ""))


def poll_slack_gil_decisions(
    engine: Experiment1Engine,
    client: SlackHistoryClient,
    *,
    config: SlackTransportConfig | None = None,
) -> SlackTransportSummary:
    config = config or SlackTransportConfig()
    checkpoint = _load_checkpoint(config.checkpoint_path)

    # First activation is deliberately non-backfilling. It records the latest
    # existing message and starts watching only future messages, preventing any
    # historic Slack content from unexpectedly becoming an inbound decision.
    if checkpoint is None:
        latest = client.history(channel=config.channel_id, limit=1)
        messages = latest.get("messages", [])
        latest_ts = "0"
        if isinstance(messages, list) and messages and isinstance(messages[0], dict):
            latest_ts = str(messages[0].get("ts") or "0")
        _save_checkpoint(config.checkpoint_path, latest_ts)
        return SlackTransportSummary(True, True, len(messages) if isinstance(messages, list) else 0, 0, 0, 0, latest_ts)

    seen = ignored = accepted = rejected = 0
    for message in _history_since(client, config.channel_id, checkpoint):
        ts = str(message.get("ts") or "")
        if not ts or ts <= checkpoint:
            continue
        seen += 1
        text = message.get("text")
        has_marker = isinstance(text, str) and MARKER in text

        if not has_marker:
            ignored += 1
            _save_checkpoint(config.checkpoint_path, ts)
            checkpoint = ts
            continue

        reason: str | None = None
        if message.get("user") != config.allowed_user_id:
            reason = "sender is not the canonical GIL Slack user"
        elif message.get("channel") not in (None, config.channel_id):
            reason = "message channel does not match canonical GIL channel"
        elif message.get("subtype") is not None:
            reason = "Slack message subtype is not accepted for machine delivery"
        elif message.get("edited") is not None:
            reason = "edited GIL decision envelope is rejected; emit a new decision_id instead"

        canonical_json: str | None = None
        if reason is None:
            try:
                canonical_json = parse_structured_envelope(text)
                if canonical_json is None:
                    reason = "marker present but message is not an exact GIL DECISION ENVELOPE v1 block"
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                reason = f"invalid structured GIL envelope: {exc}"

        if reason is None and canonical_json is not None:
            try:
                decision = decision_from_json(canonical_json)
                engine.receive_gil_decision(decision.decision_id, canonical_json)
                accepted += 1
                logger.info("Slack GIL envelope accepted - decision_id=%s ts=%s", decision.decision_id, ts)
            except (Experiment1Error, ValueError, KeyError, TypeError) as exc:
                rejected += 1
                logger.warning("Slack GIL envelope rejected at inbox boundary - ts=%s reason=%s", ts, exc)
        else:
            rejected += 1
            logger.warning(
                "Slack GIL envelope rejected - ts=%s reason=%s raw_text=%s",
                ts,
                reason,
                _diagnostic_text_repr(text),
            )

        # Advance only after this message has been deterministically handled.
        # If the process crashes after durable inbox receipt but before this
        # write, replay is still safe because decision_id is idempotent.
        _save_checkpoint(config.checkpoint_path, ts)
        checkpoint = ts

    return SlackTransportSummary(True, False, seen, ignored, accepted, rejected, checkpoint)
