"""
Tests for the Portfolio v1 Slice 4 exposure snapshot composition.
"""

from __future__ import annotations

import unittest

from portfolio_v1.domain import ExposureAssessment, ExposureState
from portfolio_v1.exposure_snapshot import (
    PortfolioExposureSnapshot,
    compose_exposure_snapshot,
)


def measured(
    *,
    assessment_id: str,
    scope: str = "persisted_research_trades:all",
    position_count: int = 0,
    total_notional: float = 0.0,
) -> ExposureAssessment:
    return ExposureAssessment(
        assessment_id=assessment_id,
        scope=scope,
        provenance=f"research_trades:{scope}",
        generated_at="2026-08-15T00:00:00Z",
        state=ExposureState.MEASURED,
        position_count=position_count,
        total_notional=total_notional,
    )


def unknown(
    *,
    assessment_id: str,
    scope: str = "persisted_research_trades:all",
) -> ExposureAssessment:
    return ExposureAssessment(
        assessment_id=assessment_id,
        scope=scope,
        provenance=f"research_trades:{scope}",
        generated_at="2026-08-15T00:00:00Z",
        state=ExposureState.UNKNOWN,
    )


def not_applicable(
    *,
    assessment_id: str,
    scope: str = "persisted_research_trades:all",
) -> ExposureAssessment:
    return ExposureAssessment(
        assessment_id=assessment_id,
        scope=scope,
        provenance=f"research_trades:{scope}",
        generated_at="2026-08-15T00:00:00Z",
        state=ExposureState.NOT_APPLICABLE,
    )


class ComposeExposureSnapshotTests(unittest.TestCase):
    def test_all_measured_produces_measured_snapshot(self) -> None:
        snapshot = compose_exposure_snapshot(
            [
                measured(assessment_id="a1", position_count=2, total_notional=200.0),
                measured(assessment_id="a2", position_count=1, total_notional=50.0),
            ],
            snapshot_id="snap-1",
            generated_at="2026-08-15T00:00:00Z",
            provenance="portfolio_v1:exposure_snapshot",
        )

        self.assertEqual(snapshot.state, ExposureState.MEASURED)
        self.assertEqual(snapshot.reasons, ())
        self.assertEqual(len(snapshot.assessments), 2)

    def test_one_unknown_makes_snapshot_unknown(self) -> None:
        snapshot = compose_exposure_snapshot(
            [
                measured(assessment_id="a1"),
                unknown(assessment_id="a2"),
            ],
            snapshot_id="snap-1",
            generated_at="2026-08-15T00:00:00Z",
            provenance="portfolio_v1:exposure_snapshot",
        )

        self.assertEqual(snapshot.state, ExposureState.UNKNOWN)
        self.assertTrue(snapshot.reasons)

    def test_unknown_does_not_become_zero(self) -> None:
        snapshot = compose_exposure_snapshot(
            [unknown(assessment_id="a1")],
            snapshot_id="snap-1",
            generated_at="2026-08-15T00:00:00Z",
            provenance="portfolio_v1:exposure_snapshot",
        )

        self.assertEqual(snapshot.state, ExposureState.UNKNOWN)
        self.assertNotEqual(snapshot.state, ExposureState.MEASURED)

    def test_not_applicable_without_unknown_makes_snapshot_not_applicable(
        self,
    ) -> None:
        snapshot = compose_exposure_snapshot(
            [
                measured(assessment_id="a1"),
                not_applicable(assessment_id="a2"),
            ],
            snapshot_id="snap-1",
            generated_at="2026-08-15T00:00:00Z",
            provenance="portfolio_v1:exposure_snapshot",
        )

        self.assertEqual(snapshot.state, ExposureState.NOT_APPLICABLE)
        self.assertTrue(snapshot.reasons)

    def test_unknown_outranks_not_applicable_when_both_present(self) -> None:
        snapshot = compose_exposure_snapshot(
            [
                unknown(assessment_id="a1"),
                not_applicable(assessment_id="a2"),
            ],
            snapshot_id="snap-1",
            generated_at="2026-08-15T00:00:00Z",
            provenance="portfolio_v1:exposure_snapshot",
        )

        self.assertEqual(snapshot.state, ExposureState.UNKNOWN)

    def test_measured_zero_exposure_stays_measured_not_unknown(self) -> None:
        snapshot = compose_exposure_snapshot(
            [
                measured(
                    assessment_id="a1",
                    position_count=0,
                    total_notional=0.0,
                ),
            ],
            snapshot_id="snap-1",
            generated_at="2026-08-15T00:00:00Z",
            provenance="portfolio_v1:exposure_snapshot",
        )

        self.assertEqual(snapshot.state, ExposureState.MEASURED)

    def test_child_assessments_are_preserved_unchanged(self) -> None:
        child = measured(
            assessment_id="a1",
            position_count=3,
            total_notional=300.0,
        )

        snapshot = compose_exposure_snapshot(
            [child],
            snapshot_id="snap-1",
            generated_at="2026-08-15T00:00:00Z",
            provenance="portfolio_v1:exposure_snapshot",
        )

        self.assertIs(snapshot.assessments[0], child)
        self.assertEqual(snapshot.assessments[0].position_count, 3)
        self.assertEqual(snapshot.assessments[0].total_notional, 300.0)

    def test_deterministic_for_identical_inputs(self) -> None:
        children = [
            measured(assessment_id="a1", position_count=1, total_notional=10.0),
        ]

        first = compose_exposure_snapshot(
            children,
            snapshot_id="snap-1",
            generated_at="2026-08-15T00:00:00Z",
            provenance="portfolio_v1:exposure_snapshot",
        )
        second = compose_exposure_snapshot(
            children,
            snapshot_id="snap-1",
            generated_at="2026-08-15T00:00:00Z",
            provenance="portfolio_v1:exposure_snapshot",
        )

        self.assertEqual(first, second)

    def test_duplicate_assessment_id_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            compose_exposure_snapshot(
                [
                    measured(assessment_id="a1"),
                    measured(assessment_id="a1"),
                ],
                snapshot_id="snap-1",
                generated_at="2026-08-15T00:00:00Z",
                provenance="portfolio_v1:exposure_snapshot",
            )

    def test_empty_assessment_collection_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            compose_exposure_snapshot(
                [],
                snapshot_id="snap-1",
                generated_at="2026-08-15T00:00:00Z",
                provenance="portfolio_v1:exposure_snapshot",
            )


class PortfolioExposureSnapshotInvariantTests(unittest.TestCase):
    def test_is_frozen(self) -> None:
        snapshot = compose_exposure_snapshot(
            [measured(assessment_id="a1")],
            snapshot_id="snap-1",
            generated_at="2026-08-15T00:00:00Z",
            provenance="portfolio_v1:exposure_snapshot",
        )

        with self.assertRaises(Exception):
            snapshot.state = ExposureState.UNKNOWN  # type: ignore[misc]

    def test_measured_snapshot_cannot_carry_reasons(self) -> None:
        with self.assertRaises(ValueError):
            PortfolioExposureSnapshot(
                snapshot_id="snap-1",
                generated_at="2026-08-15T00:00:00Z",
                provenance="portfolio_v1:exposure_snapshot",
                assessments=(measured(assessment_id="a1"),),
                state=ExposureState.MEASURED,
                reasons=("should not be here",),
            )

    def test_snapshot_id_required(self) -> None:
        with self.assertRaises(ValueError):
            PortfolioExposureSnapshot(
                snapshot_id="",
                generated_at="2026-08-15T00:00:00Z",
                provenance="portfolio_v1:exposure_snapshot",
                assessments=(measured(assessment_id="a1"),),
                state=ExposureState.MEASURED,
            )


if __name__ == "__main__":
    unittest.main()
