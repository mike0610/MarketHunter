from __future__ import annotations

import pytest

from backtesting.strategy_replay import ReplayAssumptions, StrategyReplayEngine
from models.candle import Candle
from models.signal import Signal
from strategies.base_strategy import BaseStrategy


class AlwaysLongStrategy(BaseStrategy):
    name = "AlwaysLongTest"

    async def analyze(self, snapshot):
        return Signal(
            symbol=snapshot.symbol,
            market="futures",
            timeframe="1h",
            strategy=self.name,
            direction="LONG",
            score=100,
        )


def _candles(count: int = 205) -> list[Candle]:
    rows = []
    price = 100.0
    for index in range(count):
        rows.append(
            Candle(
                open_time=index,
                open=price,
                high=price + 2.0,
                low=price - 1.0,
                close=price + 1.0,
                volume=1000.0,
                close_time=index + 1,
            )
        )
        price += 1.0
    return rows


@pytest.mark.asyncio
async def test_strategy_replay_produces_profits():
    profits = await StrategyReplayEngine().run(
        strategy=AlwaysLongStrategy(),
        symbol="BTCUSDT",
        market="futures",
        candles=_candles(),
    )
    assert profits
    assert all(isinstance(value, float) for value in profits)


@pytest.mark.asyncio
async def test_execution_costs_reduce_replay_pnl():
    zero_cost = StrategyReplayEngine(
        ReplayAssumptions(
            fee_bps_per_side=0.0,
            slippage_bps_per_side=0.0,
        )
    )
    with_costs = StrategyReplayEngine(
        ReplayAssumptions(
            fee_bps_per_side=10.0,
            slippage_bps_per_side=10.0,
        )
    )

    zero_profits = await zero_cost.run(
        strategy=AlwaysLongStrategy(),
        symbol="BTCUSDT",
        market="futures",
        candles=_candles(),
    )
    cost_profits = await with_costs.run(
        strategy=AlwaysLongStrategy(),
        symbol="BTCUSDT",
        market="futures",
        candles=_candles(),
    )

    assert len(zero_profits) == len(cost_profits)
    assert sum(cost_profits) < sum(zero_profits)


@pytest.mark.asyncio
async def test_non_overlapping_mode_limits_reentries():
    candles = _candles(210)
    overlapping = StrategyReplayEngine(
        ReplayAssumptions(
            fee_bps_per_side=0.0,
            slippage_bps_per_side=0.0,
            allow_overlapping_positions=True,
        )
    )
    sequential = StrategyReplayEngine(
        ReplayAssumptions(
            fee_bps_per_side=0.0,
            slippage_bps_per_side=0.0,
            allow_overlapping_positions=False,
        )
    )

    overlapping_profits = await overlapping.run(
        strategy=AlwaysLongStrategy(),
        symbol="BTCUSDT",
        market="futures",
        candles=candles,
    )
    sequential_profits = await sequential.run(
        strategy=AlwaysLongStrategy(),
        symbol="BTCUSDT",
        market="futures",
        candles=candles,
    )

    assert len(sequential_profits) <= len(overlapping_profits)
