"""Bounded historical validation harness for BREAKOUT LONG conditional entry.

Research-only. No broker, order, Risk/MM, sizing, or production runtime surface.
The entry hypothesis is predeclared by GIL: signal-bar high trigger, existing
breakout structural level invalidation, three forward trading bars expiry.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import inf

from backtesting.trade_simulator import ExecutionAssumptions
from market_data.foundation import MarketBar, MarketSeries


@dataclass(frozen=True, slots=True)
class BreakoutObservation:
    symbol: str
    signal_index: int
    signal_time: object
    trigger_price: Decimal
    invalidation_price: Decimal
    status: str
    fill_price: Decimal | None
    fill_index: int | None


@dataclass(frozen=True, slots=True)
class BreakoutValidationSummary:
    signals: int
    fills: int
    expired: int
    invalidated_before_fill: int
    gap_entries: int
    observations: tuple[BreakoutObservation, ...]


def _sma(bars: tuple[MarketBar, ...], end: int, length: int) -> Decimal:
    window = bars[end - length + 1 : end + 1]
    return sum((bar.close for bar in window), Decimal("0")) / Decimal(length)


def find_breakout_signals(series: MarketSeries) -> tuple[tuple[int, Decimal], ...]:
    """Canonical formation only: SMA20>SMA50 and close>prior-20 highest close."""
    bars = series.bars
    found: list[tuple[int, Decimal]] = []
    for i in range(50, len(bars)):
        sma20 = _sma(bars, i, 20)
        sma50 = _sma(bars, i, 50)
        prior_highest_close = max(bar.close for bar in bars[i - 20 : i])
        if sma20 > sma50 and bars[i].close > prior_highest_close:
            found.append((i, prior_highest_close))
    return tuple(found)


def evaluate_entry(
    series: MarketSeries,
    signal_index: int,
    breakout_level: Decimal,
    *,
    expiry_bars: int = 3,
) -> BreakoutObservation:
    """Forward-only conditional entry. Signal bar can never fill itself."""
    if expiry_bars != 3:
        raise ValueError("Stage 10 bounded hypothesis is predeclared at exactly 3 trading bars")
    bars = series.bars
    signal = bars[signal_index]
    trigger = signal.high
    end = min(signal_index + expiry_bars, len(bars) - 1)

    for i in range(signal_index + 1, end + 1):
        bar = bars[i]
        # Invalidation is close-based per the existing structural reference.
        # If a bar crosses the trigger intraday but closes below the breakout
        # boundary, chronology inside daily OHLC is unknowable, so fail closed.
        crossed = bar.high >= trigger
        invalid_close = bar.close < breakout_level
        if crossed and invalid_close:
            return BreakoutObservation(
                series.instrument.symbol, signal_index, signal.timestamp, trigger,
                breakout_level, "AMBIGUOUS_NO_FILL", None, None,
            )
        if invalid_close:
            return BreakoutObservation(
                series.instrument.symbol, signal_index, signal.timestamp, trigger,
                breakout_level, "INVALIDATED_BEFORE_FILL", None, None,
            )
        if crossed:
            # Stop order gap realism: a gap above trigger cannot fill at trigger.
            raw_fill = max(trigger, bar.open)
            return BreakoutObservation(
                series.instrument.symbol, signal_index, signal.timestamp, trigger,
                breakout_level, "FILLED", raw_fill, i,
            )

    return BreakoutObservation(
        series.instrument.symbol, signal_index, signal.timestamp, trigger,
        breakout_level, "EXPIRED", None, None,
    )


def validate_breakout_entries(series: MarketSeries) -> BreakoutValidationSummary:
    observations = tuple(
        evaluate_entry(series, idx, level)
        for idx, level in find_breakout_signals(series)
    )
    return BreakoutValidationSummary(
        signals=len(observations),
        fills=sum(o.status == "FILLED" for o in observations),
        expired=sum(o.status == "EXPIRED" for o in observations),
        invalidated_before_fill=sum(
            o.status in {"INVALIDATED_BEFORE_FILL", "AMBIGUOUS_NO_FILL"}
            for o in observations
        ),
        gap_entries=sum(
            o.status == "FILLED" and o.fill_price is not None and o.fill_price > o.trigger_price
            for o in observations
        ),
        observations=observations,
    )


def modeled_entry_cost(fill_price: Decimal, assumptions: ExecutionAssumptions | None = None) -> Decimal:
    """Existing research cost assumptions, applied without tuning."""
    a = assumptions or ExecutionAssumptions()
    bps = Decimal(str(a.fee_bps_per_side + a.slippage_bps_per_side))
    return fill_price * bps / Decimal("10000")
