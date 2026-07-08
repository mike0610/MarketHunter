"""
MarketHunter

strategies/order_block.py
"""

from __future__ import annotations

from typing import Any

from indicators.order_block_filter import OrderBlockFilter
from indicators.trend import TrendFilter
from indicators.volume_filter import VolumeFilter
from models.market_snapshot import MarketSnapshot
from models.order_block import OrderBlock
from models.signal import Signal
from strategies.base_strategy import BaseStrategy


class OrderBlockStrategy(BaseStrategy):
    """
    Order Block strategy.

    LONG:
    - latest bullish Order Block exists
    - bullish trend and bullish volume increase score

    SHORT:
    - latest bearish Order Block exists
    - bearish trend and bearish volume increase score
    """

    name = "OrderBlock"

    MAX_ZONE_DISTANCE_ATR = 1.0
    MAX_ZONE_DISTANCE_PERCENT = 2.0

    MAX_ZONE_DISTANCE_ATR = 1.0
    MAX_ZONE_DISTANCE_PERCENT = 2.0

    def __init__(self) -> None:
        self.order_block = OrderBlockFilter()
        self.trend = TrendFilter()
        self.volume = VolumeFilter()

    async def analyze(
        self,
        snapshot: MarketSnapshot,
    ) -> Signal | None:
        bullish_block = self.order_block.latest_bullish(
            snapshot,
        )

        bearish_block = self.order_block.latest_bearish(
            snapshot,
        )

        bullish_block = self._close_block_or_none(
            snapshot=snapshot,
            block=bullish_block,
        )
        bearish_block = self._close_block_or_none(
            snapshot=snapshot,
            block=bearish_block,
        )

        if bullish_block is None and bearish_block is None:
            return None

        if self._should_use_short(
            snapshot,
            bullish_block,
            bearish_block,
        ):
            return self._build_short_signal(
                snapshot,
                bearish_block,
            )

        if bullish_block is not None:
            return self._build_long_signal(
                snapshot,
                bullish_block,
            )

        if bearish_block is not None:
            return self._build_short_signal(
                snapshot,
                bearish_block,
            )

        return None

    def _build_long_signal(
        self,
        snapshot: MarketSnapshot,
        block: OrderBlock,
    ) -> Signal | None:
        score = 75

        trend_ok = self._call_bool(
            self.trend,
            "bullish",
            snapshot,
        )

        volume_ok = self._call_bool(
            self.volume,
            "bullish",
            snapshot,
        )

        inside_block = self._block_contains(
            snapshot,
            block,
        )

        distance = self._block_distance(
            snapshot=snapshot,
            block=block,
        )

        if not self._zone_is_close(
            snapshot=snapshot,
            distance=distance,
        ):
            return None

        if trend_ok:
            score += 10

        if volume_ok:
            score += 10

        if inside_block:
            score += 5

        signal = Signal(
            symbol=snapshot.symbol,
            market=self._snapshot_value(
                snapshot,
                "market",
                "",
            ),
            timeframe=self._snapshot_value(
                snapshot,
                "timeframe",
                "1d",
            ),
            strategy=self.name,
            direction="LONG",
            score=score,
        )

        signal.add_reason(
            "Bullish Order Block"
        )

        signal.add_reason(
            f"Zone {block.low:.4f} - {block.high:.4f}"
        )

        signal.add_reason(
            f"Distance {self._distance_percent(snapshot, distance):.2f}%"
        )

        if inside_block:
            signal.add_reason(
                "Price inside Bullish Order Block"
            )

        if trend_ok:
            signal.add_reason(
                "Bullish EMA trend"
            )

        if volume_ok:
            volume_ratio = self._call_number(
                self.volume,
                "ratio",
                snapshot,
            )

            if volume_ratio is None:
                signal.add_reason(
                    "Bullish volume confirmation"
                )
            else:
                signal.add_reason(
                    f"Volume x{volume_ratio:.2f}"
                )

        return signal

    def _build_short_signal(
        self,
        snapshot: MarketSnapshot,
        block: OrderBlock | None,
    ) -> Signal | None:
        if block is None:
            return None

        score = 75

        trend_ok = self._call_bool(
            self.trend,
            "bearish",
            snapshot,
        )

        volume_ok = self._call_bool(
            self.volume,
            "bearish",
            snapshot,
        )

        inside_block = self._block_contains(
            snapshot,
            block,
        )

        distance = self._block_distance(
            snapshot=snapshot,
            block=block,
        )

        if not self._zone_is_close(
            snapshot=snapshot,
            distance=distance,
        ):
            return None

        if trend_ok:
            score += 10

        if volume_ok:
            score += 10

        if inside_block:
            score += 5

        signal = Signal(
            symbol=snapshot.symbol,
            market=self._snapshot_value(
                snapshot,
                "market",
                "",
            ),
            timeframe=self._snapshot_value(
                snapshot,
                "timeframe",
                "1d",
            ),
            strategy=self.name,
            direction="SHORT",
            score=score,
        )

        signal.add_reason(
            "Bearish Order Block"
        )

        signal.add_reason(
            f"Zone {block.low:.4f} - {block.high:.4f}"
        )

        signal.add_reason(
            f"Distance {self._distance_percent(snapshot, distance):.2f}%"
        )

        if inside_block:
            signal.add_reason(
                "Price inside Bearish Order Block"
            )

        if trend_ok:
            signal.add_reason(
                "Bearish EMA trend"
            )

        if volume_ok:
            volume_ratio = self._call_number(
                self.volume,
                "ratio",
                snapshot,
            )

            if volume_ratio is None:
                signal.add_reason(
                    "Bearish volume confirmation"
                )
            else:
                signal.add_reason(
                    f"Volume x{volume_ratio:.2f}"
                )

        return signal

    def _close_block_or_none(
        self,
        *,
        snapshot: MarketSnapshot,
        block: OrderBlock | None,
    ) -> OrderBlock | None:
        if block is None:
            return None

        distance = self._block_distance(
            snapshot=snapshot,
            block=block,
        )

        if not self._zone_is_close(
            snapshot=snapshot,
            distance=distance,
        ):
            return None

        return block

    @staticmethod
    def _block_distance(
        *,
        snapshot: MarketSnapshot,
        block: OrderBlock,
    ) -> float:
        if not snapshot.candles:
            return 0.0

        close = snapshot.candles[-1].close

        if block.low <= close <= block.high:
            return 0.0

        if close < block.low:
            return block.low - close

        return close - block.high

    @classmethod
    def _zone_is_close(
        cls,
        *,
        snapshot: MarketSnapshot,
        distance: float,
    ) -> bool:
        if distance <= 0:
            return True

        distance_percent = cls._distance_percent(
            snapshot,
            distance,
        )

        if distance_percent > cls.MAX_ZONE_DISTANCE_PERCENT:
            return False

        if snapshot.atr14 <= 0:
            return True

        return (
            distance / snapshot.atr14
            <= cls.MAX_ZONE_DISTANCE_ATR
        )

    @staticmethod
    def _distance_percent(
        snapshot: MarketSnapshot,
        distance: float,
    ) -> float:
        if not snapshot.candles:
            return 0.0

        close = snapshot.candles[-1].close

        if close <= 0:
            return 0.0

        return distance / close * 100

    def _should_use_short(
        self,
        snapshot: MarketSnapshot,
        bullish_block: OrderBlock | None,
        bearish_block: OrderBlock | None,
    ) -> bool:
        if bearish_block is None:
            return False

        if bullish_block is None:
            return True

        bearish_trend = self._call_bool(
            self.trend,
            "bearish",
            snapshot,
        )

        bullish_trend = self._call_bool(
            self.trend,
            "bullish",
            snapshot,
        )

        if bearish_trend and not bullish_trend:
            return True

        if bullish_trend and not bearish_trend:
            return False

        inside_bearish = self._block_contains(
            snapshot,
            bearish_block,
        )

        inside_bullish = self._block_contains(
            snapshot,
            bullish_block,
        )

        if inside_bearish and not inside_bullish:
            return True

        return False

    @staticmethod
    def _block_contains(
        snapshot: MarketSnapshot,
        block: OrderBlock,
    ) -> bool:
        if not snapshot.candles:
            return False

        close_price = snapshot.candles[-1].close

        return bool(
            block.contains(close_price)
        )

    @staticmethod
    def _snapshot_value(
        snapshot: MarketSnapshot,
        name: str,
        default: str,
    ) -> str:
        value = getattr(
            snapshot,
            name,
            default,
        )

        if value is None:
            return default

        return str(value)

    @staticmethod
    def _call_bool(
        target: Any,
        method_name: str,
        snapshot: MarketSnapshot,
    ) -> bool:
        method = getattr(
            target,
            method_name,
            None,
        )

        if method is None:
            return False

        return bool(
            method(snapshot)
        )

    @staticmethod
    def _call_number(
        target: Any,
        method_name: str,
        snapshot: MarketSnapshot,
    ) -> float | None:
        method = getattr(
            target,
            method_name,
            None,
        )

        if method is None:
            return None

        value = method(snapshot)

        if value is None:
            return None

        try:
            return float(value)
        except (
            TypeError,
            ValueError,
        ):
            return None