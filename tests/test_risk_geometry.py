"""
Tests for risk geometry validation.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from research.setup.risk_geometry import RiskGeometryDetector


class RiskGeometryTests(unittest.TestCase):
    def test_blocks_wide_stop_percent(self) -> None:
        detector = RiskGeometryDetector(
            max_stop_distance_percent=10.0,
        )

        assessment = detector.assess_values(
            direction="LONG",
            entry_price=100.0,
            stop_loss=65.0,
        )

        self.assertFalse(assessment.valid)
        self.assertIn(
            "stop distance",
            assessment.summary,
        )

    def test_blocks_wrong_side_stop(self) -> None:
        detector = RiskGeometryDetector()

        assessment = detector.assess_values(
            direction="LONG",
            entry_price=100.0,
            stop_loss=105.0,
        )

        self.assertFalse(assessment.valid)
        self.assertIn(
            "wrong side",
            assessment.summary,
        )

    def test_allows_reasonable_stop(self) -> None:
        detector = RiskGeometryDetector()

        assessment = detector.assess_values(
            direction="SHORT",
            entry_price=100.0,
            stop_loss=105.0,
            atr14=1.0,
        )

        self.assertTrue(assessment.valid)

    def test_blocks_fvg_entry_far_below_zone(self) -> None:
        detector = RiskGeometryDetector(
            max_entry_zone_distance_percent=0.25,
        )

        assessment = detector.assess_values(
            direction="LONG",
            entry_price=95.0,
            stop_loss=90.0,
            strategy="FVG",
            signal_metadata={
                "setup_zone_type": "FVG",
                "setup_zone_lower": 97.0,
                "setup_zone_upper": 98.9,
            },
        )

        self.assertFalse(assessment.valid)
        self.assertIn(
            "FVG entry",
            assessment.summary,
        )

    def test_allows_fvg_entry_inside_zone(self) -> None:
        detector = RiskGeometryDetector()

        assessment = detector.assess(
            snapshot=SimpleNamespace(
                atr14=1.0,
            ),
            direction="LONG",
            entry_price=97.5,
            stop_loss=94.0,
            strategy="FVG",
            signal_metadata={
                "setup_zone_type": "FVG",
                "setup_zone_lower": 97.0,
                "setup_zone_upper": 98.9,
            },
        )

        self.assertTrue(assessment.valid)
        self.assertEqual(
            assessment.entry_zone_relation,
            "inside",
        )


if __name__ == "__main__":
    unittest.main()
