from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal

from trading_scanner.setups import classify_breakout_or_pullback_in_trend
from trading_scanner.universe import ContractMarketData


def md(closes, highs=None):
    c=tuple(Decimal(str(x)) for x in closes)
    h=tuple(Decimal(str(x)) for x in (highs or closes))
    return ContractMarketData(
        conid=1,
        closes=c,
        highs=h,
        lows=tuple(x-Decimal("1") for x in c),
        volumes=tuple(Decimal("1000000") for _ in c),
        observed_at=datetime(2026,9,5,20,tzinfo=timezone.utc),
    )


class GilBreakoutContractProofTests(unittest.TestCase):
    def test_exact_fresh_daily_breakout_contract(self):
        # 50-bar rising trend: SMA20>SMA50. Final completed close breaks
        # the highest completed close of the prior 20 bars.
        closes=[Decimal("100")+Decimal(i) for i in range(50)]
        closes.append(Decimal("151"))
        out=classify_breakout_or_pullback_in_trend(md(closes))
        self.assertIsNotNone(out)
        self.assertTrue(out.matched)
        self.assertTrue(out.reason_stack[0].startswith("BREAKOUT:"))
        self.assertIn("prior 20-day high",out.reason_stack[0])
        self.assertIn("SMA20",out.reason_stack[1])
        self.assertIn("SMA50",out.reason_stack[1])
        self.assertIn("breakout level",out.invalidation_reference)

    def test_no_breakout_is_not_promoted_as_breakout(self):
        closes=[Decimal("100")+Decimal(i) for i in range(50)]
        closes.append(Decimal("149"))
        out=classify_breakout_or_pullback_in_trend(md(closes))
        self.assertIsNotNone(out)
        self.assertFalse(out.matched or out.reason_stack[0].startswith("BREAKOUT:"))

    def test_trend_misalignment_blocks_breakout(self):
        closes=[Decimal("200")-Decimal(i) for i in range(50)]
        closes.append(Decimal("250"))
        out=classify_breakout_or_pullback_in_trend(md(closes))
        self.assertIsNotNone(out)
        self.assertFalse(out.matched)
        self.assertIn("trend not aligned",out.reason_stack[0])


if __name__=="__main__":
    unittest.main()
