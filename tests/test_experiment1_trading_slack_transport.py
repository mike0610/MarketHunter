from datetime import datetime, timezone
from decimal import Decimal

import pytest

from experiment1.engine import Experiment1Engine
from experiment1.models import AccountKind, DecisionAction
from experiment1.trading_decision import TRADING_ENVELOPE_MARKER, TradingDecision, decision_to_json
from experiment1.trading_slack_transport import (
    CANONICAL_CHANNEL_ID,
    CANONICAL_STRATEGY_USER_ID,
    CHATGPT_CONNECTOR_FOOTER,
    CHATGPT_CONNECTOR_RENDERED_FOOTER,
    TradingSlackTransportConfig,
    parse_trading_envelope,
    poll_slack_trading_decisions,
)

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
FENCE = chr(96) * 3


class FakeSlackClient:
    def __init__(self, messages):
        self.messages = list(messages)

    def history(self, *, channel, oldest=None, limit=100, cursor=None):
        assert channel == CANONICAL_CHANNEL_ID
        selected = self.messages
        if oldest is not None:
            selected = [m for m in selected if m["ts"] > oldest]
        selected = sorted(selected, key=lambda m: m["ts"], reverse=True)[:limit]
        return {"ok": True, "messages": selected, "response_metadata": {"next_cursor": ""}}


def decision(decision_id="sl-1"):
    return TradingDecision(
        decision_id=decision_id,
        decided_at=NOW,
        account=AccountKind.FUTURES,
        action=DecisionAction.LONG,
        symbol="ETHUSDT",
        thesis="validated setup",
        quantity=Decimal("0.1"),
        leverage=Decimal("2"),
        stop_loss=Decimal("3900"),
        take_profit=Decimal("4500"),
    )


def envelope(d):
    return "{}\n{}json\n{}\n{}".format(
        TRADING_ENVELOPE_MARKER, FENCE, decision_to_json(d), FENCE
    )


def connector_envelope(d, footer=CHATGPT_CONNECTOR_FOOTER):
    return "{}\n{}{}{} {}".format(
        TRADING_ENVELOPE_MARKER, FENCE, decision_to_json(d), FENCE, footer
    )


def message(ts, text, **extra):
    result = {"ts": ts, "user": CANONICAL_STRATEGY_USER_ID, "text": text, "type": "message"}
    result.update(extra)
    return result


def test_parser_ignores_ordinary_strategy_lab_text():
    assert parse_trading_envelope("SL-VAL-RISK-009\nSTATUS: HOLD") is None


def test_parser_round_trips_canonical_and_connector_forms():
    d = decision()
    assert parse_trading_envelope(envelope(d)) == decision_to_json(d)
    assert parse_trading_envelope(connector_envelope(d)) == decision_to_json(d)
    assert parse_trading_envelope(
        connector_envelope(d, CHATGPT_CONNECTOR_RENDERED_FOOTER)
    ) == decision_to_json(d)


def test_parser_rejects_extra_prose():
    d = decision()
    assert parse_trading_envelope(connector_envelope(d) + "\nextra") is None


def test_first_poll_bootstraps_without_backfill(tmp_path):
    engine = Experiment1Engine(tmp_path / "db.sqlite")
    config = TradingSlackTransportConfig(checkpoint_path=tmp_path / "cp.json")
    summary = poll_slack_trading_decisions(
        engine,
        FakeSlackClient([message("100.0", envelope(decision("historic")))]),
        config=config,
    )
    assert summary.bootstrapped is True
    assert engine.trading_decision_inbox_status("historic") is None


def test_new_envelope_goes_to_trading_inbox(tmp_path):
    engine = Experiment1Engine(tmp_path / "db.sqlite")
    config = TradingSlackTransportConfig(checkpoint_path=tmp_path / "cp.json")
    poll_slack_trading_decisions(engine, FakeSlackClient([]), config=config)

    d = decision("new-1")
    summary = poll_slack_trading_decisions(
        engine,
        FakeSlackClient([message("101.0", envelope(d))]),
        config=config,
    )
    assert summary.accepted == 1
    assert engine.trading_decision_inbox_status("new-1").status.value == "PENDING_DRAIN"


def test_wrong_sender_and_edited_are_rejected(tmp_path):
    engine = Experiment1Engine(tmp_path / "db.sqlite")
    config = TradingSlackTransportConfig(checkpoint_path=tmp_path / "cp.json")
    poll_slack_trading_decisions(engine, FakeSlackClient([]), config=config)

    d1 = decision("bad-sender")
    s1 = poll_slack_trading_decisions(
        engine,
        FakeSlackClient([message("101.0", envelope(d1), user="UOTHER")]),
        config=config,
    )
    assert s1.rejected == 1
    assert engine.trading_decision_inbox_status("bad-sender") is None

    d2 = decision("edited")
    s2 = poll_slack_trading_decisions(
        engine,
        FakeSlackClient([message("102.0", envelope(d2), edited={"ts": "102.1"})]),
        config=config,
    )
    assert s2.rejected == 1
    assert engine.trading_decision_inbox_status("edited") is None


def test_replay_after_checkpoint_loss_is_idempotent(tmp_path):
    engine = Experiment1Engine(tmp_path / "db.sqlite")
    cp = tmp_path / "cp.json"
    config = TradingSlackTransportConfig(checkpoint_path=cp)
    poll_slack_trading_decisions(engine, FakeSlackClient([]), config=config)

    d = decision("replay")
    m = message("101.0", envelope(d))
    assert poll_slack_trading_decisions(engine, FakeSlackClient([m]), config=config).accepted == 1

    cp.unlink()
    poll_slack_trading_decisions(engine, FakeSlackClient([]), config=config)
    assert poll_slack_trading_decisions(engine, FakeSlackClient([m]), config=config).accepted == 1
    assert engine.trading_decision_inbox_status("replay") is not None


def test_config_is_hard_allowlisted(tmp_path):
    with pytest.raises(Exception):
        TradingSlackTransportConfig(channel_id="COTHER", checkpoint_path=tmp_path / "x")
    with pytest.raises(Exception):
        TradingSlackTransportConfig(allowed_user_id="UOTHER", checkpoint_path=tmp_path / "x")
