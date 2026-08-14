"""
Tests for the Portfolio v1 Slice 1 domain layer.
"""

from __future__ import annotations

import unittest

from portfolio_v1.domain import (
    ExposureAssessment,
    ExposureState,
    PortfolioDecision,
    PortfolioOutcome,
    PositionSizingDecision,
    SizingState,
)


def exposure(
    *,
    state: ExposureState = ExposureState.MEASURED,
    position_count: int | None = 1,
    total_notional: float | None = 100.0,
) -> ExposureAssessment:
    return ExposureAssessment(
        assessment_id="exp-1",
        scope="market:futures",
        provenance="research_trades:active+waiting_entry",
        generated_at="2026-08-14T00:00:00Z",
        state=state,
        position_count=position_count,
        total_notional=total_notional,
    )


def sizing(
    *,
    state: SizingState = SizingState.APPROVED,
    requested_notional: float | None = 100.0,
    reasons: tuple[str, ...] = (),
) -> PositionSizingDecision:
    return PositionSizingDecision(
        decision_id="sizing-1",
        candidate_reference="trade-1",
        provenance="research_trades:notional",
        decided_at="2026-08-14T00:00:00Z",
        state=state,
        requested_notional=requested_notional,
        reasons=reasons,
    )


class ExposureAssessmentTests(unittest.TestCase):
    def test_measured_requires_count_and_notional(self) -> None:
        with self.assertRaises(ValueError):
            ExposureAssessment(
                assessment_id="exp-1",
                scope="total",
                provenance="test",
                generated_at="2026-08-14T00:00:00Z",
                state=ExposureState.MEASURED,
            )

    def test_measured_rejects_negative_position_count(self) -> None:
        with self.assertRaises(ValueError):
            ExposureAssessment(
                assessment_id="exp-1",
                scope="total",
                provenance="test",
                generated_at="2026-08-14T00:00:00Z",
                state=ExposureState.MEASURED,
                position_count=-1,
                total_notional=0.0,
            )

    def test_unknown_cannot_carry_numbers(self) -> None:
        with self.assertRaises(ValueError):
            ExposureAssessment(
                assessment_id="exp-1",
                scope="total",
                provenance="test",
                generated_at="2026-08-14T00:00:00Z",
                state=ExposureState.UNKNOWN,
                position_count=0,
            )

    def test_not_applicable_is_valid_with_no_numbers(self) -> None:
        assessment = ExposureAssessment(
            assessment_id="exp-1",
            scope="total",
            provenance="test",
            generated_at="2026-08-14T00:00:00Z",
            state=ExposureState.NOT_APPLICABLE,
        )

        self.assertIsNone(assessment.position_count)
        self.assertIsNone(assessment.total_notional)

    def test_is_frozen(self) -> None:
        assessment = exposure()

        with self.assertRaises(Exception):
            assessment.total_notional = 999.0  # type: ignore[misc]


class PositionSizingDecisionTests(unittest.TestCase):
    def test_approved_requires_requested_notional(self) -> None:
        with self.assertRaises(ValueError):
            PositionSizingDecision(
                decision_id="sizing-1",
                candidate_reference="trade-1",
                provenance="test",
                decided_at="2026-08-14T00:00:00Z",
                state=SizingState.APPROVED,
            )

    def test_blocked_requires_reasons(self) -> None:
        with self.assertRaises(ValueError):
            PositionSizingDecision(
                decision_id="sizing-1",
                candidate_reference="trade-1",
                provenance="test",
                decided_at="2026-08-14T00:00:00Z",
                state=SizingState.BLOCKED,
            )

    def test_not_applicable_requires_reasons(self) -> None:
        decision = PositionSizingDecision(
            decision_id="sizing-1",
            candidate_reference="trade-1",
            provenance="test",
            decided_at="2026-08-14T00:00:00Z",
            state=SizingState.NOT_APPLICABLE,
            reasons=("No real capital-availability source exists yet.",),
        )

        self.assertIsNone(decision.requested_notional)
        self.assertIsNone(decision.capital_available)

    def test_candidate_reference_required(self) -> None:
        with self.assertRaises(ValueError):
            PositionSizingDecision(
                decision_id="sizing-1",
                candidate_reference="",
                provenance="test",
                decided_at="2026-08-14T00:00:00Z",
                state=SizingState.UNKNOWN,
                reasons=("missing data",),
            )


class PortfolioDecisionTests(unittest.TestCase):
    def test_proceed_requires_measured_exposure_and_approved_sizing(self) -> None:
        decision = PortfolioDecision(
            decision_id="decision-1",
            candidate_reference="trade-1",
            provenance="test",
            decided_at="2026-08-14T00:00:00Z",
            exposure=exposure(state=ExposureState.MEASURED),
            sizing=sizing(state=SizingState.APPROVED),
            outcome=PortfolioOutcome.PROCEED,
        )

        self.assertEqual(decision.outcome, PortfolioOutcome.PROCEED)

    def test_proceed_rejected_when_exposure_unknown(self) -> None:
        with self.assertRaises(ValueError):
            PortfolioDecision(
                decision_id="decision-1",
                candidate_reference="trade-1",
                provenance="test",
                decided_at="2026-08-14T00:00:00Z",
                exposure=exposure(
                    state=ExposureState.UNKNOWN,
                    position_count=None,
                    total_notional=None,
                ),
                sizing=sizing(state=SizingState.APPROVED),
                outcome=PortfolioOutcome.PROCEED,
            )

    def test_proceed_rejected_when_sizing_not_approved(self) -> None:
        with self.assertRaises(ValueError):
            PortfolioDecision(
                decision_id="decision-1",
                candidate_reference="trade-1",
                provenance="test",
                decided_at="2026-08-14T00:00:00Z",
                exposure=exposure(),
                sizing=sizing(
                    state=SizingState.BLOCKED,
                    requested_notional=None,
                    reasons=("blocked",),
                ),
                outcome=PortfolioOutcome.PROCEED,
            )

    def test_non_proceed_requires_reasons(self) -> None:
        with self.assertRaises(ValueError):
            PortfolioDecision(
                decision_id="decision-1",
                candidate_reference="trade-1",
                provenance="test",
                decided_at="2026-08-14T00:00:00Z",
                exposure=exposure(
                    state=ExposureState.UNKNOWN,
                    position_count=None,
                    total_notional=None,
                ),
                sizing=sizing(
                    state=SizingState.UNKNOWN,
                    requested_notional=None,
                    reasons=("no data",),
                ),
                outcome=PortfolioOutcome.UNKNOWN,
            )

    def test_unknown_outcome_valid_with_reasons(self) -> None:
        decision = PortfolioDecision(
            decision_id="decision-1",
            candidate_reference="trade-1",
            provenance="test",
            decided_at="2026-08-14T00:00:00Z",
            exposure=exposure(
                state=ExposureState.UNKNOWN,
                position_count=None,
                total_notional=None,
            ),
            sizing=sizing(
                state=SizingState.UNKNOWN,
                requested_notional=None,
                reasons=("no data",),
            ),
            outcome=PortfolioOutcome.UNKNOWN,
            reasons=("Insufficient exposure data to proceed.",),
        )

        self.assertEqual(decision.outcome, PortfolioOutcome.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
