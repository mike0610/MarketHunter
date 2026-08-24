"""
MarketHunter

tools/outcome_intelligence/analysis.py

Module:
Outcome Intelligence analysis - bounded, sample-size-guarded daily and
weekly comparison of captured `GET /research/statistics` and
`GET /research/statistics/setup-reasons` run artifacts.

Responsibilities:
- Classify each group (by_strategy/by_setup_reason/by_close_reason/
  by_status/by_outcome/by_outcome_group) into an explicit disposition
  using named, conservative sample-size and win-rate thresholds -
  never a verdict from a tiny sample.
- Produce a daily change report (deltas since the prior run) and a
  weekly report (persistent losers/survivors across a run window,
  plus an explicit check for whether a proposed loser filter would
  also remove historically profitable cases).
- Render a concise, decision-oriented text summary - not a raw JSON
  dump.

Non-goals:
- No auto-disable, auto-promote, or any write to canonical
  MarketHunter/strategy state. This module only classifies and
  reports; every disposition is advisory output, never an action.
- No retrospective reconstruction of trend beyond the captured run
  history actually available - a persistent-loser/survivor verdict
  requires the minimum consecutive-run history defined below; fewer
  runs than that never produce a persistence claim.
- No deletion of any run/result - negative knowledge (losing
  patterns) stays in the immutable run history for future analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# Minimum clean_completed trades before ANY verdict beyond
# INSUFFICIENT_EVIDENCE may be issued for one group. Below this,
# win-rate swings are dominated by sample noise.
MIN_SAMPLE_SIZE_FOR_VERDICT = 20

# Minimum clean_completed trades before a verdict may be upgraded to
# STRONGER_EVIDENCE - a higher-confidence signal than
# CANDIDATE_LOSER/CANDIDATE_SURVIVOR.
MIN_SAMPLE_SIZE_FOR_STRONGER_EVIDENCE = 50

# Win-rate (%) at/below which a group with a sufficient sample is
# flagged as loser-leaning.
CANDIDATE_LOSER_WIN_RATE_THRESHOLD = 40.0

# Win-rate (%) at/above which a group with a sufficient sample is
# flagged as survivor-leaning.
CANDIDATE_SURVIVOR_WIN_RATE_THRESHOLD = 55.0

# Number of consecutive weekly runs a group must stay loser-leaning
# (or survivor-leaning) to be reported as "persistent" in the weekly
# report.
PERSISTENCE_MIN_CONSECUTIVE_RUNS = 3

_SETUP_REASON_DIMENSIONS: tuple[str, ...] = (
    "by_strategy",
    "by_setup_reason",
    "by_close_reason",
    "by_status",
    "by_outcome",
    "by_outcome_group",
)


class OutcomeIntelligenceAnalysisError(Exception):
    """Base error for Outcome Intelligence analysis failures."""


class OutcomeIntelligenceDataError(OutcomeIntelligenceAnalysisError):
    """A required field is absent from a captured payload - fail closed, never fabricate."""


class GroupDisposition(str, Enum):
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    WATCH = "WATCH"
    CANDIDATE_LOSER = "CANDIDATE_LOSER"
    CANDIDATE_SURVIVOR = "CANDIDATE_SURVIVOR"
    STRONGER_EVIDENCE = "STRONGER_EVIDENCE"


def _require_field(payload: dict[str, object], field_name: str) -> object:
    if field_name not in payload:
        raise OutcomeIntelligenceDataError(
            f"required field {field_name!r} missing from payload"
        )

    return payload[field_name]


def classify_group(
    clean_completed: int,
    win_rate: float,
) -> GroupDisposition:
    """
    Classify one group's disposition from its exact sample size and
    win rate only. Sample-size guardrail always takes precedence:
    below MIN_SAMPLE_SIZE_FOR_VERDICT, the result is
    INSUFFICIENT_EVIDENCE regardless of win_rate.
    """

    if clean_completed < MIN_SAMPLE_SIZE_FOR_VERDICT:
        return GroupDisposition.INSUFFICIENT_EVIDENCE

    is_loser_leaning = win_rate <= CANDIDATE_LOSER_WIN_RATE_THRESHOLD
    is_survivor_leaning = win_rate >= CANDIDATE_SURVIVOR_WIN_RATE_THRESHOLD

    if not is_loser_leaning and not is_survivor_leaning:
        return GroupDisposition.WATCH

    if clean_completed >= MIN_SAMPLE_SIZE_FOR_STRONGER_EVIDENCE:
        return GroupDisposition.STRONGER_EVIDENCE

    return (
        GroupDisposition.CANDIDATE_LOSER
        if is_loser_leaning
        else GroupDisposition.CANDIDATE_SURVIVOR
    )


def is_loser_leaning(disposition: GroupDisposition, win_rate: float) -> bool:
    if disposition == GroupDisposition.CANDIDATE_LOSER:
        return True

    if disposition == GroupDisposition.STRONGER_EVIDENCE:
        return win_rate <= CANDIDATE_LOSER_WIN_RATE_THRESHOLD

    return False


def is_survivor_leaning(disposition: GroupDisposition, win_rate: float) -> bool:
    if disposition == GroupDisposition.CANDIDATE_SURVIVOR:
        return True

    if disposition == GroupDisposition.STRONGER_EVIDENCE:
        return win_rate >= CANDIDATE_SURVIVOR_WIN_RATE_THRESHOLD

    return False


@dataclass(frozen=True, slots=True)
class GroupRow:
    """
    One exact group row as read from a `by_*` breakdown in one
    captured `setup-reasons` payload.
    """

    label: str
    total: int
    clean_completed: int
    wins: int
    losses: int
    win_rate: float
    total_profit: float


def _group_row_from_payload(payload: dict[str, object]) -> GroupRow:
    return GroupRow(
        label=str(_require_field(payload, "label")),
        total=int(_require_field(payload, "total")),
        clean_completed=int(_require_field(payload, "clean_completed")),
        wins=int(_require_field(payload, "wins")),
        losses=int(_require_field(payload, "losses")),
        win_rate=float(_require_field(payload, "win_rate")),
        total_profit=float(_require_field(payload, "total_profit")),
    )


def _dimension_rows(
    setup_reasons_payload: dict[str, object],
    dimension: str,
) -> dict[str, GroupRow]:
    rows = _require_field(setup_reasons_payload, dimension)

    if not isinstance(rows, list):
        raise OutcomeIntelligenceDataError(
            f"dimension {dimension!r} is not a list"
        )

    return {
        row.label: row
        for row in (_group_row_from_payload(item) for item in rows)
    }


@dataclass(frozen=True, slots=True)
class GroupChange:
    """
    One group's comparison between a prior run and the latest run.
    prior is None when the group is new in the latest run.
    """

    label: str
    prior: GroupRow | None
    latest: GroupRow
    delta_clean_completed: int
    delta_wins: int
    delta_losses: int
    delta_win_rate: float
    delta_total_profit: float
    disposition: GroupDisposition


@dataclass(frozen=True, slots=True)
class DailyDimensionReport:
    dimension: str
    changes: tuple[GroupChange, ...]


@dataclass(frozen=True, slots=True)
class DailyAnalysisResult:
    prior_run_id: str
    latest_run_id: str
    dimension_reports: tuple[DailyDimensionReport, ...]


def daily_analysis(
    prior_setup_reasons: dict[str, object],
    latest_setup_reasons: dict[str, object],
    prior_run_id: str,
    latest_run_id: str,
) -> DailyAnalysisResult:
    """
    Compare the latest run's group breakdowns against the prior run.
    Every group in the latest run receives a disposition classified
    from its own exact sample size and win rate only - this never
    disables or promotes anything, it only reports.
    """

    dimension_reports: list[DailyDimensionReport] = []

    for dimension in _SETUP_REASON_DIMENSIONS:
        prior_rows = _dimension_rows(prior_setup_reasons, dimension)
        latest_rows = _dimension_rows(latest_setup_reasons, dimension)

        changes = tuple(
            GroupChange(
                label=label,
                prior=prior_rows.get(label),
                latest=latest_row,
                delta_clean_completed=(
                    latest_row.clean_completed
                    - (
                        prior_rows[label].clean_completed
                        if label in prior_rows
                        else 0
                    )
                ),
                delta_wins=(
                    latest_row.wins
                    - (prior_rows[label].wins if label in prior_rows else 0)
                ),
                delta_losses=(
                    latest_row.losses
                    - (
                        prior_rows[label].losses
                        if label in prior_rows
                        else 0
                    )
                ),
                delta_win_rate=(
                    latest_row.win_rate
                    - (
                        prior_rows[label].win_rate
                        if label in prior_rows
                        else 0.0
                    )
                ),
                delta_total_profit=(
                    latest_row.total_profit
                    - (
                        prior_rows[label].total_profit
                        if label in prior_rows
                        else 0.0
                    )
                ),
                disposition=classify_group(
                    clean_completed=latest_row.clean_completed,
                    win_rate=latest_row.win_rate,
                ),
            )
            for label, latest_row in latest_rows.items()
        )

        dimension_reports.append(
            DailyDimensionReport(
                dimension=dimension,
                changes=changes,
            )
        )

    return DailyAnalysisResult(
        prior_run_id=prior_run_id,
        latest_run_id=latest_run_id,
        dimension_reports=tuple(dimension_reports),
    )


@dataclass(frozen=True, slots=True)
class PersistentGroup:
    dimension: str
    label: str
    consecutive_runs: int
    latest_win_rate: float
    latest_clean_completed: int
    latest_wins: int
    filter_would_remove_profitable_cases: bool


@dataclass(frozen=True, slots=True)
class WeeklyAnalysisResult:
    run_ids: tuple[str, ...]
    persistent_losers: tuple[PersistentGroup, ...]
    persistent_survivors: tuple[PersistentGroup, ...]


def weekly_analysis(
    setup_reasons_by_run: list[tuple[str, dict[str, object]]],
) -> WeeklyAnalysisResult:
    """
    Identify labels whose disposition has been loser-leaning (or
    survivor-leaning) for the last PERSISTENCE_MIN_CONSECUTIVE_RUNS
    runs in `setup_reasons_by_run`, which must already be ordered
    oldest-to-newest.

    Fewer than PERSISTENCE_MIN_CONSECUTIVE_RUNS runs are supplied ->
    no persistence claim is possible, and both result tuples are
    empty. This is the guardrail against inferring a trend from too
    short a history.
    """

    run_ids = tuple(run_id for run_id, _ in setup_reasons_by_run)

    if len(setup_reasons_by_run) < PERSISTENCE_MIN_CONSECUTIVE_RUNS:
        return WeeklyAnalysisResult(
            run_ids=run_ids,
            persistent_losers=(),
            persistent_survivors=(),
        )

    recent_window = setup_reasons_by_run[-PERSISTENCE_MIN_CONSECUTIVE_RUNS:]

    persistent_losers: list[PersistentGroup] = []
    persistent_survivors: list[PersistentGroup] = []

    for dimension in _SETUP_REASON_DIMENSIONS:
        per_run_rows = [
            _dimension_rows(payload, dimension)
            for _, payload in recent_window
        ]

        latest_rows = per_run_rows[-1]

        for label, latest_row in latest_rows.items():
            rows_for_label = [
                rows.get(label) for rows in per_run_rows
            ]

            if any(row is None for row in rows_for_label):
                continue

            dispositions = [
                classify_group(
                    clean_completed=row.clean_completed,
                    win_rate=row.win_rate,
                )
                for row in rows_for_label
                if row is not None
            ]

            all_loser_leaning = all(
                is_loser_leaning(disposition, row.win_rate)
                for disposition, row in zip(dispositions, rows_for_label)
                if row is not None
            )

            all_survivor_leaning = all(
                is_survivor_leaning(disposition, row.win_rate)
                for disposition, row in zip(dispositions, rows_for_label)
                if row is not None
            )

            filter_would_remove_profitable_cases = latest_row.wins > 0

            if all_loser_leaning:
                persistent_losers.append(
                    PersistentGroup(
                        dimension=dimension,
                        label=label,
                        consecutive_runs=PERSISTENCE_MIN_CONSECUTIVE_RUNS,
                        latest_win_rate=latest_row.win_rate,
                        latest_clean_completed=latest_row.clean_completed,
                        latest_wins=latest_row.wins,
                        filter_would_remove_profitable_cases=(
                            filter_would_remove_profitable_cases
                        ),
                    )
                )

            if all_survivor_leaning:
                persistent_survivors.append(
                    PersistentGroup(
                        dimension=dimension,
                        label=label,
                        consecutive_runs=PERSISTENCE_MIN_CONSECUTIVE_RUNS,
                        latest_win_rate=latest_row.win_rate,
                        latest_clean_completed=latest_row.clean_completed,
                        latest_wins=latest_row.wins,
                        filter_would_remove_profitable_cases=(
                            filter_would_remove_profitable_cases
                        ),
                    )
                )

    return WeeklyAnalysisResult(
        run_ids=run_ids,
        persistent_losers=tuple(persistent_losers),
        persistent_survivors=tuple(persistent_survivors),
    )


def render_daily_summary(result: DailyAnalysisResult) -> str:
    """
    Concise, decision-oriented text summary of one daily analysis -
    not a raw JSON dump.
    """

    lines = [
        f"Outcome Intelligence — daily change "
        f"({result.prior_run_id} -> {result.latest_run_id})",
    ]

    any_flagged = False

    for report in result.dimension_reports:
        flagged = [
            change
            for change in report.changes
            if change.disposition
            in (
                GroupDisposition.CANDIDATE_LOSER,
                GroupDisposition.CANDIDATE_SURVIVOR,
                GroupDisposition.STRONGER_EVIDENCE,
            )
        ]

        if not flagged:
            continue

        any_flagged = True
        lines.append(f"\n[{report.dimension}]")

        for change in flagged:
            lines.append(
                f"  - {change.label}: {change.disposition.value} "
                f"(win_rate={change.latest.win_rate:.1f}%, "
                f"clean_completed={change.latest.clean_completed}, "
                f"delta_clean_completed={change.delta_clean_completed:+d}, "
                f"delta_total_profit={change.delta_total_profit:+.2f})"
            )

    if not any_flagged:
        lines.append(
            "\nNo group crossed a CANDIDATE_LOSER/CANDIDATE_SURVIVOR/"
            "STRONGER_EVIDENCE threshold today."
        )

    return "\n".join(lines)


def render_weekly_summary(result: WeeklyAnalysisResult) -> str:
    """
    Concise, decision-oriented text summary of one weekly analysis -
    not a raw JSON dump.
    """

    lines = [
        f"Outcome Intelligence — weekly review "
        f"({len(result.run_ids)} runs: "
        f"{', '.join(result.run_ids) if result.run_ids else 'none'})",
    ]

    if not result.persistent_losers and not result.persistent_survivors:
        lines.append(
            "\nNo persistent losers or survivors across the last "
            f"{PERSISTENCE_MIN_CONSECUTIVE_RUNS} runs "
            "(or insufficient run history)."
        )

        return "\n".join(lines)

    if result.persistent_losers:
        lines.append("\n[Persistent losers]")

        for group in result.persistent_losers:
            warning = (
                " ⚠ filter would also remove "
                f"{group.latest_wins} profitable case(s)"
                if group.filter_would_remove_profitable_cases
                else ""
            )
            lines.append(
                f"  - [{group.dimension}] {group.label}: "
                f"win_rate={group.latest_win_rate:.1f}% over "
                f"{group.latest_clean_completed} trades, "
                f"loser-leaning for {group.consecutive_runs} "
                f"consecutive runs.{warning}"
            )

    if result.persistent_survivors:
        lines.append("\n[Persistent survivors]")

        for group in result.persistent_survivors:
            lines.append(
                f"  - [{group.dimension}] {group.label}: "
                f"win_rate={group.latest_win_rate:.1f}% over "
                f"{group.latest_clean_completed} trades, "
                f"survivor-leaning for {group.consecutive_runs} "
                f"consecutive runs."
            )

    return "\n".join(lines)
