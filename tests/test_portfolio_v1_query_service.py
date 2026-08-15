"""
Tests for the Portfolio v1 Slice 3 query/service layer.
"""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from research.models.trade import ResearchTrade
from research.models.trade_status import TradeStatus
from research.storage.repository import ResearchRepository

from portfolio_v1.domain import ExposureState
from portfolio_v1.query_service import query_exposure


def trade(
    *,
    trade_id: str,
    notional: float = 100.0,
    status: TradeStatus = TradeStatus.ACTIVE,
    market: str = "futures",
    direction: str = "LONG",
    research_group: str = "core",
    strategy: str = "FVG",
) -> ResearchTrade:
    return ResearchTrade(
        id=trade_id,
        signal_id=None,
        symbol="BTCUSDT",
        market=market,
        timeframe="1h",
        strategy=strategy,
        direction=direction,
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        probability=60,
        score=85.0,
        notional=notional,
        status=status,
        research_group=research_group,
    )


class PortfolioQueryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()

        self.database_path = Path(
            self.temp_dir.name
        ) / "research.db"

        self.repository = ResearchRepository(
            path=str(self.database_path),
        )

    def tearDown(self) -> None:
        self.repository.close()
        self.temp_dir.cleanup()

    def test_reads_persisted_trades_into_exposure_assessment(self) -> None:
        self.repository.save(
            trade(trade_id="1", notional=100.0),
        )
        self.repository.save(
            trade(trade_id="2", notional=250.0),
        )

        assessment = query_exposure(
            self.repository,
            assessment_id="assess-1",
            generated_at="2026-08-15T00:00:00Z",
        )

        self.assertEqual(assessment.state, ExposureState.MEASURED)
        self.assertEqual(assessment.position_count, 2)
        self.assertEqual(assessment.total_notional, 350.0)
        self.assertIn("persisted_research_trades", assessment.provenance)

    def test_valid_empty_query_is_measured_zero_not_unknown(self) -> None:
        assessment = query_exposure(
            self.repository,
            assessment_id="assess-1",
            generated_at="2026-08-15T00:00:00Z",
        )

        self.assertEqual(assessment.state, ExposureState.MEASURED)
        self.assertEqual(assessment.position_count, 0)
        self.assertEqual(assessment.total_notional, 0.0)

    def test_status_filter_only_includes_matching_trades(self) -> None:
        self.repository.save(
            trade(
                trade_id="active-1",
                notional=100.0,
                status=TradeStatus.ACTIVE,
            ),
        )
        self.repository.save(
            trade(
                trade_id="waiting-1",
                notional=999.0,
                status=TradeStatus.WAITING_ENTRY,
            ),
        )

        assessment = query_exposure(
            self.repository,
            assessment_id="assess-1",
            generated_at="2026-08-15T00:00:00Z",
            status=TradeStatus.ACTIVE,
        )

        self.assertEqual(assessment.position_count, 1)
        self.assertEqual(assessment.total_notional, 100.0)
        self.assertIn("status=active", assessment.provenance)

    def test_market_direction_research_group_strategy_filters_combine(
        self,
    ) -> None:
        self.repository.save(
            trade(
                trade_id="match",
                notional=50.0,
                market="spot",
                direction="SHORT",
                research_group="experimental",
                strategy="BOS",
            ),
        )
        self.repository.save(
            trade(
                trade_id="wrong-market",
                notional=999.0,
                market="futures",
                direction="SHORT",
                research_group="experimental",
                strategy="BOS",
            ),
        )
        self.repository.save(
            trade(
                trade_id="wrong-strategy",
                notional=999.0,
                market="spot",
                direction="SHORT",
                research_group="experimental",
                strategy="FVG",
            ),
        )

        assessment = query_exposure(
            self.repository,
            assessment_id="assess-1",
            generated_at="2026-08-15T00:00:00Z",
            market="spot",
            direction="SHORT",
            research_group="experimental",
            strategy="BOS",
        )

        self.assertEqual(assessment.position_count, 1)
        self.assertEqual(assessment.total_notional, 50.0)

    def test_does_not_mutate_persisted_trades(self) -> None:
        self.repository.save(
            trade(trade_id="1", notional=100.0),
        )

        before = self.repository.list_all()
        before_snapshot = [copy.deepcopy(t) for t in before]

        query_exposure(
            self.repository,
            assessment_id="assess-1",
            generated_at="2026-08-15T00:00:00Z",
        )

        after = self.repository.list_all()

        self.assertEqual(after, before_snapshot)

    def test_deterministic_scope_and_provenance_for_same_filters(self) -> None:
        self.repository.save(
            trade(trade_id="1", notional=10.0),
        )

        first = query_exposure(
            self.repository,
            assessment_id="assess-1",
            generated_at="2026-08-15T00:00:00Z",
            status=TradeStatus.ACTIVE,
        )
        second = query_exposure(
            self.repository,
            assessment_id="assess-1",
            generated_at="2026-08-15T00:00:00Z",
            status=TradeStatus.ACTIVE,
        )

        self.assertEqual(first.scope, second.scope)
        self.assertEqual(first.provenance, second.provenance)


if __name__ == "__main__":
    unittest.main()
