from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from models.candle import Candle
from research.price_action.context import PriceActionContextEngine


def c(i, o, h, l, cl):
    t = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=i)
    return Candle(
        t,
        o,
        h,
        l,
        cl,
        1000,
        t + timedelta(days=1),
        100000,
        100,
        500,
        50000,
    )


class PriceActionContextStructuralLineTests(unittest.TestCase):
    def test_context_exposes_repeated_reaction_support_line(self):
        candles = [
            c(i, 104, 106, 103, 105)
            for i in range(30)
        ]

        for index, low in ((3, 100.0), (10, 100.2), (18, 99.9)):
            candles[index - 1] = c(index - 1, 104, 105, 102.5, 103)
            candles[index] = c(index, 103, 104, low, 101)
            candles[index + 1] = c(index + 1, 101, 105, 100.8, 104)

        context = PriceActionContextEngine().analyze(candles)

        support_lines = [
            line
            for line in context.structural_lines
            if line.side == "support"
        ]

        self.assertTrue(support_lines)
        self.assertGreaterEqual(
            max(line.touches for line in support_lines),
            3,
        )


if __name__ == "__main__":
    unittest.main()
