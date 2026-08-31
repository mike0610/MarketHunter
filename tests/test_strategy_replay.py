from __future__ import annotations

import pytest

from backtesting.strategy_replay import StrategyReplayEngine
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
