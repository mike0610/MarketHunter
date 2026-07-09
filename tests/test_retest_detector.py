"""
Tests for breakout/breakdown retest confirmation.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from indicators.retest_detector import RetestDetector


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


class RetestDetectorTests(unittest.TestCase):
    def test_bullish_breakout_retest_rejection(self) -> None:
        candles = [
            candle(high=100.0, low=96.0, close=98.0)
            for _ in range(20)
        ]

        candles += [
            candle(high=102.0, low=99.5, close=101.2, open_=99.8),
            candle(high=102.5, low=100.8, close=101.7, open_=101.1),
            candle(high=101.8, low=99.9, close=101.1, open_=100.2),
        ]

        detector = RetestDetector(
            level_lookback=20,
            max_bars_after_breakout=5,
            tolerance_percent=0.25,
        )

        signal = detector.latest_bullish(candles)

        self.assertIsNotNone(signal)
        self.assertTrue(detector.bullish(candles))
        self.assertEqual(signal.direction, "LONG")
        self.assertEqual(signal.kind, "bullish_retest")
        self.assertEqual(signal.level, 100.0)

    def test_bearish_breakdown_retest_rejection(self) -> None:
        candles = [
            candle(high=104.0, low=100.0, close=102.0)
            for _ in range(20)
        ]

        candles += [
            candle(high=100.5, low=98.0, close=98.8, open_=100.2),
            candle(high=99.3, low=97.5, close=98.2, open_=98.9),
            candle(high=100.1, low=97.8, close=98.7, open_=99.8),
        ]

        detector = RetestDetector(
            level_lookback=20,
            max_bars_after_breakout=5,
            tolerance_percent=0.25,
        )

        signal = detector.latest_bearish(candles)

        self.assertIsNotNone(signal)
        self.assertTrue(detector.bearish(candles))
        self.assertEqual(signal.direction, "SHORT")
        self.assertEqual(signal.kind, "bearish_retest")
        self.assertEqual(signal.level, 100.0)

    def test_no_bullish_signal_without_retest_touch(self) -> None:
        candles = [
            candle(high=100.0, low=96.0, close=98.0)
            for _ in range(20)
        ]

        candles += [
            candle(high=102.0, low=99.5, close=101.2, open_=99.8),
            candle(high=102.5, low=101.1, close=101.7, open_=101.1),
            candle(high=103.0, low=101.2, close=102.4, open_=101.6),
        ]

        detector = RetestDetector(
            level_lookback=20,
            max_bars_after_breakout=5,
            tolerance_percent=0.25,
        )

        self.assertIsNone(detector.latest_bullish(candles))
        self.assertFalse(detector.bullish(candles))

    def test_no_bearish_signal_after_invalidation(self) -> None:
        candles = [
            candle(high=104.0, low=100.0, close=102.0)
            for _ in range(20)
        ]

        candles += [
            candle(high=100.5, low=98.0, close=98.8, open_=100.2),
            candle(high=101.0, low=99.0, close=100.8, open_=99.2),
            candle(high=100.1, low=97.8, close=98.7, open_=99.8),
        ]

        detector = RetestDetector(
            level_lookback=20,
            max_bars_after_breakout=5,
            tolerance_percent=0.25,
        )

        self.assertIsNone(detector.latest_bearish(candles))
        self.assertFalse(detector.bearish(candles))


if __name__ == "__main__":
    unittest.main()
