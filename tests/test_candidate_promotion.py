"""
Tests for candidate -> waiting_entry promotion.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from research.candidate_promotion_service import (
    CandidatePromotionService,
)
from research.models.trade import ResearchTrade
from research.models.trade_status import TradeStatus
from research.storage.repository import ResearchRepository


def candle(index: int):
    now = datetime.now(timezone.utc)

    return SimpleNamespace(
        open_time=now - timedelta(hours=3 - index),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=1.0,
        close_time=now - timedelta(hours=2 - index),
        quote_volume=100.0,
        trades=10,
        taker_buy_base_volume=0.5,
        taker_buy_quote_volume=50.0,
    )


class FakeSupportResistance:
    def __init__(
        self,
        *,
        target_clear: bool,
    ) -> None:
        self.target_clear = target_clear

    def assess_rr_target(
        self,
        candles,
        *,
        direction,
        entry_price,
        stop_loss,
        target_rr,
    ):
        _ = candles, direction, entry_price, stop_loss, target_rr

        return SimpleNamespace(
            target_clear=self.target_clear,
            summary=(
                "TP 1:3 looks clear."
                if self.target_clear
                else "TP 1:3 is blocked."
            ),
        )


class FakeReactionQuality:
    def __init__(
        self,
        *,
        confirmed: bool,
    ) -> None:
        self.confirmed = confirmed

    def assess(
        self,
        *,
        snapshot,
        direction,
    ):
        _ = snapshot, direction

        return SimpleNamespace(
            confirmed=self.confirmed,
            score=1 if self.confirmed else 0,
            reasons=["Bullish Retest"] if self.confirmed else [],
            atr_body_ratio=1.0,
            summary=(
                "Reaction confirmed: Bullish Retest."
                if self.confirmed
                else "No confirmed reaction."
            ),
        )


class FakeSnapshotBuilder:
    def build(
        self,
        symbol,
        candles,
    ):
        return SimpleNamespace(
            symbol=symbol,
            candles=candles,
            atr14=1.0,
            ema20=100.0,
        )


class CandidatePromotionTests(
    unittest.IsolatedAsyncioTestCase,
):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()

        database_path = Path(
            self.temp_dir.name,
        ) / "research.db"

        self.repository = ResearchRepository(
            path=str(database_path),
        )

    def tearDown(self) -> None:
        self.repository.close()
        self.temp_dir.cleanup()

    async def loader(
        self,
        trade,
    ):
        _ = trade

        return [
            candle(0),
            candle(1),
            candle(2),
        ]

    def save_candidate(
        self,
        *,
        trade_id: str = "candidate-1",
    ) -> ResearchTrade:
        trade = ResearchTrade(
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
            status=TradeStatus.CANDIDATE,
            close_reason="CANDIDATE_PROMOTION_BLOCKED: old reason",
        )

        self.repository.save(trade)

        return trade

    async def test_promotes_candidate_when_target_and_reaction_confirm(
        self,
    ) -> None:
        trade = self.save_candidate()

        service = CandidatePromotionService(
            repository=self.repository,
            support_resistance=FakeSupportResistance(
                target_clear=True,
            ),
            reaction_quality=FakeReactionQuality(
                confirmed=True,
            ),
            snapshot_builder=FakeSnapshotBuilder(),
        )

        result = await service.run_once(
            candle_loader=self.loader,
        )

        refreshed = self.repository.get_by_id(
            trade.id,
        )

        self.assertEqual(
            result.promoted,
            1,
        )
        self.assertEqual(
            refreshed.status,
            TradeStatus.WAITING_ENTRY,
        )
        self.assertIn(
            "CANDIDATE_PROMOTED",
            refreshed.close_reason or "",
        )

    async def test_blocks_candidate_when_target_is_not_clear(
        self,
    ) -> None:
        trade = self.save_candidate()

        service = CandidatePromotionService(
            repository=self.repository,
            support_resistance=FakeSupportResistance(
                target_clear=False,
            ),
            reaction_quality=FakeReactionQuality(
                confirmed=True,
            ),
            snapshot_builder=FakeSnapshotBuilder(),
        )

        result = await service.run_once(
            candle_loader=self.loader,
        )

        refreshed = self.repository.get_by_id(
            trade.id,
        )

        self.assertEqual(
            result.blocked,
            1,
        )
        self.assertEqual(
            refreshed.status,
            TradeStatus.CANDIDATE,
        )
        self.assertIn(
            "CANDIDATE_PROMOTION_BLOCKED",
            refreshed.close_reason or "",
        )

    async def test_blocks_candidate_without_reaction(
        self,
    ) -> None:
        trade = self.save_candidate()

        service = CandidatePromotionService(
            repository=self.repository,
            support_resistance=FakeSupportResistance(
                target_clear=True,
            ),
            reaction_quality=FakeReactionQuality(
                confirmed=False,
            ),
            snapshot_builder=FakeSnapshotBuilder(),
        )

        result = await service.run_once(
            candle_loader=self.loader,
        )

        refreshed = self.repository.get_by_id(
            trade.id,
        )

        self.assertEqual(
            result.blocked,
            1,
        )
        self.assertEqual(
            refreshed.status,
            TradeStatus.CANDIDATE,
        )
        self.assertIn(
            "No confirmed reaction",
            refreshed.close_reason or "",
        )


if __name__ == "__main__":
    unittest.main()
