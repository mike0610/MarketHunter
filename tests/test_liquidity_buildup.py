"""
Tests for liquidity buildup sweep confirmation.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from indicators.liquidity_buildup import (
    LiquidityBuildupSweepDetector,
)


def candle(
    *,
    high: float,
    low: float,
    close: float,
    open_: float | None = None,
):
    return SimpleNamespace(
        open=close if open_ is None else open_,
        high=high,
        low=low,
        close=close,
    )


class LiquidityBuildupSweepDetectorTests(unittest.TestCase):
    def test_bullish_equal_lows_sweep_and_reclaim(self) -> None:
        candles = [
            candle(high=105, low=100.0, close=103),
            candle(high=106, low=102.0, close=105),
            candle(high=105, low=100.1, close=104),
            candle(high=107, low=103.0, close=106),
            candle(high=106, low=100.05, close=105),
            candle(high=105, low=99.2, close=101.2),
        ]

        detector = LiquidityBuildupSweepDetector(
            lookback_candles=20,
            tolerance_percent=0.25,
            min_bars_between=2,
        )

        signal = detector.latest_bullish(candles)

        self.assertIsNotNone(signal)
        self.assertTrue(detector.bullish(candles))
        self.assertEqual(signal.direction, "LONG")
        self.assertEqual(
            signal.kind,
            "sell_side_liquidity_sweep",
        )
        self.assertGreaterEqual(signal.touches, 2)

    def test_bearish_equal_highs_sweep_and_reclaim(self) -> None:
        candles = [
            candle(high=100.0, low=95, close=97),
            candle(high=98.0, low=94, close=96),
            candle(high=100.1, low=95, close=97),
            candle(high=97.0, low=93, close=94),
            candle(high=100.05, low=96, close=98),
            candle(high=101.0, low=96, close=99.2),
        ]

        detector = LiquidityBuildupSweepDetector(
            lookback_candles=20,
            tolerance_percent=0.25,
            min_bars_between=2,
        )

        signal = detector.latest_bearish(candles)

        self.assertIsNotNone(signal)
        self.assertTrue(detector.bearish(candles))
        self.assertEqual(signal.direction, "SHORT")
        self.assertEqual(
            signal.kind,
            "buy_side_liquidity_sweep",
        )
        self.assertGreaterEqual(signal.touches, 2)

    def test_no_signal_without_reclaim(self) -> None:
        candles = [
            candle(high=100.0, low=95, close=97),
            candle(high=98.0, low=94, close=96),
            candle(high=100.1, low=95, close=97),
            candle(high=97.0, low=93, close=94),
            candle(high=100.05, low=96, close=98),
            candle(high=101.0, low=96, close=100.8),
        ]

        detector = LiquidityBuildupSweepDetector(
            lookback_candles=20,
            tolerance_percent=0.25,
            min_bars_between=2,
        )

        self.assertIsNone(
            detector.latest_bearish(candles),
        )
        self.assertFalse(
            detector.bearish(candles),
        )


if __name__ == "__main__":
    unittest.main()
