from datetime import datetime, timezone
from decimal import Decimal

from experiment1.gil_decision import decision_to_json
from experiment1.models import AccountKind, DecisionAction, GilDecision
from experiment1.slack_transport import (
    CHATGPT_CONNECTOR_RENDERED_FOOTER,
    MARKER,
    parse_structured_envelope,
)


def _decision() -> GilDecision:
    return GilDecision(
        decision_id="gil-2026-09-03-crox-growth-tranche-1",
        decided_at=datetime(2026, 9, 3, 4, 13, tzinfo=timezone.utc),
        account=AccountKind.INVESTMENTS_GROWTH,
        action=DecisionAction.BUY,
        symbol="CROX",
        thesis="Slack rendering regression",
        quantity=Decimal("4"),
        reference_close_price=Decimal("115.79"),
    )


def test_parser_accepts_observed_chatgpt_inline_code_rendering():
    decision = _decision()
    payload = decision_to_json(decision)
    text = f"{MARKER}\n`{payload}`\n{CHATGPT_CONNECTOR_RENDERED_FOOTER}"

    assert parse_structured_envelope(text) == payload


def test_parser_accepts_observed_chatgpt_fenced_rendering():
    decision = _decision()
    payload = decision_to_json(decision)
    text = f"{MARKER}\n```{payload}```\n{CHATGPT_CONNECTOR_RENDERED_FOOTER}"

    assert parse_structured_envelope(text) == payload


def test_parser_still_rejects_extra_prose_after_observed_rendering():
    decision = _decision()
    payload = decision_to_json(decision)
    text = f"{MARKER}\n`{payload}`\n{CHATGPT_CONNECTOR_RENDERED_FOOTER}\nextra prose"

    assert parse_structured_envelope(text) is None
