from __future__ import annotations

import unittest
from datetime import datetime, timezone, timedelta

from indicators.double_pattern import DoublePatternDetector
from models.candle import Candle


def candle(
    index: int,
    *,
    open_price: float,
    high: float,
    low: float,
    close: float,
) -> Candle:
    open_time = datetime(
        2026,
        1,
        1,
        tzinfo=timezone.utc,
    ) + timedelta(hours=index)

    return Candle(
        open_time=open_time,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=1000.0,
        close_time=open_time + timedelta(hours=1),
        quote_volume=1000.0,
        trades=100,
        taker_buy_base_volume=500.0,
        taker_buy_quote_volume=500.0,
    )


class DoublePatternDetectorTests(unittest.TestCase):

    def test_detects_confirmed_double_bottom(self) -> None:
        candles = [
            candle(0, open_price=12.0, high=12.2, low=11.7, close=12.0),
            candle(1, open_price=12.0, high=12.1, low=11.5, close=11.7),
            candle(2, open_price=11.8, high=12.0, low=10.0, close=10.4),
            candle(3, open_price=10.4, high=11.2, low=10.3, close=11.0),
            candle(4, open_price=11.0, high=12.4, low=10.9, close=12.0),
            candle(5, open_price=12.0, high=12.2, low=11.2, close=11.5),
            candle(6, open_price=11.5, high=11.7, low=10.05, close=10.7),
            candle(7, open_price=10.7, high=11.6, low=10.6, close=11.4),
            candle(8, open_price=11.4, high=12.6, low=11.3, close=12.5),
        ]

        detector = DoublePatternDetector(
            pivot_left=1,
            pivot_right=1,
            min_bars_between=2,
        )

        signal = detector.latest_bullish(candles)

        self.assertIsNotNone(signal)
        self.assertTrue(signal.confirmed)
        self.assertEqual(signal.direction, "LONG")
        self.assertEqual(signal.kind, "double_bottom")
        self.assertTrue(detector.bullish(candles))

    def test_detects_confirmed_double_top(self) -> None:
        candles = [
            candle(0, open_price=10.0, high=10.5, low=9.8, close=10.3),
            candle(1, open_price=10.3, high=11.0, low=10.2, close=10.8),
            candle(2, open_price=10.8, high=12.0, low=10.7, close=11.6),
            candle(3, open_price=11.6, high=11.8, low=10.6, close=10.9),
            candle(4, open_price=10.9, high=11.2, low=9.7, close=10.0),
            candle(5, open_price=10.0, high=11.0, low=9.9, close=10.8),
            candle(6, open_price=10.8, high=12.05, low=10.7, close=11.4),
            candle(7, open_price=11.4, high=11.5, low=10.4, close=10.7),
            candle(8, open_price=10.7, high=10.8, low=9.5, close=9.6),
        ]

        detector = DoublePatternDetector(
            pivot_left=1,
            pivot_right=1,
            min_bars_between=2,
        )

        signal = detector.latest_bearish(candles)

        self.assertIsNotNone(signal)
        self.assertTrue(signal.confirmed)
        self.assertEqual(signal.direction, "SHORT")
        self.assertEqual(signal.kind, "double_top")
        self.assertTrue(detector.bearish(candles))

    def test_rejects_unconfirmed_double_bottom(self) -> None:
        candles = [
            candle(0, open_price=12.0, high=12.2, low=11.7, close=12.0),
            candle(1, open_price=12.0, high=12.1, low=11.5, close=11.7),
            candle(2, open_price=11.8, high=12.0, low=10.0, close=10.4),
            candle(3, open_price=10.4, high=11.2, low=10.3, close=11.0),
            candle(4, open_price=11.0, high=12.4, low=10.9, close=12.0),
            candle(5, open_price=12.0, high=12.2, low=11.2, close=11.5),
            candle(6, open_price=11.5, high=11.7, low=10.05, close=10.7),
            candle(7, open_price=10.7, high=11.6, low=10.6, close=11.4),
        ]

        detector = DoublePatternDetector(
            pivot_left=1,
            pivot_right=1,
            min_bars_between=2,
        )

        signal = detector.latest_bullish(candles)

        self.assertIsNotNone(signal)
        self.assertFalse(signal.confirmed)
        self.assertFalse(detector.bullish(candles))


if __name__ == "__main__":
    unittest.main()
