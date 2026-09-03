import json

from experiment1.slack_transport import MARKER, _diagnostic_text_repr, parse_structured_envelope


def _payload() -> dict:
    return {
        "decision_id": "gil-test-plain-envelope-1",
        "decided_at": "2026-09-03T04:13:00+00:00",
        "account": "INVESTMENTS_GROWTH",
        "action": "BUY",
        "symbol": "CROX",
        "thesis": "Strict plain Slack serialization regression test.",
        "quantity": "4",
        "leverage": None,
        "stop_loss": None,
        "take_profit": None,
        "execution_condition": None,
        "trigger": None,
        "sizing": None,
        "reference_close_price": "115.79",
    }


def test_plain_slack_rendering_is_accepted() -> None:
    text = f"{MARKER}\n{json.dumps(_payload(), separators=(',', ':'))}"
    parsed = parse_structured_envelope(text)
    assert parsed is not None
    assert json.loads(parsed)["decision_id"] == "gil-test-plain-envelope-1"


def test_plain_slack_rendering_with_trailing_prose_is_rejected() -> None:
    text = f"{MARKER}\n{json.dumps(_payload(), separators=(',', ':'))}\nextra prose"
    assert parse_structured_envelope(text) is None


def test_rejected_slack_text_diagnostic_is_escaped_and_bounded() -> None:
    text = f"{MARKER}\r\n{{\"decision_id\":\"x\"}}\nextra prose"
    diagnostic = _diagnostic_text_repr(text)
    assert "\\r\\n" in diagnostic
    assert "\\nextra prose" in diagnostic
    assert "\n" not in diagnostic

    bounded = _diagnostic_text_repr("x" * 5000, limit=80)
    assert bounded.startswith("'" + "x" * 79)
    assert "<truncated " in bounded


def test_diagnostic_helper_does_not_change_rejection_logic() -> None:
    text = f"{MARKER}\n{json.dumps(_payload(), separators=(',', ':'))}\nextra prose"
    before = parse_structured_envelope(text)
    _diagnostic_text_repr(text)
    after = parse_structured_envelope(text)
    assert before is None
    assert after is None
