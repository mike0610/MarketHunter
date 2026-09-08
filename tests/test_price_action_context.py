from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from models.candle import Candle
from research.price_action.context import (
    PriceActionContextEngine,
    PriceZone,
    SwingPoint,
)


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


class PriceActionContextTests(unittest.TestCase):
    def setUp(self):
        self.engine = PriceActionContextEngine()

    def test_structure_break_and_reclaim_are_observable_events(self):
        candles = [
            c(0, 99, 100, 98, 99),
            c(1, 99, 101, 98, 100),
            c(2, 100, 102, 99, 101),
            c(3, 101, 103, 100, 102),
            c(4, 102, 105, 101, 104),
            c(5, 104, 106, 103, 105),
            c(6, 105, 106, 101, 102),
            c(7, 102, 103, 99, 100),
        ]
        highs = [SwingPoint(index=3, price=103, kind="high")]
        lows = []

        events = self.engine._structure_events(candles, highs, lows)

        self.assertEqual(events[0].kind, "break_of_structure")
        self.assertEqual(events[0].direction, "bullish")
        self.assertEqual(events[0].level, 103)
        self.assertEqual(events[-1].kind, "reclaim")
        self.assertEqual(events[-1].direction, "bearish")

    def test_resistance_rejection_is_detected(self):
        zone = PriceZone(100, 101, 3, "resistance")
        candles = [
            c(i, 97, 99, 96, 98)
            for i in range(8)
        ] + [
            c(8, 99, 101, 98.5, 99.2),
            c(9, 99.2, 100.8, 98.8, 99.0),
        ]

        behavior = self.engine._zone_behaviors(candles, [zone])[0]

        self.assertEqual(behavior.state, "rejection")
        self.assertEqual(behavior.direction, "bearish")

    def test_bullish_breakout_and_retest_hold_are_distinct(self):
        zone = PriceZone(100, 101, 3, "resistance")
        candles = [
            c(i, 97, 99, 96, 98)
            for i in range(7)
        ] + [
            c(7, 99, 103, 98.5, 102),
            c(8, 102, 103, 100.5, 101.5),
            c(9, 101.5, 103, 101.2, 102.5),
        ]

        behavior = self.engine._zone_behaviors(candles, [zone])[0]

        self.assertEqual(behavior.state, "retest_hold")
        self.assertEqual(behavior.direction, "bullish")

    def test_compression_toward_zone_uses_price_and_range_only(self):
        zone = PriceZone(110, 111, 2, "resistance")
        candles = [
            c(0, 100, 104, 98, 101),
            c(1, 101, 104.5, 99, 103),
            c(2, 103, 106, 101, 105),
            c(3, 105, 107, 103, 106.5),
        ]

        self.assertTrue(
            self.engine._is_compressing_toward_zone(candles, zone)
        )


if __name__ == "__main__":
    unittest.main()
