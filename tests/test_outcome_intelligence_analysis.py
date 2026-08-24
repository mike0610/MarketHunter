"""
MarketHunter

Tests for Outcome Intelligence analysis
(tools/outcome_intelligence/analysis.py).
"""

from __future__ import annotations

import unittest

from tools.outcome_intelligence.analysis import (
    CANDIDATE_LOSER_WIN_RATE_THRESHOLD,
    CANDIDATE_SURVIVOR_WIN_RATE_THRESHOLD,
    GroupDisposition,
    MIN_SAMPLE_SIZE_FOR_STRONGER_EVIDENCE,
    MIN_SAMPLE_SIZE_FOR_VERDICT,
    OutcomeIntelligenceDataError,
    PERSISTENCE_MIN_CONSECUTIVE_RUNS,
    classify_group,
    daily_analysis,
    render_daily_summary,
    render_weekly_summary,
    weekly_analysis,
)


def make_group_row(**overrides) -> dict:
    row = dict(
        label="Breakout",
        total=100,
        clean_completed=70,
        wins=40,
        losses=30,
        win_rate=57.1,
        total_profit=12.5,
    )
    row.update(overrides)
    return row


def make_setup_reasons(**dimension_overrides) -> dict:
    payload = {
        "by_strategy": [],
        "by_setup_reason": [],
        "by_close_reason": [],
        "by_status": [],
        "by_outcome": [],
        "by_outcome_group": [],
    }
    payload.update(dimension_overrides)
    return payload


class ClassifyGroupTests(unittest.TestCase):
    def test_below_minimum_sample_is_insufficient_regardless_of_win_rate(self) -> None:
        for win_rate in (0.0, 40.0, 55.0, 100.0):
            with self.subTest(win_rate=win_rate):
                self.assertEqual(
                    classify_group(
                        clean_completed=MIN_SAMPLE_SIZE_FOR_VERDICT - 1,
                        win_rate=win_rate,
                    ),
                    GroupDisposition.INSUFFICIENT_EVIDENCE,
                )

    def test_sufficient_sample_middle_win_rate_is_watch(self) -> None:
        self.assertEqual(
            classify_group(
                clean_completed=MIN_SAMPLE_SIZE_FOR_VERDICT,
                win_rate=(
                    CANDIDATE_LOSER_WIN_RATE_THRESHOLD
                    + CANDIDATE_SURVIVOR_WIN_RATE_THRESHOLD
                )
                / 2,
            ),
            GroupDisposition.WATCH,
        )

    def test_sufficient_but_below_stronger_and_loser_win_rate_is_candidate_loser(self) -> None:
        self.assertEqual(
            classify_group(
                clean_completed=MIN_SAMPLE_SIZE_FOR_VERDICT,
                win_rate=CANDIDATE_LOSER_WIN_RATE_THRESHOLD,
            ),
            GroupDisposition.CANDIDATE_LOSER,
        )

    def test_sufficient_but_below_stronger_and_survivor_win_rate_is_candidate_survivor(self) -> None:
        self.assertEqual(
            classify_group(
                clean_completed=MIN_SAMPLE_SIZE_FOR_VERDICT,
                win_rate=CANDIDATE_SURVIVOR_WIN_RATE_THRESHOLD,
            ),
            GroupDisposition.CANDIDATE_SURVIVOR,
        )

    def test_large_sample_loser_win_rate_is_stronger_evidence(self) -> None:
        self.assertEqual(
            classify_group(
                clean_completed=MIN_SAMPLE_SIZE_FOR_STRONGER_EVIDENCE,
                win_rate=CANDIDATE_LOSER_WIN_RATE_THRESHOLD,
            ),
            GroupDisposition.STRONGER_EVIDENCE,
        )

    def test_large_sample_survivor_win_rate_is_stronger_evidence(self) -> None:
        self.assertEqual(
            classify_group(
                clean_completed=MIN_SAMPLE_SIZE_FOR_STRONGER_EVIDENCE,
                win_rate=CANDIDATE_SURVIVOR_WIN_RATE_THRESHOLD,
            ),
            GroupDisposition.STRONGER_EVIDENCE,
        )

    def test_large_sample_middle_win_rate_is_still_watch(self) -> None:
        self.assertEqual(
            classify_group(
                clean_completed=MIN_SAMPLE_SIZE_FOR_STRONGER_EVIDENCE,
                win_rate=(
                    CANDIDATE_LOSER_WIN_RATE_THRESHOLD
                    + CANDIDATE_SURVIVOR_WIN_RATE_THRESHOLD
                )
                / 2,
            ),
            GroupDisposition.WATCH,
        )


class DailyAnalysisTests(unittest.TestCase):
    def test_all_six_dimensions_present_in_report(self) -> None:
        prior = make_setup_reasons()
        latest = make_setup_reasons()

        result = daily_analysis(
            prior_setup_reasons=prior,
            latest_setup_reasons=latest,
            prior_run_id="run-1",
            latest_run_id="run-2",
        )

        dimensions = {report.dimension for report in result.dimension_reports}
        self.assertEqual(
            dimensions,
            {
                "by_strategy",
                "by_setup_reason",
                "by_close_reason",
                "by_status",
                "by_outcome",
                "by_outcome_group",
            },
        )

    def test_delta_computed_against_prior_run(self) -> None:
        prior = make_setup_reasons(
            by_strategy=[
                make_group_row(
                    label="Breakout",
                    clean_completed=50,
                    wins=25,
                    losses=25,
                    win_rate=50.0,
                    total_profit=10.0,
                )
            ]
        )
        latest = make_setup_reasons(
            by_strategy=[
                make_group_row(
                    label="Breakout",
                    clean_completed=60,
                    wins=30,
                    losses=30,
                    win_rate=50.0,
                    total_profit=15.0,
                )
            ]
        )

        result = daily_analysis(
            prior_setup_reasons=prior,
            latest_setup_reasons=latest,
            prior_run_id="run-1",
            latest_run_id="run-2",
        )

        by_strategy_report = next(
            report
            for report in result.dimension_reports
            if report.dimension == "by_strategy"
        )
        change = by_strategy_report.changes[0]

        self.assertEqual(change.delta_clean_completed, 10)
        self.assertEqual(change.delta_wins, 5)
        self.assertEqual(change.delta_losses, 5)
        self.assertAlmostEqual(change.delta_total_profit, 5.0)
        self.assertIsNotNone(change.prior)

    def test_new_group_has_none_prior(self) -> None:
        prior = make_setup_reasons(by_strategy=[])
        latest = make_setup_reasons(
            by_strategy=[make_group_row(label="New Strategy")]
        )

        result = daily_analysis(
            prior_setup_reasons=prior,
            latest_setup_reasons=latest,
            prior_run_id="run-1",
            latest_run_id="run-2",
        )

        by_strategy_report = next(
            report
            for report in result.dimension_reports
            if report.dimension == "by_strategy"
        )
        change = by_strategy_report.changes[0]

        self.assertIsNone(change.prior)
        self.assertEqual(change.delta_clean_completed, change.latest.clean_completed)

    def test_disposition_computed_from_latest_row_only(self) -> None:
        prior = make_setup_reasons(
            by_strategy=[
                make_group_row(label="Breakout", clean_completed=5, win_rate=10.0)
            ]
        )
        latest = make_setup_reasons(
            by_strategy=[
                make_group_row(
                    label="Breakout",
                    clean_completed=MIN_SAMPLE_SIZE_FOR_VERDICT,
                    win_rate=CANDIDATE_LOSER_WIN_RATE_THRESHOLD,
                )
            ]
        )

        result = daily_analysis(
            prior_setup_reasons=prior,
            latest_setup_reasons=latest,
            prior_run_id="run-1",
            latest_run_id="run-2",
        )

        by_strategy_report = next(
            report
            for report in result.dimension_reports
            if report.dimension == "by_strategy"
        )
        change = by_strategy_report.changes[0]

        self.assertEqual(change.disposition, GroupDisposition.CANDIDATE_LOSER)

    def test_missing_field_fails_closed(self) -> None:
        latest = make_setup_reasons(
            by_strategy=[{"label": "Breakout"}]  # missing required fields
        )

        with self.assertRaises(OutcomeIntelligenceDataError):
            daily_analysis(
                prior_setup_reasons=make_setup_reasons(),
                latest_setup_reasons=latest,
                prior_run_id="run-1",
                latest_run_id="run-2",
            )

    def test_daily_analysis_never_disables_anything(self) -> None:
        # Structural guarantee: DailyAnalysisResult carries no field or
        # method that could represent an enable/disable action - it is
        # a pure read-only report.
        result = daily_analysis(
            prior_setup_reasons=make_setup_reasons(),
            latest_setup_reasons=make_setup_reasons(),
            prior_run_id="run-1",
            latest_run_id="run-2",
        )
        result_attrs = {name for name in dir(result) if not name.startswith("_")}
        for forbidden in ("disable", "enable", "promote", "apply", "execute"):
            for name in result_attrs:
                self.assertNotIn(forbidden, name.lower())


class WeeklyAnalysisTests(unittest.TestCase):
    def _loser_row(self, **overrides) -> dict:
        base = dict(
            clean_completed=MIN_SAMPLE_SIZE_FOR_VERDICT,
            win_rate=CANDIDATE_LOSER_WIN_RATE_THRESHOLD,
            wins=0,
        )
        base.update(overrides)
        return make_group_row(**base)

    def _survivor_row(self, **overrides) -> dict:
        return make_group_row(
            clean_completed=MIN_SAMPLE_SIZE_FOR_VERDICT,
            win_rate=CANDIDATE_SURVIVOR_WIN_RATE_THRESHOLD,
            **overrides,
        )

    def test_fewer_than_minimum_runs_yields_no_persistence_claim(self) -> None:
        runs = [
            (
                f"run-{i}",
                make_setup_reasons(by_strategy=[self._loser_row()]),
            )
            for i in range(PERSISTENCE_MIN_CONSECUTIVE_RUNS - 1)
        ]

        result = weekly_analysis(runs)

        self.assertEqual(result.persistent_losers, ())
        self.assertEqual(result.persistent_survivors, ())

    def test_loser_leaning_every_run_is_persistent(self) -> None:
        runs = [
            (
                f"run-{i}",
                make_setup_reasons(by_strategy=[self._loser_row()]),
            )
            for i in range(PERSISTENCE_MIN_CONSECUTIVE_RUNS)
        ]

        result = weekly_analysis(runs)

        self.assertEqual(len(result.persistent_losers), 1)
        self.assertEqual(result.persistent_losers[0].label, "Breakout")
        self.assertEqual(result.persistent_losers[0].dimension, "by_strategy")

    def test_survivor_leaning_every_run_is_persistent(self) -> None:
        runs = [
            (
                f"run-{i}",
                make_setup_reasons(by_strategy=[self._survivor_row()]),
            )
            for i in range(PERSISTENCE_MIN_CONSECUTIVE_RUNS)
        ]

        result = weekly_analysis(runs)

        self.assertEqual(len(result.persistent_survivors), 1)
        self.assertEqual(result.persistent_survivors[0].label, "Breakout")

    def test_flip_from_loser_to_watch_breaks_persistence(self) -> None:
        runs = [
            ("run-0", make_setup_reasons(by_strategy=[self._loser_row()])),
            (
                "run-1",
                make_setup_reasons(
                    by_strategy=[
                        make_group_row(
                            clean_completed=MIN_SAMPLE_SIZE_FOR_VERDICT,
                            win_rate=50.0,
                        )
                    ]
                ),
            ),
            ("run-2", make_setup_reasons(by_strategy=[self._loser_row()])),
        ]

        result = weekly_analysis(runs)

        self.assertEqual(result.persistent_losers, ())

    def test_group_absent_from_one_run_is_excluded(self) -> None:
        runs = [
            ("run-0", make_setup_reasons(by_strategy=[self._loser_row()])),
            ("run-1", make_setup_reasons(by_strategy=[])),
            ("run-2", make_setup_reasons(by_strategy=[self._loser_row()])),
        ]

        result = weekly_analysis(runs)

        self.assertEqual(result.persistent_losers, ())

    def test_filter_would_remove_profitable_cases_flag(self) -> None:
        runs = [
            (
                f"run-{i}",
                make_setup_reasons(by_strategy=[self._loser_row(wins=3)]),
            )
            for i in range(PERSISTENCE_MIN_CONSECUTIVE_RUNS)
        ]

        result = weekly_analysis(runs)

        self.assertTrue(
            result.persistent_losers[0].filter_would_remove_profitable_cases
        )
        self.assertEqual(result.persistent_losers[0].latest_wins, 3)

    def test_no_profitable_cases_flag_false_when_zero_wins(self) -> None:
        runs = [
            (
                f"run-{i}",
                make_setup_reasons(by_strategy=[self._loser_row(wins=0)]),
            )
            for i in range(PERSISTENCE_MIN_CONSECUTIVE_RUNS)
        ]

        result = weekly_analysis(runs)

        self.assertFalse(
            result.persistent_losers[0].filter_would_remove_profitable_cases
        )

    def test_weekly_analysis_never_disables_anything(self) -> None:
        result = weekly_analysis(
            [
                (f"run-{i}", make_setup_reasons())
                for i in range(PERSISTENCE_MIN_CONSECUTIVE_RUNS)
            ]
        )
        result_attrs = {name for name in dir(result) if not name.startswith("_")}
        for forbidden in ("disable", "enable", "promote", "apply", "execute"):
            for name in result_attrs:
                self.assertNotIn(forbidden, name.lower())


class RenderSummaryTests(unittest.TestCase):
    def test_daily_summary_reports_no_flags_when_none_crossed(self) -> None:
        result = daily_analysis(
            prior_setup_reasons=make_setup_reasons(),
            latest_setup_reasons=make_setup_reasons(),
            prior_run_id="run-1",
            latest_run_id="run-2",
        )

        summary = render_daily_summary(result)

        self.assertIn("No group crossed", summary)
        self.assertIsInstance(summary, str)

    def test_daily_summary_flags_candidate_loser(self) -> None:
        prior = make_setup_reasons()
        latest = make_setup_reasons(
            by_strategy=[
                make_group_row(
                    label="Breakout",
                    clean_completed=MIN_SAMPLE_SIZE_FOR_VERDICT,
                    win_rate=CANDIDATE_LOSER_WIN_RATE_THRESHOLD,
                )
            ]
        )

        result = daily_analysis(
            prior_setup_reasons=prior,
            latest_setup_reasons=latest,
            prior_run_id="run-1",
            latest_run_id="run-2",
        )

        summary = render_daily_summary(result)

        self.assertIn("Breakout", summary)
        self.assertIn("CANDIDATE_LOSER", summary)

    def test_weekly_summary_reports_no_persistence_when_insufficient_runs(self) -> None:
        result = weekly_analysis([("run-0", make_setup_reasons())])

        summary = render_weekly_summary(result)

        self.assertIn("No persistent losers or survivors", summary)

    def test_weekly_summary_flags_persistent_loser_with_warning(self) -> None:
        runs = [
            (
                f"run-{i}",
                make_setup_reasons(
                    by_strategy=[
                        make_group_row(
                            clean_completed=MIN_SAMPLE_SIZE_FOR_VERDICT,
                            win_rate=CANDIDATE_LOSER_WIN_RATE_THRESHOLD,
                            wins=2,
                        )
                    ]
                ),
            )
            for i in range(PERSISTENCE_MIN_CONSECUTIVE_RUNS)
        ]

        result = weekly_analysis(runs)
        summary = render_weekly_summary(result)

        self.assertIn("Breakout", summary)
        self.assertIn("also remove", summary)


if __name__ == "__main__":
    unittest.main()
