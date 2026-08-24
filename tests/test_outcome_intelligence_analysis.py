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
    GROUP_LEVEL_UNSUPPORTED_METRICS,
    GroupDisposition,
    MIN_SAMPLE_SIZE_FOR_STRONGER_EVIDENCE,
    MIN_SAMPLE_SIZE_FOR_VERDICT,
    OutcomeIntelligenceDataError,
    PERSISTENCE_MIN_CONSECUTIVE_RUNS,
    classify_group,
    daily_analysis,
    is_loser_leaning,
    is_survivor_leaning,
    render_daily_summary,
    render_weekly_summary,
    weekly_analysis,
)


def make_group_row(**overrides) -> dict:
    # Defaults: 40 wins + 30 losses = 70 decisive, win_rate = 40/70 =
    # 57.1..%, clean_completed = 70 (zero breakeven by default - tests
    # that need breakeven padding override clean_completed directly).
    row = dict(
        label="Breakout",
        total=100,
        clean_completed=70,
        wins=40,
        losses=30,
        win_rate=57.1,
        total_profit=12.5,
        average_rr=1.5,
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


def build_cumulative_runs(
    deltas: list[tuple[int, int, int]],
    label: str = "Breakout",
) -> list[tuple[str, dict]]:
    """
    Build PERSISTENCE-window-shaped run history for one `by_strategy`
    group: `len(deltas) + 1` runs, where `deltas[i]` is
    (delta_wins, delta_losses, delta_breakeven) - the incremental
    evidence between run i and run i+1. delta_breakeven pads
    clean_completed beyond decisive (wins + losses) without
    contributing to win_rate, exactly like real breakeven trades.
    Cumulative counters grow monotonically, as the real
    `setup-reasons` endpoint does.
    """

    cumulative_wins = 0
    cumulative_losses = 0
    cumulative_clean_completed = 0

    runs = [
        (
            "run-0",
            make_setup_reasons(
                by_strategy=[
                    make_group_row(
                        label=label,
                        total=0,
                        clean_completed=0,
                        wins=0,
                        losses=0,
                        win_rate=0.0,
                        total_profit=0.0,
                    )
                ]
            ),
        )
    ]

    for index, (delta_wins, delta_losses, delta_breakeven) in enumerate(
        deltas, start=1
    ):
        cumulative_wins += delta_wins
        cumulative_losses += delta_losses
        cumulative_clean_completed += delta_wins + delta_losses + delta_breakeven
        decisive = cumulative_wins + cumulative_losses
        win_rate = (cumulative_wins / decisive) * 100.0 if decisive else 0.0

        runs.append(
            (
                f"run-{index}",
                make_setup_reasons(
                    by_strategy=[
                        make_group_row(
                            label=label,
                            total=cumulative_clean_completed,
                            clean_completed=cumulative_clean_completed,
                            wins=cumulative_wins,
                            losses=cumulative_losses,
                            win_rate=win_rate,
                            total_profit=0.0,
                        )
                    ]
                ),
            )
        )

    return runs


# Incremental deltas (delta_wins, delta_losses, delta_breakeven) that
# make every window loser-leaning with zero breakeven padding:
# 8/(8+12) = 40.0% win rate <= CANDIDATE_LOSER_WIN_RATE_THRESHOLD,
# decisive = 20 = MIN_SAMPLE_SIZE_FOR_VERDICT.
LOSER_WINDOW = (8, 12, 0)
# 11/(11+9) = 55.0% win rate >= CANDIDATE_SURVIVOR_WIN_RATE_THRESHOLD,
# decisive = 20.
SURVIVOR_WINDOW = (11, 9, 0)
# 10/(10+10) = 50.0% win rate -> WATCH, decisive = 20.
WATCH_WINDOW = (10, 10, 0)


class ClassifyGroupTests(unittest.TestCase):
    def test_below_minimum_sample_is_insufficient_regardless_of_win_rate(self) -> None:
        for win_rate in (0.0, 40.0, 55.0, 100.0):
            with self.subTest(win_rate=win_rate):
                self.assertEqual(
                    classify_group(
                        decisive_sample_size=MIN_SAMPLE_SIZE_FOR_VERDICT - 1,
                        win_rate=win_rate,
                    ),
                    GroupDisposition.INSUFFICIENT_EVIDENCE,
                )

    def test_sufficient_sample_middle_win_rate_is_watch(self) -> None:
        self.assertEqual(
            classify_group(
                decisive_sample_size=MIN_SAMPLE_SIZE_FOR_VERDICT,
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
                decisive_sample_size=MIN_SAMPLE_SIZE_FOR_VERDICT,
                win_rate=CANDIDATE_LOSER_WIN_RATE_THRESHOLD,
            ),
            GroupDisposition.CANDIDATE_LOSER,
        )

    def test_sufficient_but_below_stronger_and_survivor_win_rate_is_candidate_survivor(self) -> None:
        self.assertEqual(
            classify_group(
                decisive_sample_size=MIN_SAMPLE_SIZE_FOR_VERDICT,
                win_rate=CANDIDATE_SURVIVOR_WIN_RATE_THRESHOLD,
            ),
            GroupDisposition.CANDIDATE_SURVIVOR,
        )

    def test_large_sample_loser_win_rate_is_stronger_evidence_loser(self) -> None:
        self.assertEqual(
            classify_group(
                decisive_sample_size=MIN_SAMPLE_SIZE_FOR_STRONGER_EVIDENCE,
                win_rate=CANDIDATE_LOSER_WIN_RATE_THRESHOLD,
            ),
            GroupDisposition.STRONGER_EVIDENCE_LOSER,
        )

    def test_large_sample_survivor_win_rate_is_stronger_evidence_survivor(self) -> None:
        self.assertEqual(
            classify_group(
                decisive_sample_size=MIN_SAMPLE_SIZE_FOR_STRONGER_EVIDENCE,
                win_rate=CANDIDATE_SURVIVOR_WIN_RATE_THRESHOLD,
            ),
            GroupDisposition.STRONGER_EVIDENCE_SURVIVOR,
        )

    def test_large_sample_middle_win_rate_is_still_watch(self) -> None:
        self.assertEqual(
            classify_group(
                decisive_sample_size=MIN_SAMPLE_SIZE_FOR_STRONGER_EVIDENCE,
                win_rate=(
                    CANDIDATE_LOSER_WIN_RATE_THRESHOLD
                    + CANDIDATE_SURVIVOR_WIN_RATE_THRESHOLD
                )
                / 2,
            ),
            GroupDisposition.WATCH,
        )

    def test_stronger_evidence_direction_is_unambiguous(self) -> None:
        # STRONGER_EVIDENCE_LOSER and STRONGER_EVIDENCE_SURVIVOR are
        # distinct disposition values - direction cannot be lost or
        # confused downstream.
        self.assertNotEqual(
            GroupDisposition.STRONGER_EVIDENCE_LOSER,
            GroupDisposition.STRONGER_EVIDENCE_SURVIVOR,
        )
        self.assertTrue(is_loser_leaning(GroupDisposition.STRONGER_EVIDENCE_LOSER))
        self.assertFalse(is_survivor_leaning(GroupDisposition.STRONGER_EVIDENCE_LOSER))
        self.assertTrue(
            is_survivor_leaning(GroupDisposition.STRONGER_EVIDENCE_SURVIVOR)
        )
        self.assertFalse(
            is_loser_leaning(GroupDisposition.STRONGER_EVIDENCE_SURVIVOR)
        )

    def test_is_loser_survivor_leaning_false_for_insufficient_and_watch(self) -> None:
        for disposition in (
            GroupDisposition.INSUFFICIENT_EVIDENCE,
            GroupDisposition.WATCH,
        ):
            with self.subTest(disposition=disposition):
                self.assertFalse(is_loser_leaning(disposition))
                self.assertFalse(is_survivor_leaning(disposition))


class GroupRowDecisiveTests(unittest.TestCase):
    def test_decisive_excludes_breakeven(self) -> None:
        # clean_completed=25 padded with 7 breakevens over wins=10/losses=8.
        prior = make_setup_reasons()
        latest = make_setup_reasons(
            by_strategy=[
                make_group_row(
                    label="Breakout",
                    clean_completed=25,
                    wins=10,
                    losses=8,
                    win_rate=(10 / 18) * 100.0,
                )
            ]
        )

        result = daily_analysis(
            prior_setup_reasons=prior,
            latest_setup_reasons=latest,
            prior_run_id="run-1",
            latest_run_id="run-2",
        )

        change = result.dimension_reports[0].changes[0]
        self.assertEqual(change.latest.decisive, 18)
        self.assertEqual(change.latest.clean_completed, 25)


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
        self.assertAlmostEqual(change.delta_average_rr, 0.0)
        self.assertIsNotNone(change.prior)

    def test_delta_average_rr_computed_against_prior_run(self) -> None:
        prior = make_setup_reasons(
            by_strategy=[make_group_row(label="Breakout", average_rr=1.0)]
        )
        latest = make_setup_reasons(
            by_strategy=[make_group_row(label="Breakout", average_rr=1.8)]
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

        self.assertAlmostEqual(change.latest.average_rr, 1.8)
        self.assertAlmostEqual(change.delta_average_rr, 0.8)

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

    def test_disposition_computed_from_latest_row_decisive_sample(self) -> None:
        prior = make_setup_reasons(
            by_strategy=[
                make_group_row(label="Breakout", clean_completed=5, wins=1, losses=4, win_rate=20.0)
            ]
        )
        latest = make_setup_reasons(
            by_strategy=[
                make_group_row(
                    label="Breakout",
                    clean_completed=MIN_SAMPLE_SIZE_FOR_VERDICT,
                    wins=8,
                    losses=12,
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

    def test_breakeven_padded_clean_completed_does_not_grant_sufficient_evidence(
        self,
    ) -> None:
        # Regression for the denominator bug: clean_completed=25 (>=
        # MIN_SAMPLE_SIZE_FOR_VERDICT=20) but decisive=18 (<20) because
        # 7 of the 25 completed trades were breakeven. Must be
        # INSUFFICIENT_EVIDENCE, not a verdict derived from
        # clean_completed.
        prior = make_setup_reasons()
        latest = make_setup_reasons(
            by_strategy=[
                make_group_row(
                    label="Breakout",
                    clean_completed=25,
                    wins=10,
                    losses=8,
                    win_rate=(10 / 18) * 100.0,  # ~55.6% -> survivor-leaning if evaluated
                )
            ]
        )

        result = daily_analysis(
            prior_setup_reasons=prior,
            latest_setup_reasons=latest,
            prior_run_id="run-1",
            latest_run_id="run-2",
        )

        change = result.dimension_reports[0].changes[0]

        self.assertEqual(change.disposition, GroupDisposition.INSUFFICIENT_EVIDENCE)

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

    def test_backward_cumulative_counters_fail_closed(self) -> None:
        prior = make_setup_reasons(
            by_strategy=[
                make_group_row(label="Breakout", clean_completed=60, wins=30, losses=30)
            ]
        )
        latest = make_setup_reasons(
            by_strategy=[
                # Went backwards: 60 -> 20 clean_completed.
                make_group_row(label="Breakout", clean_completed=20, wins=10, losses=10)
            ]
        )

        with self.assertRaises(OutcomeIntelligenceDataError):
            daily_analysis(
                prior_setup_reasons=prior,
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
    def test_fewer_than_minimum_runs_yields_no_persistence_claim(self) -> None:
        # PERSISTENCE_MIN_CONSECUTIVE_RUNS - 1 windows -> one short of
        # the PERSISTENCE_MIN_CONSECUTIVE_RUNS windows required.
        deltas = [LOSER_WINDOW] * (PERSISTENCE_MIN_CONSECUTIVE_RUNS - 1)
        runs = build_cumulative_runs(deltas)

        result = weekly_analysis(runs)

        self.assertEqual(result.persistent_losers, ())
        self.assertEqual(result.persistent_survivors, ())

    def test_loser_leaning_every_window_is_persistent(self) -> None:
        deltas = [LOSER_WINDOW] * PERSISTENCE_MIN_CONSECUTIVE_RUNS
        runs = build_cumulative_runs(deltas)

        result = weekly_analysis(runs)

        self.assertEqual(len(result.persistent_losers), 1)
        self.assertEqual(result.persistent_losers[0].label, "Breakout")
        self.assertEqual(result.persistent_losers[0].dimension, "by_strategy")
        self.assertEqual(
            result.persistent_losers[0].consecutive_windows,
            PERSISTENCE_MIN_CONSECUTIVE_RUNS,
        )

    def test_survivor_leaning_every_window_is_persistent(self) -> None:
        deltas = [SURVIVOR_WINDOW] * PERSISTENCE_MIN_CONSECUTIVE_RUNS
        runs = build_cumulative_runs(deltas)

        result = weekly_analysis(runs)

        self.assertEqual(len(result.persistent_survivors), 1)
        self.assertEqual(result.persistent_survivors[0].label, "Breakout")

    def test_same_cumulative_win_rate_across_snapshots_is_not_fabricated_persistence(
        self,
    ) -> None:
        # Regression for the original defect: three snapshots of an
        # UNCHANGING cumulative total (zero new trades between
        # captures) must NOT be treated as persistence evidence merely
        # because the cumulative number repeats. Each window has zero
        # incremental evidence.
        deltas = [(0, 0, 0)] * PERSISTENCE_MIN_CONSECUTIVE_RUNS
        # Seed a loser-leaning cumulative history once, then stay flat.
        runs = build_cumulative_runs([LOSER_WINDOW] + deltas)

        result = weekly_analysis(runs)

        self.assertEqual(result.persistent_losers, ())

    def test_flip_from_loser_to_watch_breaks_persistence(self) -> None:
        deltas = [LOSER_WINDOW, WATCH_WINDOW, LOSER_WINDOW]
        runs = build_cumulative_runs(deltas)

        result = weekly_analysis(runs)

        self.assertEqual(result.persistent_losers, ())

    def test_breakeven_padded_window_is_insufficient_evidence(self) -> None:
        # Regression for the denominator bug at the incremental-window
        # level: each window adds 25 clean_completed (>=
        # MIN_SAMPLE_SIZE_FOR_VERDICT=20 by the old, wrong gate) but
        # only 18 decisive trades (10 wins, 8 losses -> ~55.6% win
        # rate, survivor-leaning by rate but insufficient by sample).
        # Must NOT be reported as a persistent survivor.
        deltas = [(10, 8, 7)] * PERSISTENCE_MIN_CONSECUTIVE_RUNS
        runs = build_cumulative_runs(deltas)

        result = weekly_analysis(runs)

        self.assertEqual(result.persistent_survivors, ())
        self.assertEqual(result.persistent_losers, ())

    def test_group_absent_from_one_run_is_excluded(self) -> None:
        runs = [
            (
                "run-0",
                make_setup_reasons(
                    by_strategy=[
                        make_group_row(
                            clean_completed=20, wins=8, losses=12, win_rate=40.0
                        )
                    ]
                ),
            ),
            ("run-1", make_setup_reasons(by_strategy=[])),
            (
                "run-2",
                make_setup_reasons(
                    by_strategy=[
                        make_group_row(
                            clean_completed=40, wins=16, losses=24, win_rate=40.0
                        )
                    ]
                ),
            ),
            (
                "run-3",
                make_setup_reasons(
                    by_strategy=[
                        make_group_row(
                            clean_completed=60, wins=24, losses=36, win_rate=40.0
                        )
                    ]
                ),
            ),
        ]

        result = weekly_analysis(runs)

        self.assertEqual(result.persistent_losers, ())

    def test_non_monotonic_counters_fail_closed(self) -> None:
        # A cumulative counter going backwards (data reset / anomaly)
        # must never be silently treated as valid incremental
        # evidence. At least PERSISTENCE_MIN_CONSECUTIVE_RUNS + 1 runs
        # are required for weekly_analysis to attempt window
        # computation at all; the anomaly sits inside that window.
        def row(clean_completed: int, wins: int) -> dict:
            losses = clean_completed - wins
            win_rate = (wins / clean_completed) * 100.0 if clean_completed else 0.0
            return make_group_row(
                clean_completed=clean_completed,
                wins=wins,
                losses=losses,
                win_rate=win_rate,
            )

        runs = [
            ("run-0", make_setup_reasons(by_strategy=[row(40, 16)])),
            ("run-1", make_setup_reasons(by_strategy=[row(60, 24)])),
            # Backwards: 60 -> 20 clean_completed between run-1 and run-2.
            ("run-2", make_setup_reasons(by_strategy=[row(20, 8)])),
            ("run-3", make_setup_reasons(by_strategy=[row(40, 16)])),
        ]

        with self.assertRaises(OutcomeIntelligenceDataError):
            weekly_analysis(runs)

    def test_group_filter_impact_reports_wins_and_losses_removed(self) -> None:
        # LOSER_WINDOW = (8, 12, 0) -> per window: 8 wins, 12 losses.
        deltas = [LOSER_WINDOW] * PERSISTENCE_MIN_CONSECUTIVE_RUNS
        runs = build_cumulative_runs(deltas)

        result = weekly_analysis(runs)
        impact = result.persistent_losers[0].filter_impact

        self.assertTrue(impact.would_remove_profitable_cases)
        self.assertEqual(impact.wins_removed, 8 * PERSISTENCE_MIN_CONSECUTIVE_RUNS)
        self.assertEqual(impact.losses_removed, 12 * PERSISTENCE_MIN_CONSECUTIVE_RUNS)

    def test_group_filter_impact_false_when_zero_incremental_wins(self) -> None:
        deltas = [(0, MIN_SAMPLE_SIZE_FOR_VERDICT, 0)] * PERSISTENCE_MIN_CONSECUTIVE_RUNS
        runs = build_cumulative_runs(deltas)

        result = weekly_analysis(runs)
        impact = result.persistent_losers[0].filter_impact

        self.assertEqual(len(result.persistent_losers), 1)
        self.assertFalse(impact.would_remove_profitable_cases)
        self.assertEqual(impact.wins_removed, 0)
        self.assertEqual(
            impact.losses_removed,
            MIN_SAMPLE_SIZE_FOR_VERDICT * PERSISTENCE_MIN_CONSECUTIVE_RUNS,
        )

    def test_persistent_group_surfaces_cumulative_average_rr_and_decisive(self) -> None:
        deltas = [LOSER_WINDOW] * PERSISTENCE_MIN_CONSECUTIVE_RUNS
        runs = build_cumulative_runs(deltas)

        result = weekly_analysis(runs)

        self.assertAlmostEqual(
            result.persistent_losers[0].latest_cumulative_average_rr, 1.5
        )
        self.assertEqual(
            result.persistent_losers[0].latest_cumulative_decisive,
            20 * PERSISTENCE_MIN_CONSECUTIVE_RUNS,
        )

    def test_weekly_analysis_never_disables_anything(self) -> None:
        result = weekly_analysis(
            [
                (f"run-{i}", make_setup_reasons())
                for i in range(PERSISTENCE_MIN_CONSECUTIVE_RUNS + 1)
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
                    wins=8,
                    losses=12,
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
        self.assertIn("decisive=20", summary)

    def test_weekly_summary_reports_no_persistence_when_insufficient_runs(self) -> None:
        result = weekly_analysis([("run-0", make_setup_reasons())])

        summary = render_weekly_summary(result)

        self.assertIn("No persistent losers or survivors", summary)

    def test_weekly_summary_flags_persistent_loser_with_warning(self) -> None:
        deltas = [LOSER_WINDOW] * PERSISTENCE_MIN_CONSECUTIVE_RUNS
        runs = build_cumulative_runs(deltas)

        result = weekly_analysis(runs)
        summary = render_weekly_summary(result)

        self.assertIn("Breakout", summary)
        self.assertIn("GROUP_FILTER_IMPACT", summary)
        self.assertIn("also remove", summary)
        self.assertIn("winning", summary)
        self.assertIn("losing", summary)
        self.assertIn("decisive=", summary)

    def test_daily_summary_states_unsupported_metrics_explicitly(self) -> None:
        result = daily_analysis(
            prior_setup_reasons=make_setup_reasons(),
            latest_setup_reasons=make_setup_reasons(),
            prior_run_id="run-1",
            latest_run_id="run-2",
        )

        summary = render_daily_summary(result)

        for metric in GROUP_LEVEL_UNSUPPORTED_METRICS:
            self.assertIn(metric, summary)
        self.assertIn("NOT", summary)

    def test_weekly_summary_states_unsupported_metrics_explicitly(self) -> None:
        result = weekly_analysis([("run-0", make_setup_reasons())])

        summary = render_weekly_summary(result)

        for metric in GROUP_LEVEL_UNSUPPORTED_METRICS:
            self.assertIn(metric, summary)
        self.assertIn("NOT", summary)

    def test_daily_summary_surfaces_average_rr(self) -> None:
        prior = make_setup_reasons()
        latest = make_setup_reasons(
            by_strategy=[
                make_group_row(
                    label="Breakout",
                    clean_completed=MIN_SAMPLE_SIZE_FOR_VERDICT,
                    wins=8,
                    losses=12,
                    win_rate=CANDIDATE_LOSER_WIN_RATE_THRESHOLD,
                    average_rr=1.5,
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

        self.assertIn("average_rr=1.50", summary)


if __name__ == "__main__":
    unittest.main()
