from __future__ import annotations

from backtesting.trade_simulator import ExecutionAssumptions, TradeSimulator
from models.candle import Candle
from models.position import Position


def _position(side: str = "LONG") -> Position:
    return Position(
        symbol="BTCUSDT",
        market="futures",
        side=side,
        quantity=1.0,
        entry=100.0,
        stop_loss=95.0 if side == "LONG" else 105.0,
        take_profit=110.0 if side == "LONG" else 90.0,
        opened_at=0.0,
        current_price=100.0,
    )


def _candle(low: float, high: float, close: float = 100.0) -> Candle:
    return Candle(
        open_time=0,
        open=100.0,
        high=high,
        low=low,
        close=close,
        volume=1000.0,
        close_time=1,
    )


def test_same_candle_uses_conservative_stop_by_default():
    result = TradeSimulator(
        ExecutionAssumptions(fee_bps_per_side=0, slippage_bps_per_side=0)
    ).long(_position("LONG"), [_candle(low=94.0, high=111.0)])

    assert result.exit_reason == "stop"
    assert result.pnl == -5.0


def test_same_candle_can_be_run_as_optimistic_sensitivity_case():
    result = TradeSimulator(
        ExecutionAssumptions(
            fee_bps_per_side=0,
            slippage_bps_per_side=0,
            ambiguous_candle_policy="target_first",
        )
    ).long(_position("LONG"), [_candle(low=94.0, high=111.0)])

    assert result.exit_reason == "target"
    assert result.pnl == 10.0


def test_fees_and_slippage_are_adverse_for_long_trade():
    clean = TradeSimulator(
        ExecutionAssumptions(fee_bps_per_side=0, slippage_bps_per_side=0)
    ).long(_position("LONG"), [_candle(low=99.0, high=111.0)])
    costly = TradeSimulator(
        ExecutionAssumptions(fee_bps_per_side=10, slippage_bps_per_side=10)
    ).long(_position("LONG"), [_candle(low=99.0, high=111.0)])

    assert costly.pnl < clean.pnl
    assert costly.fees > 0
    assert costly.entry_fill > 100.0
    assert costly.exit_fill < 110.0


def test_short_trade_applies_adverse_execution_costs():
    result = TradeSimulator(
        ExecutionAssumptions(fee_bps_per_side=10, slippage_bps_per_side=10)
    ).short(_position("SHORT"), [_candle(low=89.0, high=101.0)])

    assert result.exit_reason == "target"
    assert result.fees > 0
    assert result.entry_fill < 100.0
    assert result.exit_fill > 90.0
    assert result.pnl < 10.0
