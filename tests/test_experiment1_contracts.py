from datetime import datetime, timezone
from decimal import Decimal

import pytest

from simulation.experiment1 import (
    ExperimentAccount,
    ExperimentAccountKind,
    OrderIntent,
    OrderSide,
    OrderType,
)


def make_intent(**overrides):
    values = dict(
        intent_id="intent-1",
        account_id="spot-1",
        portfolio_id="experiment-1",
        strategy_id="gil-1",
        instrument_id="BTCUSDT",
        asset_class="crypto",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        target_notional=Decimal("500"),
        max_risk=Decimal("25"),
    )
    values.update(overrides)
    return OrderIntent(**values)


def test_three_accounts_can_start_independently_at_5000():
    for kind, leverage in (
        (ExperimentAccountKind.INVESTMENTS, False),
        (ExperimentAccountKind.SPOT, False),
        (ExperimentAccountKind.FUTURES, True),
    ):
        account = ExperimentAccount(
            account_id=kind.value,
            portfolio_id="experiment-1",
            kind=kind,
            starting_cash=Decimal("5000"),
            leverage_allowed=leverage,
        )
        assert account.starting_cash == Decimal("5000")


def test_non_futures_account_rejects_leverage():
    with pytest.raises(ValueError):
        ExperimentAccount(
            account_id="spot",
            portfolio_id="experiment-1",
            kind=ExperimentAccountKind.SPOT,
            starting_cash=Decimal("5000"),
            leverage_allowed=True,
        )


def test_intent_requires_exactly_one_sizing_instruction():
    with pytest.raises(ValueError):
        make_intent(quantity=Decimal("1"))
    with pytest.raises(ValueError):
        make_intent(target_notional=None)


def test_limit_and_stop_require_their_prices():
    with pytest.raises(ValueError):
        make_intent(order_type=OrderType.LIMIT)
    with pytest.raises(ValueError):
        make_intent(order_type=OrderType.STOP)


def test_intent_contains_no_fill_price_or_execution_defaults():
    intent = make_intent()
    assert not hasattr(intent, "fill_price")
    assert not hasattr(intent, "fee")
    assert not hasattr(intent, "slippage")
    assert not hasattr(intent, "funding")
