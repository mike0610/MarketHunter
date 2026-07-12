"""
MarketHunter

Module:
Research Trade Outcome Classifier

Responsibilities:
- Classify a ResearchTrade into an analytical outcome_group/outcome_type.
- Never override a manually-locked classification (see trade.outcome_locked).
- Never touch lifecycle `status`.

This classifier reads the trade's *current* status and close_reason.
It is called from ResearchRepository.save() so every persisted trade
stays classified without touching monitor/candidate-promotion code.

Known close_reason values produced by the engine today
(verified against a real production data/research.db snapshot,
2026-07-12 - see cleanup pattern comment below for the two that don't
follow the plain TP/SL/EXPIRED shape):
- "TP"        -> TradeStatus.CLOSED
- "SL"        -> TradeStatus.CLOSED
- "EXPIRED"   -> TradeStatus.EXPIRED
- "WAITING_ENTRY_REVALIDATION_FAILED: ..." -> TradeStatus.CANDIDATE
- "CANDIDATE_PROMOTION_BLOCKED: ..." -> TradeStatus.CANDIDATE

Cleanup reasons observed on real EXPIRED trades (a housekeeping script
can apparently close a trade out-of-band, not just TradeMonitor.expire()):
- "MANUAL_CLEANUP: <free text>"            -> TradeStatus.EXPIRED
- "DUPLICATE_CANDIDATE_CLEANUP: <free text>" -> TradeStatus.EXPIRED

These must NOT fall through to profit-based expired_profit/expired_loss/
expired_neutral just because they happen to carry status=EXPIRED - the
reason prefix always wins over the profit sign. This is why cleanup
pattern matching runs first, for both CLOSED and EXPIRED trades, before
any TP/SL/profit-sign branching.

Cleanup patterns below are intentionally specific ("manual_cleanup",
not a bare "manual") after a review round flagged the bare "manual"
fallback as too broad - a future close_reason that merely contains
"manual" without meaning cleanup would otherwise get silently
mis-routed to invalid_legacy. A generic "duplicate" fallback is kept
since every real and hypothetical duplicate-style reason observed so
far is cleanup-flavoured, unlike "manual".

TP/SL matching also accepts "take_profit"/"stop_loss" as a substring,
not just the exact "tp"/"sl" the engine produces today
(research/monitor.py). This is defensive hardening for a close_reason
shape that does not exist anywhere in the current codebase or
production data (verified by grepping research/monitor.py,
research/monitor_service.py, research/manager.py,
research/candidate_promotion_service.py and the real research.db -
only "TP"/"SL" literals were found, nothing "live"-prefixed) - not a
fix for an observed bug. Kept here only so a future live-trading
close_reason format doesn't need a second migration.
"""

from __future__ import annotations

from research.models.trade import ResearchTrade
from research.models.trade_outcome import (
    outcome_group_for,
    TradeOutcomeGroup,
    TradeOutcomeType,
)
from research.models.trade_status import TradeStatus


_OPEN_STATUSES = (
    TradeStatus.CANDIDATE,
    TradeStatus.WAITING_ENTRY,
    TradeStatus.ACTIVE,
)

_TERMINAL_STATUSES = (
    TradeStatus.CLOSED,
    TradeStatus.EXPIRED,
)

# Substring match against a lowercased close_reason. First match wins.
# Checked before TP/SL/profit-sign branching, for CLOSED and EXPIRED
# trades alike - a cleanup reason always outranks the profit outcome.
# Specific patterns first, generic "duplicate" fallback last - there is
# deliberately no generic "manual" fallback (see module docstring).
_CLEANUP_PATTERNS: tuple[tuple[str, TradeOutcomeType], ...] = (
    ("universe_filter_cleanup", TradeOutcomeType.UNIVERSE_CLEANUP),
    ("duplicate_candidate_cleanup", TradeOutcomeType.UNIVERSE_CLEANUP),
    ("duplicate_cleanup", TradeOutcomeType.UNIVERSE_CLEANUP),
    ("manual_cleanup", TradeOutcomeType.INVALID_LEGACY),
    ("invalid_legacy", TradeOutcomeType.INVALID_LEGACY),
    ("duplicate", TradeOutcomeType.UNIVERSE_CLEANUP),
)


def classify_research_trade(
    trade: ResearchTrade,
) -> tuple[TradeOutcomeGroup, TradeOutcomeType]:
    """
    Return (outcome_group, outcome_type) for one research trade.

    Callers are responsible for skipping this when the trade carries a
    manual lock (trade.outcome_locked) - see ResearchRepository.save().
    """

    if trade.status in _OPEN_STATUSES:
        return _resolve(TradeOutcomeType.OPEN_ACTIVE)

    if trade.status not in _TERMINAL_STATUSES:
        return _resolve(TradeOutcomeType.UNCLASSIFIED)

    cleanup = _match_cleanup_pattern(
        _normalized_reason(trade),
    )

    if cleanup is not None:
        return _resolve(cleanup)

    if trade.status == TradeStatus.CLOSED:
        return _resolve(_classify_closed(trade))

    return _resolve(_classify_expired(trade))


def _classify_closed(
    trade: ResearchTrade,
) -> TradeOutcomeType:
    reason = _normalized_reason(trade)

    if reason == "tp" or "take_profit" in reason:
        return TradeOutcomeType.TAKE_PROFIT

    if reason == "sl" or "stop_loss" in reason:
        return TradeOutcomeType.STOP_LOSS

    return TradeOutcomeType.UNCLASSIFIED


def _classify_expired(
    trade: ResearchTrade,
) -> TradeOutcomeType:
    if trade.profit_percent > 0:
        return TradeOutcomeType.EXPIRED_PROFIT

    if trade.profit_percent < 0:
        return TradeOutcomeType.EXPIRED_LOSS

    return TradeOutcomeType.EXPIRED_NEUTRAL


def _match_cleanup_pattern(
    reason: str,
) -> TradeOutcomeType | None:
    for keyword, outcome_type in _CLEANUP_PATTERNS:
        if keyword in reason:
            return outcome_type

    return None


def _normalized_reason(
    trade: ResearchTrade,
) -> str:
    return str(
        trade.close_reason or ""
    ).strip().lower()


def _resolve(
    outcome_type: TradeOutcomeType,
) -> tuple[TradeOutcomeGroup, TradeOutcomeType]:
    return outcome_group_for(outcome_type), outcome_type
