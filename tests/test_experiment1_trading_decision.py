from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from experiment1.engine import Experiment1Engine, Experiment1Error
from experiment1.models import (
    AccountKind,
    DecisionAction,
    ExecutionTrigger,
    IntentStatus,
    SizingIntent,
    SizingMode,
    TriggerType,
)
from experiment1.trading_decision import (
    TRADING_ENVELOPE_MARKER,
    TradingDecision,
    decision_from_json,
    decision_id_from,
    decision_to_json,
    ingest_trading_decision,
    intent_id_for,
    to_order_intent,
)


NOW = datetime(2026, 9, 4, 9, 30, tzinfo=timezone.utc)


@pytest.fixture
def engine(tmp_path: Path) -> Experiment1Engine:
    return Experiment1Engine(tmp_path / "experiment1.db")


def _spot(**overrides) -> TradingDecision:
    data = dict(
        decision_id="sl-spot-001",
        decided_at=NOW,
        account=AccountKind.SPOT,
        action=DecisionAction.BUY,
        symbol="BTCUSDT",
        thesis="validated spot setup",
        quantity=Decimal("0.01"),
        leverage=Decimal("1"),
        stop_loss=Decimal("59000"),
        take_profit=Decimal("66000"),
    )
    data.update(overrides)
    return TradingDecision(**data)


def _futures(**overrides) -> TradingDecision:
    data = dict(
        decision_id="sl-futures-001",
        decided_at=NOW,
        account=AccountKind.FUTURES,
        action=DecisionAction.LONG,
        symbol="ETHUSDT",
        thesis="validated futures setup",
        quantity=Decimal("0.2"),
        leverage=Decimal("2"),
        stop_loss=Decimal("3900"),
        take_profit=Decimal("4500"),
    )
    data.update(overrides)
    return TradingDecision(**data)


def test_marker_is_versioned_and_stable():
    assert TRADING_ENVELOPE_MARKER == "TRADING DECISION ENVELOPE v1"


def test_spot_maps_verbatim_to_existing_order_intent():
    decision = _spot()
    intent = to_order_intent(decision)

    assert intent.account is AccountKind.SPOT
    assert intent.action is DecisionAction.BUY
    assert intent.symbol == decision.symbol
    assert intent.quantity == decision.quantity
    assert intent.leverage == Decimal("1")
    assert intent.stop_loss == decision.stop_loss
    assert intent.take_profit == decision.take_profit
    assert decision.decision_id in intent.reason


def test_futures_maps_verbatim_to_existing_order_intent():
    decision = _futures()
    intent = to_order_intent(decision)

    assert intent.account is AccountKind.FUTURES
    assert intent.action is DecisionAction.LONG
    assert intent.leverage == Decimal("2")


def test_spot_rejects_futures_actions():
    with pytest.raises(ValueError, match="SPOT only allows"):
        _spot(action=DecisionAction.LONG)


def test_futures_rejects_spot_actions():
    with pytest.raises(ValueError, match="FUTURES only allows"):
        _futures(action=DecisionAction.BUY)


def test_investments_account_is_rejected():
    with pytest.raises(ValueError, match="SPOT or FUTURES"):
        _spot(account=AccountKind.INVESTMENTS_GROWTH)


def test_spot_rejects_any_leverage_other_than_one():
    with pytest.raises(ValueError, match="1x"):
        _spot(leverage=Decimal("1.5"))


def test_futures_rejects_leverage_above_three():
    with pytest.raises(ValueError, match="3x"):
        _futures(leverage=Decimal("3.01"))


def test_wait_hold_must_be_zero_quantity_and_cannot_carry_sizing():
    wait = _spot(action=DecisionAction.WAIT, quantity=Decimal("0"), stop_loss=None, take_profit=None)
    assert to_order_intent(wait).quantity == 0

    with pytest.raises(ValueError, match="zero quantity"):
        _spot(action=DecisionAction.WAIT, quantity=Decimal("1"))

    with pytest.raises(ValueError, match="cannot carry sizing"):
        _spot(
            action=DecisionAction.HOLD,
            quantity=None,
            sizing=SizingIntent(mode=SizingMode.EXACT_QUANTITY, exact_quantity=Decimal("1")),
            stop_loss=None,
            take_profit=None,
        )


def test_requires_exactly_one_quantity_or_sizing():
    with pytest.raises(ValueError, match="exactly one"):
        _spot(sizing=SizingIntent(mode=SizingMode.EXACT_QUANTITY, exact_quantity=Decimal("0.01")))

    with pytest.raises(ValueError, match="exactly one"):
        _spot(quantity=None)


def test_risk_budget_sizing_requires_stop_loss():
    with pytest.raises(ValueError, match="requires stop_loss"):
        _futures(
            quantity=None,
            stop_loss=None,
            sizing=SizingIntent(
                mode=SizingMode.RISK_BUDGET_FROM_STOP,
                risk_budget_amount=Decimal("20"),
            ),
        )


def test_structured_trigger_round_trip():
    decision = _futures(
        trigger=ExecutionTrigger(
            trigger_type=TriggerType.PRICE_AT_OR_ABOVE,
            trigger_price=Decimal("4200"),
            note="enter only after threshold",
        )
    )
    assert decision_from_json(decision_to_json(decision)) == decision


def test_sizing_round_trip():
    decision = _spot(
        quantity=None,
        sizing=SizingIntent(
            mode=SizingMode.MAX_NOTIONAL,
            max_notional=Decimal("250"),
        ),
    )
    assert decision_from_json(decision_to_json(decision)) == decision


def test_serialization_is_deterministic():
    decision = _spot()
    assert decision_to_json(decision) == decision_to_json(decision)


def test_intent_binding_is_deterministic():
    intent_id = intent_id_for("sl-abc")
    assert intent_id == "trading-decision:sl-abc"
    assert decision_id_from(intent_id) == "sl-abc"
    assert decision_id_from("gil-decision:sl-abc") is None


def test_ingestion_uses_existing_engine_policy_and_creates_no_fill(engine):
    decision = _futures()
    status = ingest_trading_decision(engine, decision)

    assert status is IntentStatus.PENDING
    assert engine.pending_intent_ids() == (intent_id_for(decision.decision_id),)
    assert engine.positions(AccountKind.FUTURES) == ()


def test_ingestion_is_idempotent(engine):
    decision = _spot()
    first = ingest_trading_decision(engine, decision)
    second = ingest_trading_decision(engine, decision)

    assert first is second is IntentStatus.PENDING
    assert len(engine.pending_intent_ids()) == 1


def test_engine_still_blocks_policy_violation_if_contract_is_bypassed(engine):
    # Defense in depth: even if a future caller somehow constructs an
    # invalid intent outside TradingDecision, Experiment1 remains the
    # authoritative policy gate.
    decision = _futures(leverage=Decimal("3"))
    intent = to_order_intent(decision)
    object.__setattr__(intent, "leverage", Decimal("4"))

    with pytest.raises(Experiment1Error, match="3x"):
        engine.submit_intent(intent)
