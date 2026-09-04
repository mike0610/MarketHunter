from datetime import datetime, timezone
from decimal import Decimal

import pytest

from experiment1.engine import Experiment1Engine
from experiment1.gil_decision import decision_to_json
from experiment1.models import AccountKind, DecisionAction, GilDecision
from experiment1.slack_transport import (
    CANONICAL_CHANNEL_ID,
    CANONICAL_GIL_USER_ID,
    CHATGPT_CONNECTOR_FOOTER,
    CHATGPT_CONNECTOR_RENDERED_FOOTER,
    MARKER,
    SlackTransportConfig,
    parse_structured_envelope,
    poll_slack_gil_decisions,
)


NOW = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


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


def _wait_decision(decision_id="gil-wait-1"):
    return GilDecision(
        decision_id=decision_id,
        decided_at=NOW,
        account=AccountKind.SPOT,
        action=DecisionAction.WAIT,
        symbol="BTCUSDT",
        thesis="runtime-safe transport proof",
        quantity=Decimal("0"),
    )


def _envelope(decision):
    return f"{MARKER}\n```json\n{decision_to_json(decision)}\n```"


def _connector_envelope(decision, footer=CHATGPT_CONNECTOR_FOOTER):
    return f"{MARKER}\n```{decision_to_json(decision)}```\n{footer}"


def _message(ts, text, **extra):
    result = {
        "ts": ts,
        "user": CANONICAL_GIL_USER_ID,
        "text": text,
        "type": "message",
    }
    result.update(extra)
    return result


def test_parser_ignores_ordinary_gil_research_text():
    assert parse_structured_envelope("GIL EVIDENCE PACKET\nSTATUS: CANDIDATE") is None


def test_parser_requires_entire_message_to_be_machine_envelope():
    decision = _wait_decision()
    assert parse_structured_envelope(f"preface\n{_envelope(decision)}") is None


def test_parser_round_trips_exact_canonical_envelope():
    decision = _wait_decision()
    assert parse_structured_envelope(_envelope(decision)) == decision_to_json(decision)


def test_parser_round_trips_raw_slack_api_connector_rendering():
    decision = _wait_decision("connector-raw-form")
    assert parse_structured_envelope(_connector_envelope(decision)) == decision_to_json(decision)


def test_parser_round_trips_actual_same_line_connector_rendering():
    decision = _wait_decision("connector-same-line-form")
    text = f"{MARKER}\n```{decision_to_json(decision)}``` {CHATGPT_CONNECTOR_FOOTER}"
    assert parse_structured_envelope(text) == decision_to_json(decision)


def test_parser_rejects_same_line_connector_rendering_with_extra_prose():
    decision = _wait_decision("connector-same-line-extra")
    text = f"{MARKER}\n```{decision_to_json(decision)}``` {CHATGPT_CONNECTOR_FOOTER} extra prose"
    assert parse_structured_envelope(text) is None


def test_parser_round_trips_enriched_connector_read_rendering():
    decision = _wait_decision("connector-rendered-form")
    text = _connector_envelope(decision, CHATGPT_CONNECTOR_RENDERED_FOOTER)
    assert parse_structured_envelope(text) == decision_to_json(decision)


def test_parser_rejects_connector_form_with_extra_prose():
    decision = _wait_decision("connector-extra")
    assert parse_structured_envelope(f"{_connector_envelope(decision)}\nextra prose") is None


def test_parser_rejects_connector_form_with_lookalike_footer():
    decision = _wait_decision("connector-fake-footer")
    text = f"{MARKER}\n```{decision_to_json(decision)}```\n*Sent using* <@UOTHER|ChatGPT>"
    assert parse_structured_envelope(text) is None


def test_parser_rejects_malformed_connector_json():
    text = f'{MARKER}\n```{{"decision_id":}}```\n{CHATGPT_CONNECTOR_FOOTER}'
    with pytest.raises(Exception):
        parse_structured_envelope(text)


def test_first_poll_bootstraps_without_backfilling_historic_messages(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    client = FakeSlackClient([_message("100.000001", _envelope(_wait_decision("historic")))])
    config = SlackTransportConfig(checkpoint_path=tmp_path / "checkpoint.json")

    summary = poll_slack_gil_decisions(engine, client, config=config)

    assert summary.bootstrapped is True
    assert summary.accepted == 0
    assert engine.gil_decision_inbox_status("historic") is None


def test_ordinary_new_slack_text_is_ignored_and_checkpointed(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    config = SlackTransportConfig(checkpoint_path=tmp_path / "checkpoint.json")
    bootstrap = FakeSlackClient([_message("100.000001", "existing research")])
    poll_slack_gil_decisions(engine, bootstrap, config=config)

    client = FakeSlackClient([
        _message("100.000001", "existing research"),
        _message("101.000001", "GIL EVIDENCE PACKET\nCANDIDATE / WAIT"),
    ])
    summary = poll_slack_gil_decisions(engine, client, config=config)

    assert summary.ordinary_ignored == 1
    assert summary.accepted == 0
    assert summary.checkpoint == "101.000001"


def test_exact_wait_envelope_is_forwarded_to_existing_durable_inbox(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    config = SlackTransportConfig(checkpoint_path=tmp_path / "checkpoint.json")
    poll_slack_gil_decisions(engine, FakeSlackClient([]), config=config)

    decision = _wait_decision("gil-new-wait")
    summary = poll_slack_gil_decisions(
        engine, FakeSlackClient([_message("101.000001", _envelope(decision))]), config=config
    )

    assert summary.accepted == 1
    record = engine.gil_decision_inbox_status(decision.decision_id)
    assert record is not None
    assert record.status.value == "PENDING_DRAIN"


def test_connector_wait_envelope_is_forwarded_to_existing_durable_inbox(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    config = SlackTransportConfig(checkpoint_path=tmp_path / "checkpoint.json")
    poll_slack_gil_decisions(engine, FakeSlackClient([]), config=config)

    decision = _wait_decision("gil-connector-wait")
    summary = poll_slack_gil_decisions(
        engine,
        FakeSlackClient([_message("101.000001", _connector_envelope(decision))]),
        config=config,
    )

    assert summary.accepted == 1
    record = engine.gil_decision_inbox_status(decision.decision_id)
    assert record is not None
    assert record.status.value == "PENDING_DRAIN"


def test_wrong_sender_marker_is_rejected_never_forwarded(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    config = SlackTransportConfig(checkpoint_path=tmp_path / "checkpoint.json")
    poll_slack_gil_decisions(engine, FakeSlackClient([]), config=config)
    decision = _wait_decision("wrong-user")
    message = _message("101.000001", _envelope(decision), user="UOTHER")

    summary = poll_slack_gil_decisions(engine, FakeSlackClient([message]), config=config)

    assert summary.rejected == 1
    assert engine.gil_decision_inbox_status(decision.decision_id) is None


def test_edited_machine_envelope_is_rejected(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    config = SlackTransportConfig(checkpoint_path=tmp_path / "checkpoint.json")
    poll_slack_gil_decisions(engine, FakeSlackClient([]), config=config)
    decision = _wait_decision("edited")
    message = _message(
        "101.000001",
        _envelope(decision),
        edited={"user": CANONICAL_GIL_USER_ID, "ts": "101.100001"},
    )

    summary = poll_slack_gil_decisions(engine, FakeSlackClient([message]), config=config)

    assert summary.rejected == 1
    assert engine.gil_decision_inbox_status(decision.decision_id) is None


def test_marker_with_research_state_candidate_fails_closed(tmp_path):
    engine = Experiment1Engine(tmp_path / "experiment1.db")
    config = SlackTransportConfig(checkpoint_path=tmp_path / "checkpoint.json")
    poll_slack_gil_decisions(engine, FakeSlackClient([]), config=config)
    raw = decision_to_json(_wait_decision("candidate-test")).replace('"WAIT"', '"CANDIDATE"')

    summary = poll_slack_gil_decisions(
        engine,
        FakeSlackClient([_message("101.000001", f"{MARKER}\n```json\n{raw}\n```")]),
        config=config,
    )

    assert summary.rejected == 1
    assert engine.gil_decision_inbox_status("candidate-test") is None


def test_replay_after_checkpoint_loss_is_idempotent_by_decision_id(tmp_path):
    db_path = tmp_path / "experiment1.db"
    checkpoint = tmp_path / "checkpoint.json"
    engine = Experiment1Engine(db_path)
    config = SlackTransportConfig(checkpoint_path=checkpoint)
    poll_slack_gil_decisions(engine, FakeSlackClient([]), config=config)
    decision = _wait_decision("replay-safe")
    message = _message("101.000001", _envelope(decision))

    first = poll_slack_gil_decisions(engine, FakeSlackClient([message]), config=config)
    assert first.accepted == 1

    checkpoint.unlink()
    poll_slack_gil_decisions(engine, FakeSlackClient([]), config=config)
    second = poll_slack_gil_decisions(engine, FakeSlackClient([message]), config=config)
    assert second.accepted == 1
    assert engine.gil_decision_inbox_status("replay-safe") is not None


def test_config_refuses_noncanonical_channel_or_sender(tmp_path):
    with pytest.raises(Exception):
        SlackTransportConfig(channel_id="COTHER", checkpoint_path=tmp_path / "x")
    with pytest.raises(Exception):
        SlackTransportConfig(allowed_user_id="UOTHER", checkpoint_path=tmp_path / "x")
