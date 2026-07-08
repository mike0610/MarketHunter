"""
MarketHunter

strategies/premium_discount.py
"""

from __future__ import annotations

from typing import Any

from indicators.premium_discount_filter import (
    PremiumDiscountFilter,
)
from indicators.trend import TrendFilter
from indicators.volume_filter import VolumeFilter
from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from strategies.base_strategy import BaseStrategy


class PremiumDiscountStrategy(BaseStrategy):
    """
    ICT Premium / Discount strategy.

    LONG:
    - price is in Discount zone
    - bullish trend and bullish volume increase score

    SHORT:
    - price is in Premium zone
    - bearish trend and bearish volume increase score
    """

    name = "PremiumDiscount"

    def __init__(self) -> None:
        self.zone = PremiumDiscountFilter()
        self.trend = TrendFilter()
        self.volume = VolumeFilter()

    async def analyze(
        self,
        snapshot: MarketSnapshot,
    ) -> Signal | None:
        if self.zone.in_discount(snapshot):
            return self._build_long_signal(snapshot)

        if self._in_premium(snapshot):
            return self._build_short_signal(snapshot)

        return None

    def _build_long_signal(
        self,
        snapshot: MarketSnapshot,
    ) -> Signal:
        score = 70

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
            "Price in Discount Zone"
        )

        discount_percent = self._call_number(
            self.zone,
            "discount_percent",
            snapshot,
        )

        if discount_percent is not None:
            signal.add_reason(
                f"Discount {discount_percent:.1f}%"
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
    ) -> Signal:
        score = 70

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
            "Price in Premium Zone"
        )

        premium_percent = self._call_number(
            self.zone,
            "premium_percent",
            snapshot,
        )

        if premium_percent is not None:
            signal.add_reason(
                f"Premium {premium_percent:.1f}%"
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

    def _in_premium(
        self,
        snapshot: MarketSnapshot,
    ) -> bool:
        return self._call_bool(
            self.zone,
            "in_premium",
            snapshot,
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