"""
MarketHunter

Module:
Trade Outcome Classification

Responsibilities:
- Define analytical outcome categories, separate from lifecycle `status`.
- outcome_group answers: was this trade good, bad, neutral, or excluded
  from clean statistics.
- outcome_type answers: exactly why.

This classification never changes TradeStatus. A trade can be
`status = expired` and `outcome_group = positive` at the same time
(Profitable Expired).
"""

from __future__ import annotations

from enum import StrEnum


class TradeOutcomeGroup(StrEnum):
    """
    High-level bucket used by clean statistics.
    """

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    EXCLUDED = "excluded"


class TradeOutcomeType(StrEnum):
    """
    Specific reason behind an outcome_group.
    """

    TAKE_PROFIT = "take_profit"
    STOP_LOSS = "stop_loss"

    # Reserved for managed/live stop exits once real trading exists.
    # The research engine cannot produce this today: `live/` execution
    # is not implemented, so no trade can close this way yet.
    LIVE_STOP_LOSS = "live_stop_loss"

    EXPIRED_PROFIT = "expired_profit"
    EXPIRED_LOSS = "expired_loss"
    EXPIRED_NEUTRAL = "expired_neutral"

    UNIVERSE_CLEANUP = "universe_cleanup"
    INVALID_LEGACY = "invalid_legacy"

    OPEN_ACTIVE = "open_active"

    # Safety net: a closed/expired trade whose close_reason does not
    # match any known pattern. Should stay empty in practice; existing
    # to satisfy "old trades never break the API".
    UNCLASSIFIED = "unclassified"


OUTCOME_TYPE_GROUP: dict[TradeOutcomeType, TradeOutcomeGroup] = {
    TradeOutcomeType.TAKE_PROFIT: TradeOutcomeGroup.POSITIVE,
    TradeOutcomeType.STOP_LOSS: TradeOutcomeGroup.NEGATIVE,
    TradeOutcomeType.LIVE_STOP_LOSS: TradeOutcomeGroup.NEGATIVE,
    TradeOutcomeType.EXPIRED_PROFIT: TradeOutcomeGroup.POSITIVE,
    TradeOutcomeType.EXPIRED_LOSS: TradeOutcomeGroup.NEGATIVE,
    TradeOutcomeType.EXPIRED_NEUTRAL: TradeOutcomeGroup.NEUTRAL,
    TradeOutcomeType.UNIVERSE_CLEANUP: TradeOutcomeGroup.EXCLUDED,
    TradeOutcomeType.INVALID_LEGACY: TradeOutcomeGroup.EXCLUDED,
    TradeOutcomeType.OPEN_ACTIVE: TradeOutcomeGroup.NEUTRAL,
    TradeOutcomeType.UNCLASSIFIED: TradeOutcomeGroup.NEUTRAL,
}


def outcome_group_for(
    outcome_type: TradeOutcomeType,
) -> TradeOutcomeGroup:
    """
    Return the outcome_group that belongs to one outcome_type.
    """

    return OUTCOME_TYPE_GROUP[outcome_type]
