from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from experiment1.engine import Experiment1Engine, Experiment1Error
from experiment1.trading_decision import TRADING_ENVELOPE_MARKER, decision_from_json, decision_to_json

CANONICAL_CHANNEL_ID = "C0BME3BU1LN"
CANONICAL_STRATEGY_USER_ID = "U0BMKMQ4U04"
CHATGPT_SLACK_APP_USER_ID = "U0BME2V91TQ"
CHATGPT_CONNECTOR_FOOTER = "*Sent using* <@{}>".format(CHATGPT_SLACK_APP_USER_ID)
CHATGPT_CONNECTOR_RENDERED_FOOTER = "*Sent using* <@{}|ChatGPT>".format(CHATGPT_SLACK_APP_USER_ID)

ENV_ENABLED = "TRADING_SLACK_TRANSPORT_ENABLED"
ENV_TOKEN = "TRADING_SLACK_BOT_TOKEN"
ENV_CHANNEL_ID = "TRADING_SLACK_CHANNEL_ID"
ENV_ALLOWED_USER_ID = "TRADING_SLACK_ALLOWED_USER_ID"
ENV_CHECKPOINT_PATH = "TRADING_SLACK_CHECKPOINT_PATH"
DEFAULT_CHECKPOINT_PATH = Path("data/experiment1_trading_slack_checkpoint.json")

_FENCE = r"\x60\x60\x60"
_FOOTER = "(?:{}|{})".format(
    re.escape(CHATGPT_CONNECTOR_FOOTER),
    re.escape(CHATGPT_CONNECTOR_RENDERED_FOOTER),
)
_PATTERNS = (
    re.compile(
        r"\A\s*{}\s*\n{}json\s*\n(?P<payload>{{.*}})\s*\n{}\s*\Z".format(
            re.escape(TRADING_ENVELOPE_MARKER), _FENCE, _FENCE
        ),
        re.DOTALL,
    ),
    re.compile(
        r"\A\s*{}\s*\n{}(?:json\s*\n?)?\s*(?P<payload>{{.*}})\s*{}\s+{}\s*\Z".format(
            re.escape(TRADING_ENVELOPE_MARKER), _FENCE, _FENCE, _FOOTER
        ),
        re.DOTALL,
    ),
    re.compile(
        r"\A\s*{}\s*\n(?P<payload>{{.*}})(?:\s+{})?\s*\Z".format(
            re.escape(TRADING_ENVELOPE_MARKER), _FOOTER
        ),
        re.DOTALL,
    ),
)

_TOP_LEVEL_KEYS = {
    "decision_id", "decided_at", "account", "action", "symbol", "thesis",
    "quantity", "leverage", "stop_loss", "take_profit", "trigger", "sizing",
}
_TRIGGER_KEYS = {
    "trigger_type", "trigger_price", "trigger_price_low", "trigger_price_high", "note",
}
_SIZING_KEYS = {
    "mode", "exact_quantity", "max_notional", "risk_budget_amount",
}


class TradingSlackTransportError(RuntimeError):
    pass


class SlackHistoryClient(Protocol):
    def history(self, *, channel: str, oldest: str | None = None, limit: int = 100, cursor: str | None = None) -> dict: ...


@dataclass(frozen=True, slots=True)
class TradingSlackTransportConfig:
    channel_id: str = CANONICAL_CHANNEL_ID
    allowed_user_id: str = CANONICAL_STRATEGY_USER_ID
    checkpoint_path: Path = DEFAULT_CHECKPOINT_PATH

    def __post_init__(self) -> None:
        if self.channel_id != CANONICAL_CHANNEL_ID:
            raise TradingSlackTransportError("channel allowlist violation")
        if self.allowed_user_id != CANONICAL_STRATEGY_USER_ID:
            raise TradingSlackTransportError("sender allowlist violation")


@dataclass(frozen=True, slots=True)
class TradingSlackTransportSummary:
    enabled: bool
    bootstrapped: bool
    messages_seen: int
    ordinary_ignored: int
    accepted: int
    rejected: int
    checkpoint: str | None


def transport_enabled_from_env() -> bool:
    return os.getenv(ENV_ENABLED, "").strip().lower() in {"1", "true", "yes", "on"}


def config_from_env() -> TradingSlackTransportConfig:
    return TradingSlackTransportConfig(
        channel_id=os.getenv(ENV_CHANNEL_ID, CANONICAL_CHANNEL_ID).strip(),
        allowed_user_id=os.getenv(ENV_ALLOWED_USER_ID, CANONICAL_STRATEGY_USER_ID).strip(),
        checkpoint_path=Path(os.getenv(ENV_CHECKPOINT_PATH, str(DEFAULT_CHECKPOINT_PATH))),
    )


def _validate_schema(data: object) -> dict:
    if not isinstance(data, dict):
        raise ValueError("envelope JSON must be an object")
    if set(data) != _TOP_LEVEL_KEYS:
        raise ValueError("envelope keys mismatch")
    if data["trigger"] is not None:
        if not isinstance(data["trigger"], dict) or set(data["trigger"]) != _TRIGGER_KEYS:
            raise ValueError("trigger schema mismatch")
    if data["sizing"] is not None:
        if not isinstance(data["sizing"], dict) or set(data["sizing"]) != _SIZING_KEYS:
            raise ValueError("sizing schema mismatch")
    return data


def parse_trading_envelope(text: str) -> str | None:
    raw = (text or "").replace("\r\n", "\n")
    match = None
    for pattern in _PATTERNS:
        match = pattern.match(raw)
        if match is not None:
            break
    if match is None:
        return None
    data = json.loads(match.group("payload"))
    _validate_schema(data)
    decision = decision_from_json(json.dumps(data, sort_keys=True))
    return decision_to_json(decision)


def _load_checkpoint(path: Path) -> str | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    ts = data.get("last_ts")
    if not isinstance(ts, str) or not ts:
        raise TradingSlackTransportError("invalid checkpoint")
    return ts


def _save_checkpoint(path: Path, ts: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps({"last_ts": ts}, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _history_since(client: SlackHistoryClient, channel_id: str, oldest: str) -> list[dict]:
    messages: list[dict] = []
    cursor: str | None = None
    for _ in range(10):
        page = client.history(channel=channel_id, oldest=oldest, limit=100, cursor=cursor)
        page_messages = page.get("messages", [])
        if not isinstance(page_messages, list):
            raise TradingSlackTransportError("invalid messages payload")
        messages.extend(m for m in page_messages if isinstance(m, dict))
        cursor = (page.get("response_metadata") or {}).get("next_cursor") or None
        if not cursor:
            break
    else:
        raise TradingSlackTransportError("history page limit exceeded")
    return sorted(messages, key=lambda m: m.get("ts", ""))


def poll_slack_trading_decisions(
    engine: Experiment1Engine,
    client: SlackHistoryClient,
    *,
    config: TradingSlackTransportConfig | None = None,
) -> TradingSlackTransportSummary:
    config = config or TradingSlackTransportConfig()
    checkpoint = _load_checkpoint(config.checkpoint_path)

    if checkpoint is None:
        latest = client.history(channel=config.channel_id, limit=1)
        messages = latest.get("messages", [])
        latest_ts = "0"
        if isinstance(messages, list) and messages and isinstance(messages[0], dict):
            latest_ts = str(messages[0].get("ts") or "0")
        _save_checkpoint(config.checkpoint_path, latest_ts)
        return TradingSlackTransportSummary(True, True, len(messages) if isinstance(messages, list) else 0, 0, 0, 0, latest_ts)

    seen = ignored = accepted = rejected = 0
    for message in _history_since(client, config.channel_id, checkpoint):
        ts = str(message.get("ts") or "")
        if not ts or ts <= checkpoint:
            continue
        seen += 1
        text = message.get("text")
        if not (isinstance(text, str) and TRADING_ENVELOPE_MARKER in text):
            ignored += 1
            _save_checkpoint(config.checkpoint_path, ts)
            checkpoint = ts
            continue

        reason = None
        if message.get("user") != config.allowed_user_id:
            reason = "wrong sender"
        elif message.get("channel") not in (None, config.channel_id):
            reason = "wrong channel"
        elif message.get("subtype") is not None:
            reason = "subtype rejected"
        elif message.get("edited") is not None:
            reason = "edited envelope rejected"

        canonical_json = None
        if reason is None:
            try:
                canonical_json = parse_trading_envelope(text)
                if canonical_json is None:
                    reason = "invalid envelope rendering"
            except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                reason = "invalid structured envelope"

        if reason is None and canonical_json is not None:
            try:
                decision = decision_from_json(canonical_json)
                engine.receive_trading_decision(decision.decision_id, canonical_json)
                accepted += 1
            except (Experiment1Error, ValueError, KeyError, TypeError):
                rejected += 1
        else:
            rejected += 1

        _save_checkpoint(config.checkpoint_path, ts)
        checkpoint = ts

    return TradingSlackTransportSummary(True, False, seen, ignored, accepted, rejected, checkpoint)
