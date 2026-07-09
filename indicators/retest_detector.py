"""
MarketHunter

Module:
Retest Detector

Detects:
- Breakout above resistance -> retest level -> bullish rejection
- Breakdown below support -> retest level -> bearish rejection
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from models.candle import Candle


RetestKind = Literal[
    "bullish_retest",
    "bearish_retest",
]


@dataclass(slots=True)
class RetestSignal:
    kind: RetestKind
    direction: str
    level: float
    breakout_index: int
    retest_index: int
    tolerance_percent: float
    breakout_close: float
    retest_close: float


class RetestDetector:
    """
    Confirms that price broke a level, returned to it, and rejected it.

    LONG:
    price closes above resistance, later retests that level from above,
    and closes bullish above the level.

    SHORT:
    price closes below support, later retests that level from below,
    and closes bearish below the level.
    """

    def __init__(
        self,
        *,
        level_lookback: int = 20,
        max_bars_after_breakout: int = 12,
        tolerance_percent: float = 0.25,
        require_rejection_candle: bool = True,
    ) -> None:
        if level_lookback < 5:
            raise ValueError(
                "Retest level lookback must be at least 5 candles."
            )

        if max_bars_after_breakout < 1:
            raise ValueError(
                "Max bars after breakout must be positive."
            )

        if tolerance_percent <= 0:
            raise ValueError(
                "Retest tolerance must be positive."
            )

        self.level_lookback = level_lookback
        self.max_bars_after_breakout = max_bars_after_breakout
        self.tolerance_percent = tolerance_percent
        self.require_rejection_candle = require_rejection_candle

    def bullish(
        self,
        candles: list[Candle],
    ) -> bool:
        return self.latest_bullish(candles) is not None

    def bearish(
        self,
        candles: list[Candle],
    ) -> bool:
        return self.latest_bearish(candles) is not None

    def latest_bullish(
        self,
        candles: list[Candle],
    ) -> RetestSignal | None:
        if len(candles) < self.level_lookback + 3:
            return None

        retest_index = len(candles) - 1
        retest = candles[retest_index]

        start = max(
            self.level_lookback,
            retest_index - self.max_bars_after_breakout,
        )

        for breakout_index in range(
            retest_index - 1,
            start - 1,
            -1,
        ):
            previous = candles[
                breakout_index - self.level_lookback
                : breakout_index
            ]

            if not previous:
                continue

            level = max(
                candle.high
                for candle in previous
            )

            tolerance = self._tolerance(level)
            breakout = candles[breakout_index]

            if breakout.close <= level:
                continue

            if self._bullish_invalidated(
                candles=candles[
                    breakout_index + 1
                    : retest_index
                ],
                level=level,
                tolerance=tolerance,
            ):
                continue

            if not self._bullish_retest(
                candle=retest,
                level=level,
                tolerance=tolerance,
            ):
                continue

            return RetestSignal(
                kind="bullish_retest",
                direction="LONG",
                level=level,
                breakout_index=breakout_index,
                retest_index=retest_index,
                tolerance_percent=self.tolerance_percent,
                breakout_close=breakout.close,
                retest_close=retest.close,
            )

        return None

    def latest_bearish(
        self,
        candles: list[Candle],
    ) -> RetestSignal | None:
        if len(candles) < self.level_lookback + 3:
            return None

        retest_index = len(candles) - 1
        retest = candles[retest_index]

        start = max(
            self.level_lookback,
            retest_index - self.max_bars_after_breakout,
        )

        for breakout_index in range(
            retest_index - 1,
            start - 1,
            -1,
        ):
            previous = candles[
                breakout_index - self.level_lookback
                : breakout_index
            ]

            if not previous:
                continue

            level = min(
                candle.low
                for candle in previous
            )

            tolerance = self._tolerance(level)
            breakout = candles[breakout_index]

            if breakout.close >= level:
                continue

            if self._bearish_invalidated(
                candles=candles[
                    breakout_index + 1
                    : retest_index
                ],
                level=level,
                tolerance=tolerance,
            ):
                continue

            if not self._bearish_retest(
                candle=retest,
                level=level,
                tolerance=tolerance,
            ):
                continue

            return RetestSignal(
                kind="bearish_retest",
                direction="SHORT",
                level=level,
                breakout_index=breakout_index,
                retest_index=retest_index,
                tolerance_percent=self.tolerance_percent,
                breakout_close=breakout.close,
                retest_close=retest.close,
            )

        return None

    def _bullish_retest(
        self,
        *,
        candle: Candle,
        level: float,
        tolerance: float,
    ) -> bool:
        if candle.low > level + tolerance:
            return False

        if candle.close <= level:
            return False

        if (
            self.require_rejection_candle
            and candle.close <= candle.open
        ):
            return False

        return True

    def _bearish_retest(
        self,
        *,
        candle: Candle,
        level: float,
        tolerance: float,
    ) -> bool:
        if candle.high < level - tolerance:
            return False

        if candle.close >= level:
            return False

        if (
            self.require_rejection_candle
            and candle.close >= candle.open
        ):
            return False

        return True

    @staticmethod
    def _bullish_invalidated(
        *,
        candles: list[Candle],
        level: float,
        tolerance: float,
    ) -> bool:
        return any(
            candle.close < level - tolerance
            for candle in candles
        )

    @staticmethod
    def _bearish_invalidated(
        *,
        candles: list[Candle],
        level: float,
        tolerance: float,
    ) -> bool:
        return any(
            candle.close > level + tolerance
            for candle in candles
        )

    def _tolerance(
        self,
        level: float,
    ) -> float:
        return abs(level) * (
            self.tolerance_percent
            / 100.0
        )
