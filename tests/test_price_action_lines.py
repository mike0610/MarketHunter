from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from models.candle import Candle
from research.price_action.context import SwingPoint
from research.price_action.lines import StructuralLineDetector


def c(i, o, h, l, cl):
    t = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i)
    return Candle(
        t,
        o,
        h,
        l,
        cl,
        1000,
        t + timedelta(hours=1),
        100000,
        100,
        500,
        50000,
    )


class StructuralLineDetectorTests(unittest.TestCase):
    def setUp(self):
        self.detector = StructuralLineDetector(
            minimum_rebound_percent=1.0,
            minimum_touches=3,
            maximum_line_deviation_percent=0.6,
            minimum_touch_spacing=3,
        )

    def test_horizontal_support_requires_repeated_rebounds(self):
        candles = [c(i, 102, 104, 100, 103) for i in range(24)]
        lows = [
            SwingPoint(3, 100.0, "low"),
            SwingPoint(10, 100.2, "low"),
            SwingPoint(18, 99.9, "low"),
        ]

        lines = self.detector.detect(
            candles,
            swing_highs=[],
            swing_lows=lows,
        )

        self.assertTrue(
            any(
                line.side == "support"
                and line.kind == "horizontal"
                and line.touches >= 3
                for line in lines
            )
        )

    def test_ascending_support_line_is_detected(self):
        candles = [c(i, 105 + i, 108 + i, 100 + i, 107 + i) for i in range(30)]
        lows = [
            SwingPoint(3, 103.0, "low"),
            SwingPoint(10, 110.0, "low"),
            SwingPoint(18, 118.0, "low"),
        ]

        lines = self.detector.detect(
            candles,
            swing_highs=[],
            swing_lows=lows,
        )

        self.assertTrue(
            any(
                line.side == "support"
                and line.kind == "ascending"
                and line.touches >= 3
                for line in lines
            )
        )

    def test_touch_without_rebound_does_not_count(self):
        flat = [c(i, 100, 100.4, 99.8, 100.1) for i in range(20)]
        lows = [
            SwingPoint(3, 100.0, "low"),
            SwingPoint(9, 100.1, "low"),
            SwingPoint(15, 99.9, "low"),
        ]

        lines = self.detector.detect(
            flat,
            swing_highs=[],
            swing_lows=lows,
        )

        self.assertEqual(lines, [])

    def test_descending_resistance_line_is_detected(self):
        candles = [c(i, 95 - i, 100 - i, 92 - i, 93 - i) for i in range(30)]
        highs = [
            SwingPoint(3, 97.0, "high"),
            SwingPoint(10, 90.0, "high"),
            SwingPoint(18, 82.0, "high"),
        ]

        lines = self.detector.detect(
            candles,
            swing_highs=highs,
            swing_lows=[],
        )

        self.assertTrue(
            any(
                line.side == "resistance"
                and line.kind == "descending"
                and line.touches >= 3
                for line in lines
            )
        )


if __name__ == "__main__":
    unittest.main()
