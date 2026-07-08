"""
Tests for RSI and divergence detection.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from indicators.divergence_detector import DivergenceDetector
from indicators.rsi import rsi


def candle(
    high: float,
    low: float,
    close: float | None = None,
):
    if close is None:
        close = (high + low) / 2.0

    return SimpleNamespace(
        high=high,
        low=low,
        close=close,
    )


class RSITest(unittest.TestCase):
    def test_rsi_returns_values_after_period(self):
        candles = [
            candle(
                high=float(index + 2),
                low=float(index),
                close=float(index + 1),
            )
            for index in range(30)
        ]

        values = rsi(
            candles=candles,
            period=14,
        )

        self.assertEqual(
            len(values),
            len(candles),
        )

        self.assertIsNone(
            values[13],
        )

        self.assertIsNotNone(
            values[14],
        )

        self.assertGreater(
            values[-1],
            90.0,
        )


class DivergenceDetectorTests(unittest.TestCase):
    def setUp(self):
        self.detector = DivergenceDetector(
            pivot_window=2,
            min_bars_between=3,
            max_bars_between=30,
            min_oscillator_delta=2.0,
        )

    def test_detects_regular_bullish_divergence(self):
        lows = [
            100,
            99,
            98,
            97,
            96,
            90,
            96,
            97,
            98,
            99,
            100,
            99,
            98,
            97,
            96,
            85,
            96,
            97,
            98,
            99,
            100,
        ]

        candles = [
            candle(
                high=value + 5,
                low=value,
            )
            for value in lows
        ]

        oscillator = [
            50.0
            for _ in candles
        ]

        oscillator[5] = 30.0
        oscillator[15] = 40.0

        signals = self.detector.detect(
            candles=candles,
            oscillator_values=oscillator,
            oscillator_name="RSI",
        )

        self.assertEqual(
            signals[-1].kind,
            "regular_bullish",
        )

        self.assertEqual(
            signals[-1].direction,
            "LONG",
        )

    def test_detects_regular_bearish_divergence(self):
        highs = [
            100,
            101,
            102,
            103,
            104,
            110,
            104,
            103,
            102,
            101,
            100,
            101,
            102,
            103,
            104,
            115,
            104,
            103,
            102,
            101,
            100,
        ]

        candles = [
            candle(
                high=value,
                low=value - 5,
            )
            for value in highs
        ]

        oscillator = [
            50.0
            for _ in candles
        ]

        oscillator[5] = 70.0
        oscillator[15] = 60.0

        signals = self.detector.detect(
            candles=candles,
            oscillator_values=oscillator,
            oscillator_name="RSI",
        )

        self.assertEqual(
            signals[-1].kind,
            "regular_bearish",
        )

        self.assertEqual(
            signals[-1].direction,
            "SHORT",
        )

    def test_detects_hidden_bullish_divergence(self):
        lows = [
            100,
            99,
            98,
            97,
            96,
            90,
            96,
            97,
            98,
            99,
            100,
            101,
            100,
            99,
            98,
            95,
            98,
            99,
            100,
            101,
            102,
        ]

        candles = [
            candle(
                high=value + 5,
                low=value,
            )
            for value in lows
        ]

        oscillator = [
            50.0
            for _ in candles
        ]

        oscillator[5] = 45.0
        oscillator[15] = 35.0

        signals = self.detector.detect(
            candles=candles,
            oscillator_values=oscillator,
            oscillator_name="RSI",
        )

        self.assertEqual(
            signals[-1].kind,
            "hidden_bullish",
        )

        self.assertEqual(
            signals[-1].direction,
            "LONG",
        )

    def test_detects_hidden_bearish_divergence(self):
        highs = [
            100,
            101,
            102,
            103,
            104,
            115,
            104,
            103,
            102,
            101,
            100,
            99,
            100,
            101,
            102,
            110,
            102,
            101,
            100,
            99,
            98,
        ]

        candles = [
            candle(
                high=value,
                low=value - 5,
            )
            for value in highs
        ]

        oscillator = [
            50.0
            for _ in candles
        ]

        oscillator[5] = 55.0
        oscillator[15] = 65.0

        signals = self.detector.detect(
            candles=candles,
            oscillator_values=oscillator,
            oscillator_name="RSI",
        )

        self.assertEqual(
            signals[-1].kind,
            "hidden_bearish",
        )

        self.assertEqual(
            signals[-1].direction,
            "SHORT",
        )


if __name__ == "__main__":
    unittest.main()
