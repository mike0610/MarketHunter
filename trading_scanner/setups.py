"""
MarketHunter

trading_scanner/setups.py

Module:
Setup-family classification - deterministic v1 rules only, no learned/
ranked score. All three dispatched families are implemented:
MOMENTUM_RELATIVE_STRENGTH, ABNORMAL_VOLUME_CATALYST,
BREAKOUT_OR_PULLBACK_IN_TREND.

Every classifier is a pure function over already-fetched OHLCV history
(trading_scanner.universe.ContractMarketData) - never a live fetch of
its own, and never a fabricated indicator value: a classifier that
does not have enough history to compute its own rule returns None
(DATA_FAIL), never a guessed classification.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from trading_scanner.models import CatalystEvidence
from trading_scanner.universe import ContractMarketData

# The two moving-average windows the trend-alignment rule is defined
# over - a well-established, explainable check, not an invented magic
# number. Shared by MOMENTUM_RELATIVE_STRENGTH and
# BREAKOUT_OR_PULLBACK_IN_TREND, both of which require the same
# underlying trend context.
_SHORT_WINDOW = 20
_LONG_WINDOW = 50

# ABNORMAL_VOLUME_CATALYST: today's volume must exceed this multiple of
# the prior average - a conservative, explainable threshold, not a
# fabricated probability.
_ABNORMAL_VOLUME_MULTIPLE = Decimal("3")

# BREAKOUT_OR_PULLBACK_IN_TREND: how close to the 20-day SMA counts as
# a "pullback" (a band, not an exact touch) - and the breakout lookback
# window (the 20-day high, excluding today).
_PULLBACK_BAND_PCT = Decimal("2")
_BREAKOUT_LOOKBACK = 20

# MOMENTUM_RELATIVE_STRENGTH's optional benchmark leg: the lookback
# window for comparing the symbol's own return against the benchmark's.
_RELATIVE_STRENGTH_LOOKBACK = 20


@dataclass(frozen=True, slots=True)
class SetupClassification:
    matched: bool
    reason_stack: tuple[str, ...]  # always non-empty, explaining the match OR the non-match
    invalidation_reference: str | None = None


def _sma(values: tuple[Decimal, ...], window: int) -> Decimal:
    tail = values[-window:]
    return sum(tail, start=Decimal("0")) / window


def _trend_aligned(market_data: ContractMarketData) -> tuple[bool, Decimal, Decimal] | None:
    """Shared trend-context leg: None if too little history, else (aligned, sma_short, sma_long)."""
    if len(market_data.closes) < _LONG_WINDOW:
        return None
    sma_short = _sma(market_data.closes, _SHORT_WINDOW)
    sma_long = _sma(market_data.closes, _LONG_WINDOW)
    return sma_short > sma_long, sma_short, sma_long


def classify_momentum_relative_strength(
    market_data: ContractMarketData, benchmark: ContractMarketData | None = None
) -> SetupClassification | None:
    """
    MOMENTUM_RELATIVE_STRENGTH v1 rule: close above its own 20-day SMA,
    AND the 20-day SMA above the 50-day SMA (short-term trend aligned
    above the longer-term trend) - a standard, explainable momentum/
    trend-alignment check. Returns None (DATA_FAIL - not enough
    history to compute the 50-day SMA) rather than a guessed result.

    `benchmark` is optional and additive, per "relative-strength aware
    where evidence allows": when supplied (with at least
    _RELATIVE_STRENGTH_LOOKBACK+1 closes of its own), a genuine
    relative-strength leg is ALSO required - the symbol's own trailing
    return over the lookback window must exceed the benchmark's over
    the same window. Absent a benchmark, the rule behaves exactly as
    before - relative strength is never fabricated from a benchmark
    this call was not actually given.
    """
    trend = _trend_aligned(market_data)
    if trend is None:
        return None
    trend_aligned, sma_short, sma_long = trend

    close = market_data.closes[-1]
    price_above_short = close > sma_short

    reasons: list[str] = []
    relative_strength_ok = True
    if benchmark is not None and len(benchmark.closes) > _RELATIVE_STRENGTH_LOOKBACK:
        if len(market_data.closes) > _RELATIVE_STRENGTH_LOOKBACK:
            symbol_return = (market_data.closes[-1] / market_data.closes[-1 - _RELATIVE_STRENGTH_LOOKBACK]) - 1
            benchmark_return = (benchmark.closes[-1] / benchmark.closes[-1 - _RELATIVE_STRENGTH_LOOKBACK]) - 1
            relative_strength_ok = symbol_return > benchmark_return
            reasons.append(
                f"{_RELATIVE_STRENGTH_LOOKBACK}-bar return {symbol_return:.4f} "
                f"{'>' if relative_strength_ok else '<='} benchmark return {benchmark_return:.4f}"
            )

    if trend_aligned and price_above_short and relative_strength_ok:
        return SetupClassification(
            matched=True,
            reason_stack=(
                f"close {close} > SMA{_SHORT_WINDOW} {sma_short}",
                f"SMA{_SHORT_WINDOW} {sma_short} > SMA{_LONG_WINDOW} {sma_long} (trend aligned)",
                *reasons,
            ),
            invalidation_reference=f"close back below SMA{_SHORT_WINDOW} ({sma_short})",
        )

    if not price_above_short:
        reasons.insert(0, f"close {close} <= SMA{_SHORT_WINDOW} {sma_short}")
    if not trend_aligned:
        reasons.insert(0, f"SMA{_SHORT_WINDOW} {sma_short} <= SMA{_LONG_WINDOW} {sma_long} (trend not aligned)")
    return SetupClassification(matched=False, reason_stack=tuple(reasons))


def classify_abnormal_volume_catalyst(
    market_data: ContractMarketData, catalyst: CatalystEvidence | None
) -> SetupClassification | None:
    """
    ABNORMAL_VOLUME_CATALYST v1 rule: today's volume exceeds
    _ABNORMAL_VOLUME_MULTIPLE times the average of the prior
    _SHORT_WINDOW days (excluding today, so today's own spike never
    inflates its own baseline) AND explicit catalyst evidence is
    present. This repo has no news/filing feed of its own - `catalyst`
    is always caller-supplied; if it is None, this setup structurally
    cannot match, no matter how abnormal the volume is - never
    fabricated. Returns None (DATA_FAIL) if there isn't enough prior
    history to compute the baseline.
    """
    if len(market_data.volumes) < _SHORT_WINDOW + 1:
        return None

    today_volume = market_data.volumes[-1]
    baseline = _sma(market_data.volumes[-(_SHORT_WINDOW + 1):-1], _SHORT_WINDOW)
    if baseline == 0:
        return SetupClassification(matched=False, reason_stack=(f"{_SHORT_WINDOW}-day average volume baseline is zero",))

    ratio = today_volume / baseline
    volume_abnormal = ratio >= _ABNORMAL_VOLUME_MULTIPLE

    if volume_abnormal and catalyst is not None:
        return SetupClassification(
            matched=True,
            reason_stack=(
                f"volume {today_volume} is {ratio:.2f}x the {_SHORT_WINDOW}-day average {baseline}",
                f"catalyst: {catalyst.description} (source={catalyst.source})",
            ),
            invalidation_reference=None,  # no deterministic structural level this rule itself defines
        )

    reasons = []
    if not volume_abnormal:
        reasons.append(
            f"volume {today_volume} is only {ratio:.2f}x the {_SHORT_WINDOW}-day average {baseline} "
            f"(< {_ABNORMAL_VOLUME_MULTIPLE}x threshold)"
        )
    if catalyst is None:
        reasons.append("no catalyst evidence supplied")
    return SetupClassification(matched=False, reason_stack=tuple(reasons))


def classify_breakout_or_pullback_in_trend(market_data: ContractMarketData) -> SetupClassification | None:
    """
    BREAKOUT_OR_PULLBACK_IN_TREND v1 rule: requires the same established-
    trend context as MOMENTUM_RELATIVE_STRENGTH (SMA20 > SMA50), then
    EITHER:
      - BREAKOUT: today's close exceeds the highest close of the prior
        _BREAKOUT_LOOKBACK days (excluding today); or
      - PULLBACK: close is within _PULLBACK_BAND_PCT percent of the
        20-day SMA (a shallow retracement, not a trend break) while the
        trend itself remains intact.
    Both sub-cases are reported explicitly in reason_stack. Returns
    None (DATA_FAIL) without enough history for either leg.
    """
    trend = _trend_aligned(market_data)
    if trend is None:
        return None
    trend_aligned, sma_short, sma_long = trend
    if len(market_data.closes) < _BREAKOUT_LOOKBACK + 1:
        return None

    close = market_data.closes[-1]

    if not trend_aligned:
        return SetupClassification(
            matched=False,
            reason_stack=(f"SMA{_SHORT_WINDOW} {sma_short} <= SMA{_LONG_WINDOW} {sma_long} (trend not aligned)",),
        )

    prior_high = max(market_data.closes[-(_BREAKOUT_LOOKBACK + 1):-1])
    if close > prior_high:
        return SetupClassification(
            matched=True,
            reason_stack=(
                f"BREAKOUT: close {close} > prior {_BREAKOUT_LOOKBACK}-day high {prior_high}",
                f"SMA{_SHORT_WINDOW} {sma_short} > SMA{_LONG_WINDOW} {sma_long} (trend aligned)",
            ),
            invalidation_reference=f"close back below the breakout level ({prior_high})",
        )

    distance_pct = abs(close - sma_short) / sma_short * Decimal("100")
    if distance_pct <= _PULLBACK_BAND_PCT:
        return SetupClassification(
            matched=True,
            reason_stack=(
                f"PULLBACK: close {close} within {distance_pct:.2f}% of SMA{_SHORT_WINDOW} {sma_short} "
                f"(band {_PULLBACK_BAND_PCT}%)",
                f"SMA{_SHORT_WINDOW} {sma_short} > SMA{_LONG_WINDOW} {sma_long} (trend aligned)",
            ),
            invalidation_reference=f"close back below SMA{_LONG_WINDOW} ({sma_long})",
        )

    return SetupClassification(
        matched=False,
        reason_stack=(
            f"trend aligned but neither breakout (close {close} <= prior high {prior_high}) "
            f"nor pullback (close {distance_pct:.2f}% from SMA{_SHORT_WINDOW}, band {_PULLBACK_BAND_PCT}%)",
        ),
    )
