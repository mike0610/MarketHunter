"""
Tests for the Portfolio v1 Slice 2 assessment/read-model service.
"""

from __future__ import annotations

import copy
import unittest

from research.models.trade import ResearchTrade
from research.models.trade_status import TradeStatus

from portfolio_v1.assessment import (
    NO_CAPITAL_POLICY_REASON,
    assess_exposure,
    build_sizing_decision,
    compose_portfolio_decision,
)
from portfolio_v1.domain import (
    ExposureState,
    PortfolioOutcome,
    SizingState,
)


def trade(
    *,
    trade_id: str,
    notional: float = 100.0,
    status: TradeStatus = TradeStatus.ACTIVE,
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
        notional=notional,
        status=status,
    )


class AssessExposureTests(unittest.TestCase):
    def test_measured_collection_reports_correct_count_and_notional(self) -> None:
        trades = [
            trade(trade_id="1", notional=100.0),
            trade(trade_id="2", notional=250.0),
            trade(trade_id="3", notional=50.0),
        ]

        assessment = assess_exposure(
            trades,
            scope="active",
            assessment_id="assess-1",
            generated_at="2026-08-15T00:00:00Z",
        )

        self.assertEqual(assessment.state, ExposureState.MEASURED)
        self.assertEqual(assessment.position_count, 3)
        self.assertEqual(assessment.total_notional, 400.0)
        self.assertIn("active", assessment.provenance)

    def test_empty_scope_is_measured_zero_not_unknown(self) -> None:
        assessment = assess_exposure(
            [],
            scope="active",
            assessment_id="assess-1",
            generated_at="2026-08-15T00:00:00Z",
        )

        self.assertEqual(assessment.state, ExposureState.MEASURED)
        self.assertEqual(assessment.position_count, 0)
        self.assertEqual(assessment.total_notional, 0.0)

    def test_does_not_mutate_input_trades(self) -> None:
        trades = [trade(trade_id="1", notional=123.0)]
        before = copy.deepcopy(trades[0])

        assess_exposure(
            trades,
            scope="active",
            assessment_id="assess-1",
            generated_at="2026-08-15T00:00:00Z",
        )

        self.assertEqual(trades[0], before)


class BuildSizingDecisionTests(unittest.TestCase):
    def test_preserves_notional_without_recalculating(self) -> None:
        candidate = trade(trade_id="trade-1", notional=321.0)

        decision = build_sizing_decision(
            candidate,
            decision_id="sizing-1",
            decided_at="2026-08-15T00:00:00Z",
        )

        self.assertEqual(decision.requested_notional, 321.0)
        self.assertEqual(decision.candidate_reference, "trade-1")

    def test_never_approved_and_capital_available_stays_unset(self) -> None:
        candidate = trade(trade_id="trade-1", notional=100.0)

        decision = build_sizing_decision(
            candidate,
            decision_id="sizing-1",
            decided_at="2026-08-15T00:00:00Z",
        )

        self.assertNotEqual(decision.state, SizingState.APPROVED)
        self.assertEqual(decision.state, SizingState.NOT_APPLICABLE)
        self.assertIsNone(decision.capital_available)
        self.assertIn(NO_CAPITAL_POLICY_REASON, decision.reasons)

    def test_does_not_mutate_input_trade(self) -> None:
        candidate = trade(trade_id="trade-1", notional=100.0)
        before = copy.deepcopy(candidate)

        build_sizing_decision(
            candidate,
            decision_id="sizing-1",
            decided_at="2026-08-15T00:00:00Z",
        )

        self.assertEqual(candidate, before)

    def test_deterministic_provenance_and_candidate_reference(self) -> None:
        candidate = trade(trade_id="trade-42", notional=10.0)

        first = build_sizing_decision(
            candidate,
            decision_id="sizing-1",
            decided_at="2026-08-15T00:00:00Z",
        )
        second = build_sizing_decision(
            candidate,
            decision_id="sizing-1",
            decided_at="2026-08-15T00:00:00Z",
        )

        self.assertEqual(first.provenance, second.provenance)
        self.assertEqual(first.candidate_reference, "trade-42")
        self.assertIn("trade-42", first.provenance)


class ComposePortfolioDecisionTests(unittest.TestCase):
    def test_not_applicable_sizing_never_becomes_proceed(self) -> None:
        candidate = trade(trade_id="trade-1", notional=100.0)

        exposure = assess_exposure(
            [candidate],
            scope="active",
            assessment_id="assess-1",
            generated_at="2026-08-15T00:00:00Z",
        )
        sizing = build_sizing_decision(
            candidate,
            decision_id="sizing-1",
            decided_at="2026-08-15T00:00:00Z",
        )

        decision = compose_portfolio_decision(
            decision_id="decision-1",
            candidate_reference=candidate.id,
            provenance="portfolio_v1.assessment",
            decided_at="2026-08-15T00:00:00Z",
            exposure=exposure,
            sizing=sizing,
        )

        self.assertNotEqual(decision.outcome, PortfolioOutcome.PROCEED)
        self.assertEqual(decision.outcome, PortfolioOutcome.NOT_APPLICABLE)
        self.assertTrue(decision.reasons)

    def test_unknown_sizing_does_not_become_proceed(self) -> None:
        from portfolio_v1.domain import PositionSizingDecision

        candidate = trade(trade_id="trade-1", notional=100.0)

        exposure = assess_exposure(
            [candidate],
            scope="active",
            assessment_id="assess-1",
            generated_at="2026-08-15T00:00:00Z",
        )
        sizing = PositionSizingDecision(
            decision_id="sizing-1",
            candidate_reference=candidate.id,
            provenance="test",
            decided_at="2026-08-15T00:00:00Z",
            state=SizingState.UNKNOWN,
            reasons=("no data",),
        )

        decision = compose_portfolio_decision(
            decision_id="decision-1",
            candidate_reference=candidate.id,
            provenance="portfolio_v1.assessment",
            decided_at="2026-08-15T00:00:00Z",
            exposure=exposure,
            sizing=sizing,
        )

        self.assertNotEqual(decision.outcome, PortfolioOutcome.PROCEED)
        self.assertEqual(decision.outcome, PortfolioOutcome.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
