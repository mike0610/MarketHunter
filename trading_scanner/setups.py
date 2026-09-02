"""
MarketHunter

trading_scanner/setups.py

Module:
Setup-family classification - deterministic v1 rules only, no learned/
ranked score. This bounded slice implements exactly one of the three
dispatched families (MOMENTUM_RELATIVE_STRENGTH); ABNORMAL_VOLUME_CATALYST
and BREAKOUT_OR_PULLBACK_IN_TREND are deliberately deferred to a
follow-up slice, per explicit direct guidance this cycle to keep
changes minimal - see the PR description for exactly what remains.

Every classifier is a pure function over already-fetched OHLCV history
(trading_scanner.universe.ContractMarketData) - never a live fetch of
its own, and never a fabricated indicator value: a classifier that
does not have enough history to compute its own rule returns None
(DATA_FAIL), never a guessed classification.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from trading_scanner.universe import ContractMarketData

# The two moving-average windows this rule is defined over - a
# well-established, explainable trend/momentum alignment check, not an
# invented magic number. Requires at least this many closes to compute
# both windows.
_SHORT_WINDOW = 20
_LONG_WINDOW = 50


@dataclass(frozen=True, slots=True)
class SetupClassification:
    matched: bool
    reason_stack: tuple[str, ...]  # always non-empty, explaining the match OR the non-match
    invalidation_reference: str | None = None


def _sma(values: tuple[Decimal, ...], window: int) -> Decimal:
    tail = values[-window:]
    return sum(tail, start=Decimal("0")) / window


def classify_momentum_relative_strength(market_data: ContractMarketData) -> SetupClassification | None:
    """
    MOMENTUM_RELATIVE_STRENGTH v1 rule: close above its own 20-day SMA,
    AND the 20-day SMA above the 50-day SMA (short-term trend aligned
    above the longer-term trend) - a standard, explainable momentum/
    trend-alignment check. Returns None (DATA_FAIL - not enough history
    to compute the 50-day SMA) rather than a guessed result.
    """
    if len(market_data.closes) < _LONG_WINDOW:
        return None

    close = market_data.closes[-1]
    sma_short = _sma(market_data.closes, _SHORT_WINDOW)
    sma_long = _sma(market_data.closes, _LONG_WINDOW)

    trend_aligned = sma_short > sma_long
    price_above_short = close > sma_short

    if trend_aligned and price_above_short:
        return SetupClassification(
            matched=True,
            reason_stack=(
                f"close {close} > SMA{_SHORT_WINDOW} {sma_short}",
                f"SMA{_SHORT_WINDOW} {sma_short} > SMA{_LONG_WINDOW} {sma_long} (trend aligned)",
            ),
            invalidation_reference=f"close back below SMA{_SHORT_WINDOW} ({sma_short})",
        )

    reasons = []
    if not price_above_short:
        reasons.append(f"close {close} <= SMA{_SHORT_WINDOW} {sma_short}")
    if not trend_aligned:
        reasons.append(f"SMA{_SHORT_WINDOW} {sma_short} <= SMA{_LONG_WINDOW} {sma_long} (trend not aligned)")
    return SetupClassification(matched=False, reason_stack=tuple(reasons))
