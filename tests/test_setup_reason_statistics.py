"""
Tests for setup reason statistics.
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
    strategy: str,
    reasons: list[str],
    status: TradeStatus,
    close_reason: str | None,
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
        strategy=strategy,
        direction="LONG",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        probability=60,
        score=85.0,
        reasons=reasons,
        status=status,
        created_at=datetime.now(timezone.utc),
        close_reason=close_reason,
        profit_percent=profit_percent,
        profit_amount=profit_amount,
        rr=rr,
    )


class SetupReasonStatisticsTests(unittest.TestCase):
    def test_groups_completed_trades_by_strategy(self) -> None:
        stats = ResearchStatistics().calculate_setup_reasons(
            [
                trade(
                    trade_id="1",
                    strategy="FVG",
                    reasons=["Bullish Fair Value Gap"],
                    status=TradeStatus.CLOSED,
                    close_reason="TP",
                    profit_percent=5.0,
                    profit_amount=5.0,
                    rr=2.0,
                ),
                trade(
                    trade_id="2",
                    strategy="FVG",
                    reasons=["Bullish Fair Value Gap"],
                    status=TradeStatus.CLOSED,
                    close_reason="SL",
                    profit_percent=-2.0,
                    profit_amount=-2.0,
                    rr=-1.0,
                ),
            ]
        )

        fvg = stats["by_strategy"][0]

        self.assertEqual(
            fvg["label"],
            "FVG",
        )
        self.assertEqual(
            fvg["completed"],
            2,
        )
        self.assertEqual(
            fvg["wins"],
            1,
        )
        self.assertEqual(
            fvg["losses"],
            1,
        )

    def test_groups_risk_geometry_block_reason(self) -> None:
        stats = ResearchStatistics().calculate_setup_reasons(
            [
                trade(
                    trade_id="1",
                    strategy="FVG",
                    reasons=["Bullish Fair Value Gap"],
                    status=TradeStatus.CANDIDATE,
                    close_reason=(
                        "CANDIDATE_PROMOTION_BLOCKED: "
                        "Risk geometry invalid: stop distance 33%."
                    ),
                ),
            ]
        )

        labels = [
            row["label"]
            for row in stats["by_close_reason"]
        ]

        self.assertIn(
            "Risk geometry blocked",
            labels,
        )

    def test_detects_liquidity_buildup_setup_reason(self) -> None:
        stats = ResearchStatistics().calculate_setup_reasons(
            [
                trade(
                    trade_id="1",
                    strategy="FVG",
                    reasons=["Bullish Liquidity Buildup Sweep"],
                    status=TradeStatus.CLOSED,
                    close_reason="TP",
                    profit_percent=4.0,
                    profit_amount=4.0,
                    rr=2.0,
                ),
            ]
        )

        labels = [
            row["label"]
            for row in stats["by_setup_reason"]
        ]

        self.assertIn(
            "Liquidity Buildup Sweep",
            labels,
        )


if __name__ == "__main__":
    unittest.main()
