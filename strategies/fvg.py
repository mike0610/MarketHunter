"""
MarketHunter

strategies/fvg.py
"""

from __future__ import annotations

from typing import Any

from indicators.fvg_filter import FVGFilter
from indicators.trend import TrendFilter
from indicators.volume_filter import VolumeFilter
from models.fvg import FVG
from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from strategies.base_strategy import BaseStrategy


class FVGStrategy(BaseStrategy):
    """
    Fair Value Gap strategy.

    LONG:
    - latest bullish FVG exists
    - bullish trend and bullish volume increase score

    SHORT:
    - latest bearish FVG exists
    - bearish trend and bearish volume increase score
    """

    name = "FVG"

    MAX_ZONE_DISTANCE_ATR = 1.0
    MAX_ZONE_DISTANCE_PERCENT = 2.0

    def __init__(self) -> None:
        self.trend = TrendFilter()
        self.volume = VolumeFilter()
        self.fvg = FVGFilter()

    async def analyze(
        self,
        snapshot: MarketSnapshot,
    ) -> Signal | None:
        bullish_gap = self.fvg.latest_bullish(snapshot)

        if bullish_gap is not None:
            return self._build_long_signal(
                snapshot,
                bullish_gap,
            )

        bearish_gap = self.fvg.latest_bearish(snapshot)

        if bearish_gap is not None:
            return self._build_short_signal(
                snapshot,
                bearish_gap,
            )

        return None

    def _build_long_signal(
        self,
        snapshot: MarketSnapshot,
        gap: FVG,
    ) -> Signal | None:
        score = 70

        distance = self._distance_to_zone(
            snapshot=snapshot,
            lower=gap.lower,
            upper=gap.upper,
        )

        if not self._zone_is_close(
            snapshot=snapshot,
            distance=distance,
        ):
            return None

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

        if trend_ok:
            score += 15

        if volume_ok:
            score += 15

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
            "Bullish Fair Value Gap"
        )

        signal.add_reason(
            f"Gap {gap.lower:.4f} - {gap.upper:.4f}"
        )

        signal.add_reason(
            f"Gap Size {gap.percent:.2f}%"
        )

        signal.add_reason(
            f"Distance {self._distance_percent(snapshot, distance):.2f}%"
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
        gap: FVG,
    ) -> Signal | None:
        score = 70

        distance = self._distance_to_zone(
            snapshot=snapshot,
            lower=gap.lower,
            upper=gap.upper,
        )

        if not self._zone_is_close(
            snapshot=snapshot,
            distance=distance,
        ):
            return None

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

        if trend_ok:
            score += 15

        if volume_ok:
            score += 15

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
            "Bearish Fair Value Gap"
        )

        signal.add_reason(
            f"Gap {gap.lower:.4f} - {gap.upper:.4f}"
        )

        signal.add_reason(
            f"Gap Size {gap.percent:.2f}%"
        )

        signal.add_reason(
            f"Distance {self._distance_percent(snapshot, distance):.2f}%"
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

    @staticmethod
    def _distance_to_zone(
        *,
        snapshot: MarketSnapshot,
        lower: float,
        upper: float,
    ) -> float:
        if not snapshot.candles:
            return 0.0

        close = snapshot.candles[-1].close

        if lower <= close <= upper:
            return 0.0

        if close < lower:
            return lower - close

        return close - upper

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