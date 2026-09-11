"""
MarketHunter

strategies/breaker.py
"""

from __future__ import annotations

from indicators.breaker_filter import BreakerFilter
from indicators.trend import TrendFilter
from indicators.volume_filter import VolumeFilter
from models.breaker_block import BreakerBlock
from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from strategies.base_strategy import BaseStrategy


class BreakerStrategy(BaseStrategy):

    name = "Breaker"

    def __init__(self) -> None:

        self.breaker = BreakerFilter()
        self.trend = TrendFilter()
        self.volume = VolumeFilter()

    async def analyze(
        self,
        snapshot: MarketSnapshot,
    ) -> Signal | None:

        bullish = self.breaker.latest_bullish(snapshot)

        if (
            bullish is not None
            and self.breaker.inside_bullish(snapshot)
        ):
            return self._build_signal(
                snapshot=snapshot,
                block=bullish,
                direction="LONG",
            )

        bearish = self.breaker.latest_bearish(snapshot)

        if (
            bearish is not None
            and self.breaker.inside_bearish(snapshot)
        ):
            return self._build_signal(
                snapshot=snapshot,
                block=bearish,
                direction="SHORT",
            )

        return None

    def _build_signal(
        self,
        *,
        snapshot: MarketSnapshot,
        block: BreakerBlock,
        direction: str,
    ) -> Signal:

        is_long = direction == "LONG"
        trend = (
            self.trend.bullish(snapshot)
            if is_long
            else self.trend.bearish(snapshot)
        )
        volume = self.volume.bullish(snapshot)

        score = 80

        if trend:
            score += 10

        if volume:
            score += 10

        signal = Signal(
            symbol=snapshot.symbol,
            market="",
            timeframe="1d",
            strategy=self.name,
            direction=direction,
            score=score,
        )

        signal.metadata["breaker_zone_low"] = block.low
        signal.metadata["breaker_zone_high"] = block.high
        signal.metadata["breaker_invalidation_price"] = (
            block.low if is_long else block.high
        )
        signal.metadata["breaker_invalidation_rule"] = (
            "close_below" if is_long else "close_above"
        )

        signal.add_reason(
            "Bullish Breaker Block"
            if is_long
            else "Bearish Breaker Block"
        )

        signal.add_reason(
            f"Zone {block.low:.4f}-{block.high:.4f}"
        )

        if block.retest_index is not None:
            signal.add_reason(
                "Breaker retest confirmed"
            )

        signal.add_reason(
            "Price inside breaker"
        )

        if trend:
            signal.add_reason(
                "Bullish EMA trend"
                if is_long
                else "Bearish EMA trend"
            )

        if volume:
            signal.add_reason(
                f"Volume x{self.volume.ratio(snapshot):.2f}"
            )

        return signal
