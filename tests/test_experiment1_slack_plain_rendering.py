import json

from experiment1.slack_transport import MARKER, parse_structured_envelope


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
