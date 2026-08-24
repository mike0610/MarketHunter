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
  win_rate do NOT constitute three confirmations at all - they are
  the same growing history read three times. Weekly persistence is
  therefore evaluated on the *incremental* evidence between
  consecutive snapshots (new clean_completed/wins/losses since the
  prior capture), so each confirming window is a distinct,
  non-overlapping sample of new trades - not a claim that the windows
  are statistically independent in any formal sense, just that they
  do not share the same underlying trades.
  A window with zero incremental clean_completed carries no evidence
  and cannot confirm persistence in either direction.
- Metric coverage is explicit, not silently partial: the grouped
  endpoint provides win_rate, average_rr, and total_profit per group,
  and all three are surfaced. profit_factor/expectancy are NOT
  present at the group level (only in the top-level `/statistics`
  summary) and are never fabricated here - every daily/weekly summary
  says so explicitly rather than silently omitting them.
- Sample size and win rate are computed on DECISIVE trades
  (wins + losses) - the same denominator the canonical
  `research/statistics.py::_trade_group_payload()` uses for its own
  `win_rate` field (`wins / (wins + losses)`, breakeven excluded).
  `clean_completed` (completed minus excluded, including breakevens)
  is reported for context but is NEVER used as the win-rate
  denominator or the sample-size evidence gate - a group with many
  breakevens and few decisive trades must not look more evidenced
  than it is.
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

# Minimum DECISIVE trades (wins + losses - breakeven excluded, same
# denominator as the canonical win_rate) before ANY verdict beyond
# INSUFFICIENT_EVIDENCE may be issued for one group (or one
# incremental window). Below this, win-rate swings are dominated by
# sample noise. clean_completed is NEVER used here - a group padded
# with breakevens must not look more evidenced than its decisive
# trade count actually supports.
MIN_SAMPLE_SIZE_FOR_VERDICT = 20

# Minimum decisive trades before a verdict may be upgraded to a
# STRONGER_EVIDENCE_* disposition - a higher-confidence signal than
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

# Metrics the grouped `setup-reasons` endpoint does NOT provide per
# group (only the top-level `/statistics` summary has them). Named
# explicitly so every render function can say so rather than silently
# omitting them.
GROUP_LEVEL_UNSUPPORTED_METRICS: tuple[str, ...] = ("profit_factor", "expectancy")

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
    decisive_sample_size: int,
    win_rate: float,
) -> GroupDisposition:
    """
    Classify one group's (or one incremental window's) disposition
    from its exact decisive-trade sample size (wins + losses -
    breakeven excluded, matching the canonical win_rate denominator)
    and win rate only. Sample-size guardrail always takes precedence:
    below MIN_SAMPLE_SIZE_FOR_VERDICT decisive trades, the result is
    INSUFFICIENT_EVIDENCE regardless of win_rate. Callers must pass
    wins + losses here, never clean_completed.
    """

    if decisive_sample_size < MIN_SAMPLE_SIZE_FOR_VERDICT:
        return GroupDisposition.INSUFFICIENT_EVIDENCE

    loser_leaning = win_rate <= CANDIDATE_LOSER_WIN_RATE_THRESHOLD
    survivor_leaning = win_rate >= CANDIDATE_SURVIVOR_WIN_RATE_THRESHOLD

    if not loser_leaning and not survivor_leaning:
        return GroupDisposition.WATCH

    stronger = decisive_sample_size >= MIN_SAMPLE_SIZE_FOR_STRONGER_EVIDENCE

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
    (all-time) as returned by the endpoint. average_rr is surfaced
    because the endpoint provides it per group; profit_factor and
    expectancy are NOT provided per group (see
    GROUP_LEVEL_UNSUPPORTED_METRICS) and have no field here.

    clean_completed = completed minus excluded (includes breakeven
    trades) - a reported context metric only. It is NEVER the
    win-rate denominator or the sample-size evidence gate; `decisive`
    (wins + losses) is, matching the canonical
    `research/statistics.py` win_rate formula.
    """

    label: str
    total: int
    clean_completed: int
    wins: int
    losses: int
    win_rate: float
    total_profit: float
    average_rr: float

    @property
    def decisive(self) -> int:
        return self.wins + self.losses


def _group_row_from_payload(payload: dict[str, object]) -> GroupRow:
    return GroupRow(
        label=str(_require_field(payload, "label")),
        total=int(_require_field(payload, "total")),
        clean_completed=int(_require_field(payload, "clean_completed")),
        wins=int(_require_field(payload, "wins")),
        losses=int(_require_field(payload, "losses")),
        win_rate=float(_require_field(payload, "win_rate")),
        total_profit=float(_require_field(payload, "total_profit")),
        average_rr=float(_require_field(payload, "average_rr")),
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
    delta_average_rr: float
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


def _daily_group_change(
    label: str,
    prior_row: GroupRow | None,
    latest_row: GroupRow,
) -> GroupChange:
    if prior_row is None:
        delta_clean_completed = latest_row.clean_completed
        delta_wins = latest_row.wins
        delta_losses = latest_row.losses
        delta_win_rate = latest_row.win_rate
        delta_total_profit = latest_row.total_profit
        delta_average_rr = latest_row.average_rr
    else:
        delta_clean_completed = (
            latest_row.clean_completed - prior_row.clean_completed
        )
        delta_wins = latest_row.wins - prior_row.wins
        delta_losses = latest_row.losses - prior_row.losses
        delta_win_rate = latest_row.win_rate - prior_row.win_rate
        delta_total_profit = latest_row.total_profit - prior_row.total_profit
        delta_average_rr = latest_row.average_rr - prior_row.average_rr

        if delta_clean_completed < 0 or delta_wins < 0 or delta_losses < 0:
            raise OutcomeIntelligenceDataError(
                f"non-monotonic cumulative counters for {label!r} between "
                f"prior run and latest run (delta_clean_completed="
                f"{delta_clean_completed}, delta_wins={delta_wins}, "
                f"delta_losses={delta_losses})"
            )

    disposition = classify_group(
        decisive_sample_size=latest_row.decisive,
        win_rate=latest_row.win_rate,
    )

    return GroupChange(
        label=label,
        prior=prior_row,
        latest=latest_row,
        delta_clean_completed=delta_clean_completed,
        delta_wins=delta_wins,
        delta_losses=delta_losses,
        delta_win_rate=delta_win_rate,
        delta_total_profit=delta_total_profit,
        delta_average_rr=delta_average_rr,
        disposition=disposition,
    )


def daily_analysis(
    prior_setup_reasons: dict[str, object],
    latest_setup_reasons: dict[str, object],
    prior_run_id: str,
    latest_run_id: str,
) -> DailyAnalysisResult:
    """
    Compare the latest run's group breakdowns against the prior run.
    Every group in the latest run receives a disposition classified
    from its own exact decisive-trade sample size (wins + losses) and
    win rate - this never disables or promotes anything, it only
    reports. Fails closed (OutcomeIntelligenceDataError) if any of a
    group's cumulative clean_completed/wins/losses went backwards
    since the prior run, rather than emitting a misleading negative
    delta.
    """

    dimension_reports: list[DailyDimensionReport] = []

    for dimension in _SETUP_REASON_DIMENSIONS:
        prior_rows = _dimension_rows(prior_setup_reasons, dimension)
        latest_rows = _dimension_rows(latest_setup_reasons, dimension)

        changes = tuple(
            _daily_group_change(
                label=label,
                prior_row=prior_rows.get(label),
                latest_row=latest_row,
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

    decisive_sample_size (delta_wins + delta_losses) is the win-rate
    denominator and the sample-size evidence gate - delta_clean_completed
    is reported for context only and is NEVER used as either.
    """

    prior_run_id: str
    latest_run_id: str
    delta_clean_completed: int
    delta_wins: int
    delta_losses: int
    decisive_sample_size: int
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

    decisive_sample_size = delta_wins + delta_losses

    incremental_win_rate = (
        (delta_wins / decisive_sample_size) * 100.0
        if decisive_sample_size > 0
        else None
    )

    disposition = classify_group(
        decisive_sample_size=decisive_sample_size,
        win_rate=incremental_win_rate if incremental_win_rate is not None else 0.0,
    )

    return IncrementalWindow(
        prior_run_id=prior_run_id,
        latest_run_id=latest_run_id,
        delta_clean_completed=delta_clean_completed,
        delta_wins=delta_wins,
        delta_losses=delta_losses,
        decisive_sample_size=decisive_sample_size,
        incremental_win_rate=incremental_win_rate,
        disposition=disposition,
    )


@dataclass(frozen=True, slots=True)
class GroupFilterImpact:
    """
    GROUP_FILTER_IMPACT: the exact winning and losing trades that
    were recorded within the incremental persistence window for one
    group - i.e. what a blanket exclusion of this group would have
    also discarded during that window. This is a bounded count of
    documented cases, NOT a before/after counterfactual performance
    simulation - it does not claim to know what would have happened
    to overall portfolio results had the group been filtered out.
    """

    wins_removed: int
    losses_removed: int
    would_remove_profitable_cases: bool


@dataclass(frozen=True, slots=True)
class PersistentGroup:
    dimension: str
    label: str
    consecutive_windows: int
    window_run_ids: tuple[str, ...]
    latest_cumulative_win_rate: float
    latest_cumulative_clean_completed: int
    latest_cumulative_decisive: int
    latest_cumulative_average_rr: float
    filter_impact: GroupFilterImpact


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
    runs - a distinct, non-overlapping sample of new
    clean_completed/wins/losses - not a re-read of the same
    cumulative total, so three confirming windows are three separate
    pieces of evidence, not one number seen three times. (This is a
    non-overlap guarantee, not a claim of statistical independence -
    consecutive windows can still share serial/market correlation.)
    A window with zero incremental clean_completed carries no
    evidence and breaks the persistence claim (it cannot confirm in
    either direction).

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

            wins_removed = sum(window.delta_wins for window in windows)
            losses_removed = sum(window.delta_losses for window in windows)
            filter_impact = GroupFilterImpact(
                wins_removed=wins_removed,
                losses_removed=losses_removed,
                would_remove_profitable_cases=wins_removed > 0,
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
                        latest_cumulative_decisive=latest_row.decisive,
                        latest_cumulative_average_rr=latest_row.average_rr,
                        filter_impact=filter_impact,
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
                        latest_cumulative_decisive=latest_row.decisive,
                        latest_cumulative_average_rr=latest_row.average_rr,
                        filter_impact=filter_impact,
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


_METRIC_COVERAGE_NOTE = (
    "(group-level metrics: win_rate, average_rr, total_profit - supported "
    "and reported; " + "/".join(GROUP_LEVEL_UNSUPPORTED_METRICS) + ": NOT "
    "provided by the grouped endpoint, not fabricated, not reported.)"
)


def render_daily_summary(result: DailyAnalysisResult) -> str:
    """
    Concise, decision-oriented text summary of one daily analysis -
    not a raw JSON dump.
    """

    lines = [
        f"Outcome Intelligence — daily change "
        f"({result.prior_run_id} -> {result.latest_run_id})",
        _METRIC_COVERAGE_NOTE,
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
                f"decisive={change.latest.decisive}, "
                f"average_rr={change.latest.average_rr:.2f}, "
                f"clean_completed={change.latest.clean_completed}, "
                f"delta_clean_completed={change.delta_clean_completed:+d}, "
                f"delta_total_profit={change.delta_total_profit:+.2f}, "
                f"delta_average_rr={change.delta_average_rr:+.2f})"
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
        _METRIC_COVERAGE_NOTE,
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
            impact = group.filter_impact
            warning = (
                " ⚠ GROUP_FILTER_IMPACT: excluding this group would also "
                f"remove {impact.wins_removed} winning and "
                f"{impact.losses_removed} losing trade(s) recorded in "
                "this persistence window"
                if impact.would_remove_profitable_cases
                else (
                    f" GROUP_FILTER_IMPACT: excluding this group would "
                    f"remove {impact.losses_removed} losing trade(s) and "
                    "0 winning trades recorded in this persistence window"
                )
            )
            lines.append(
                f"  - [{group.dimension}] {group.label}: loser-leaning "
                f"for {group.consecutive_windows} consecutive incremental "
                f"windows (runs {', '.join(group.window_run_ids)}; "
                f"cumulative-to-date win_rate="
                f"{group.latest_cumulative_win_rate:.1f}% (decisive="
                f"{group.latest_cumulative_decisive}), average_rr="
                f"{group.latest_cumulative_average_rr:.2f} over "
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
                f"{group.latest_cumulative_win_rate:.1f}% (decisive="
                f"{group.latest_cumulative_decisive}), average_rr="
                f"{group.latest_cumulative_average_rr:.2f} over "
                f"{group.latest_cumulative_clean_completed} trades)."
            )

    return "\n".join(lines)
