"""
Tests for aggregate research statistics.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from research.models.trade import ResearchTrade
from research.models.trade_status import TradeStatus
from research.statistics import ResearchStatistics


def trade(
    *,
    trade_id: str,
    status: TradeStatus,
    profit_percent: float = 0.0,
    profit_amount: float = 0.0,
    rr: float = 0.0,
) -> ResearchTrade:
    return ResearchTrade(
        id=trade_id,
        signal_id=None,
        symbol="BTCUSDT",
        market="futures",
        timeframe="1h",
        strategy="FVG",
        direction="LONG",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        probability=60,
        score=85.0,
        reasons=["Bullish Fair Value Gap"],
        status=status,
        created_at=datetime.now(timezone.utc),
        close_reason="TP" if profit_percent >= 0 else "SL",
        profit_percent=profit_percent,
        profit_amount=profit_amount,
        rr=rr,
    )


class ResearchStatisticsProfitFactorTests(unittest.TestCase):
    def test_profit_factor_is_none_with_no_completed_trades(self) -> None:
        stats = ResearchStatistics().calculate([])

        self.assertIsNone(stats["profit_factor"])

    def test_profit_factor_is_none_with_wins_and_zero_losses(self) -> None:
        stats = ResearchStatistics().calculate(
            [
                trade(
                    trade_id="1",
                    status=TradeStatus.CLOSED,
                    profit_percent=5.0,
                    profit_amount=5.0,
                    rr=2.0,
                ),
            ]
        )

        self.assertEqual(stats["wins"], 1)
        self.assertEqual(stats["losses"], 0)
        self.assertIsNone(stats["profit_factor"])

    def test_profit_factor_is_a_ratio_with_wins_and_losses(self) -> None:
        stats = ResearchStatistics().calculate(
            [
                trade(
                    trade_id="1",
                    status=TradeStatus.CLOSED,
                    profit_percent=6.0,
                    profit_amount=6.0,
                    rr=2.0,
                ),
                trade(
                    trade_id="2",
                    status=TradeStatus.CLOSED,
                    profit_percent=-2.0,
                    profit_amount=-2.0,
                    rr=-1.0,
                ),
            ]
        )

        self.assertEqual(stats["profit_factor"], 3.0)


if __name__ == "__main__":
    unittest.main()
