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
- Produce a daily change report (deltas since the prior run, computed
  from each group's own latest cumulative sample) and a weekly report
  of persistent losers/survivors.
- The `setup-reasons` endpoint returns cumulative (all-time) counters
  per group. Three snapshots that all show the same cumulative
  win_rate are NOT three independent confirmations - they are the
  same growing history read three times. Weekly persistence is
  therefore evaluated on the *incremental* evidence between
  consecutive snapshots (new clean_completed/wins/losses since the
  prior capture), so each confirming window is a disjoint sample.
  A window with zero incremental clean_completed carries no evidence
  and cannot confirm persistence in either direction.
- Render a concise, decision-oriented text summary - not a raw JSON
  dump.

Non-goals:
- No auto-disable, auto-promote, or any write to canonical
  MarketHunter/strategy state. This module only classifies and
  reports; every disposition is advisory output, never an action.
- No retrospective reconstruction of trend beyond the captured run
  history actually available - a persistent-loser/survivor verdict
  requires PERSISTENCE_MIN_CONSECUTIVE_RUNS consecutive *incremental*
  confirming windows (PERSISTENCE_MIN_CONSECUTIVE_RUNS + 1 captured
  runs). Fewer runs than that never produce a persistence claim.
- No deletion of any run/result - negative knowledge (losing
  patterns) stays in the immutable run history for future analysis.
- No scheduling: this module and its CLI are manual/externally
  scheduled only. Nothing here runs autonomously on a cadence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# Minimum clean_completed trades before ANY verdict beyond
# INSUFFICIENT_EVIDENCE may be issued for one group (or one
# incremental window). Below this, win-rate swings are dominated by
# sample noise.
MIN_SAMPLE_SIZE_FOR_VERDICT = 20

# Minimum clean_completed trades before a verdict may be upgraded to
# a STRONGER_EVIDENCE_* disposition - a higher-confidence signal than
# CANDIDATE_LOSER/CANDIDATE_SURVIVOR.
MIN_SAMPLE_SIZE_FOR_STRONGER_EVIDENCE = 50

# Win-rate (%) at/below which a group with a sufficient sample is
# flagged as loser-leaning.
CANDIDATE_LOSER_WIN_RATE_THRESHOLD = 40.0

# Win-rate (%) at/above which a group with a sufficient sample is
# flagged as survivor-leaning.
CANDIDATE_SURVIVOR_WIN_RATE_THRESHOLD = 55.0

# Number of consecutive incremental windows (each the delta between
# two adjacent captured runs) a group must stay loser-leaning (or
# survivor-leaning) to be reported as "persistent" in the weekly
# report. Requires PERSISTENCE_MIN_CONSECUTIVE_RUNS + 1 captured runs.
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
    """A required field is absent, or a cumulative counter went
    backwards between two runs (data reset / non-monotonic source) -
    fail closed, never fabricate."""


class GroupDisposition(str, Enum):
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    WATCH = "WATCH"
    CANDIDATE_LOSER = "CANDIDATE_LOSER"
    CANDIDATE_SURVIVOR = "CANDIDATE_SURVIVOR"
    STRONGER_EVIDENCE_LOSER = "STRONGER_EVIDENCE_LOSER"
    STRONGER_EVIDENCE_SURVIVOR = "STRONGER_EVIDENCE_SURVIVOR"


_LOSER_DISPOSITIONS = frozenset(
    {GroupDisposition.CANDIDATE_LOSER, GroupDisposition.STRONGER_EVIDENCE_LOSER}
)
_SURVIVOR_DISPOSITIONS = frozenset(
    {
        GroupDisposition.CANDIDATE_SURVIVOR,
        GroupDisposition.STRONGER_EVIDENCE_SURVIVOR,
    }
)


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
    Classify one group's (or one incremental window's) disposition
    from its exact sample size and win rate only. Sample-size
    guardrail always takes precedence: below
    MIN_SAMPLE_SIZE_FOR_VERDICT, the result is INSUFFICIENT_EVIDENCE
    regardless of win_rate.
    """

    if clean_completed < MIN_SAMPLE_SIZE_FOR_VERDICT:
        return GroupDisposition.INSUFFICIENT_EVIDENCE

    loser_leaning = win_rate <= CANDIDATE_LOSER_WIN_RATE_THRESHOLD
    survivor_leaning = win_rate >= CANDIDATE_SURVIVOR_WIN_RATE_THRESHOLD

    if not loser_leaning and not survivor_leaning:
        return GroupDisposition.WATCH

    stronger = clean_completed >= MIN_SAMPLE_SIZE_FOR_STRONGER_EVIDENCE

    if loser_leaning:
        return (
            GroupDisposition.STRONGER_EVIDENCE_LOSER
            if stronger
            else GroupDisposition.CANDIDATE_LOSER
        )

    return (
        GroupDisposition.STRONGER_EVIDENCE_SURVIVOR
        if stronger
        else GroupDisposition.CANDIDATE_SURVIVOR
    )


def is_loser_leaning(disposition: GroupDisposition) -> bool:
    return disposition in _LOSER_DISPOSITIONS


def is_survivor_leaning(disposition: GroupDisposition) -> bool:
    return disposition in _SURVIVOR_DISPOSITIONS


@dataclass(frozen=True, slots=True)
class GroupRow:
    """
    One exact group row as read from a `by_*` breakdown in one
    captured `setup-reasons` payload. All counters are cumulative
    (all-time) as returned by the endpoint.
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
    prior is None when the group is new in the latest run. Disposition
    is classified from the latest run's own cumulative sample - this
    is a same-run snapshot classification, not a persistence claim.
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
    from its own exact cumulative sample size and win rate - this
    never disables or promotes anything, it only reports.
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
class IncrementalWindow:
    """
    The incremental (new-since-prior-snapshot) evidence for one group
    between two adjacent captured runs. This is a disjoint sample -
    the actual new clean_completed/wins/losses recorded strictly
    between prior_run_id and latest_run_id - not a re-read of the
    same cumulative total.
    """

    prior_run_id: str
    latest_run_id: str
    delta_clean_completed: int
    delta_wins: int
    delta_losses: int
    incremental_win_rate: float | None
    disposition: GroupDisposition


def _incremental_window(
    prior_run_id: str,
    latest_run_id: str,
    prior_row: GroupRow,
    latest_row: GroupRow,
) -> IncrementalWindow:
    delta_clean_completed = latest_row.clean_completed - prior_row.clean_completed
    delta_wins = latest_row.wins - prior_row.wins
    delta_losses = latest_row.losses - prior_row.losses

    if delta_clean_completed < 0 or delta_wins < 0 or delta_losses < 0:
        raise OutcomeIntelligenceDataError(
            f"non-monotonic cumulative counters for {latest_row.label!r} "
            f"between runs {prior_run_id!r} -> {latest_run_id!r} "
            f"(delta_clean_completed={delta_clean_completed}, "
            f"delta_wins={delta_wins}, delta_losses={delta_losses})"
        )

    incremental_win_rate = (
        (delta_wins / delta_clean_completed) * 100.0
        if delta_clean_completed > 0
        else None
    )

    disposition = classify_group(
        clean_completed=delta_clean_completed,
        win_rate=incremental_win_rate if incremental_win_rate is not None else 0.0,
    )

    return IncrementalWindow(
        prior_run_id=prior_run_id,
        latest_run_id=latest_run_id,
        delta_clean_completed=delta_clean_completed,
        delta_wins=delta_wins,
        delta_losses=delta_losses,
        incremental_win_rate=incremental_win_rate,
        disposition=disposition,
    )


@dataclass(frozen=True, slots=True)
class PersistentGroup:
    dimension: str
    label: str
    consecutive_windows: int
    window_run_ids: tuple[str, ...]
    latest_cumulative_win_rate: float
    latest_cumulative_clean_completed: int
    wins_during_persistence_window: int
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
    Identify labels whose *incremental* evidence has been
    loser-leaning (or survivor-leaning) for PERSISTENCE_MIN_CONSECUTIVE_RUNS
    consecutive windows between adjacent runs in `setup_reasons_by_run`,
    which must already be ordered oldest-to-newest.

    Each window's evidence is the delta between two adjacent captured
    runs - a disjoint sample of new clean_completed/wins/losses - not
    a re-read of the same cumulative total, so three confirming
    windows are three independent confirmations, not one number seen
    three times. A window with zero incremental clean_completed
    carries no evidence and breaks the persistence claim (it cannot
    confirm in either direction).

    Fewer than PERSISTENCE_MIN_CONSECUTIVE_RUNS + 1 runs are supplied
    -> no persistence claim is possible (not enough runs to form
    PERSISTENCE_MIN_CONSECUTIVE_RUNS windows), and both result tuples
    are empty. This is the guardrail against inferring a trend from
    too short a history.
    """

    run_ids = tuple(run_id for run_id, _ in setup_reasons_by_run)
    required_runs = PERSISTENCE_MIN_CONSECUTIVE_RUNS + 1

    if len(setup_reasons_by_run) < required_runs:
        return WeeklyAnalysisResult(
            run_ids=run_ids,
            persistent_losers=(),
            persistent_survivors=(),
        )

    recent_window = setup_reasons_by_run[-required_runs:]
    window_run_ids = tuple(run_id for run_id, _ in recent_window)

    persistent_losers: list[PersistentGroup] = []
    persistent_survivors: list[PersistentGroup] = []

    for dimension in _SETUP_REASON_DIMENSIONS:
        per_run_rows = [
            _dimension_rows(payload, dimension)
            for _, payload in recent_window
        ]

        latest_rows = per_run_rows[-1]

        for label, latest_row in latest_rows.items():
            rows_for_label = [rows.get(label) for rows in per_run_rows]

            if any(row is None for row in rows_for_label):
                continue

            windows = [
                _incremental_window(
                    prior_run_id=window_run_ids[index],
                    latest_run_id=window_run_ids[index + 1],
                    prior_row=rows_for_label[index],
                    latest_row=rows_for_label[index + 1],
                )
                for index in range(len(rows_for_label) - 1)
            ]

            all_loser = all(
                is_loser_leaning(window.disposition) for window in windows
            )
            all_survivor = all(
                is_survivor_leaning(window.disposition) for window in windows
            )

            wins_during_persistence_window = sum(
                window.delta_wins for window in windows
            )
            filter_would_remove_profitable_cases = (
                wins_during_persistence_window > 0
            )

            if all_loser:
                persistent_losers.append(
                    PersistentGroup(
                        dimension=dimension,
                        label=label,
                        consecutive_windows=len(windows),
                        window_run_ids=window_run_ids,
                        latest_cumulative_win_rate=latest_row.win_rate,
                        latest_cumulative_clean_completed=(
                            latest_row.clean_completed
                        ),
                        wins_during_persistence_window=(
                            wins_during_persistence_window
                        ),
                        filter_would_remove_profitable_cases=(
                            filter_would_remove_profitable_cases
                        ),
                    )
                )

            if all_survivor:
                persistent_survivors.append(
                    PersistentGroup(
                        dimension=dimension,
                        label=label,
                        consecutive_windows=len(windows),
                        window_run_ids=window_run_ids,
                        latest_cumulative_win_rate=latest_row.win_rate,
                        latest_cumulative_clean_completed=(
                            latest_row.clean_completed
                        ),
                        wins_during_persistence_window=(
                            wins_during_persistence_window
                        ),
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


_FLAGGED_DAILY_DISPOSITIONS = (
    GroupDisposition.CANDIDATE_LOSER,
    GroupDisposition.CANDIDATE_SURVIVOR,
    GroupDisposition.STRONGER_EVIDENCE_LOSER,
    GroupDisposition.STRONGER_EVIDENCE_SURVIVOR,
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
            if change.disposition in _FLAGGED_DAILY_DISPOSITIONS
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
            "STRONGER_EVIDENCE_LOSER/STRONGER_EVIDENCE_SURVIVOR "
            "threshold today."
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
            f"{PERSISTENCE_MIN_CONSECUTIVE_RUNS} incremental windows "
            "(or insufficient run history)."
        )

        return "\n".join(lines)

    if result.persistent_losers:
        lines.append("\n[Persistent losers]")

        for group in result.persistent_losers:
            warning = (
                " ⚠ filter would also remove "
                f"{group.wins_during_persistence_window} profitable "
                "case(s) recorded during this persistence window"
                if group.filter_would_remove_profitable_cases
                else ""
            )
            lines.append(
                f"  - [{group.dimension}] {group.label}: loser-leaning "
                f"for {group.consecutive_windows} consecutive incremental "
                f"windows (runs {', '.join(group.window_run_ids)}; "
                f"cumulative-to-date win_rate="
                f"{group.latest_cumulative_win_rate:.1f}% over "
                f"{group.latest_cumulative_clean_completed} trades)."
                f"{warning}"
            )

    if result.persistent_survivors:
        lines.append("\n[Persistent survivors]")

        for group in result.persistent_survivors:
            lines.append(
                f"  - [{group.dimension}] {group.label}: survivor-leaning "
                f"for {group.consecutive_windows} consecutive incremental "
                f"windows (runs {', '.join(group.window_run_ids)}; "
                f"cumulative-to-date win_rate="
                f"{group.latest_cumulative_win_rate:.1f}% over "
                f"{group.latest_cumulative_clean_completed} trades)."
            )

    return "\n".join(lines)
