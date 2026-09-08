from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from market_data.foundation import MarketBar, MarketSeries
from market_data.twelve_data_earnings import EarningsEvent


class EarningsDriftDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass(frozen=True, slots=True)
class EarningsDriftSignal:
    symbol: str
    signal_date: date
    direction: EarningsDriftDirection
    signal_bar_high: Decimal
    signal_bar_low: Decimal
    volume_ratio: Decimal
    catalyst_reference: str


def _event_dates(events: tuple[EarningsEvent, ...], symbol: str) -> set[date]:
    s = symbol.upper()
    return {e.earnings_date for e in events if e.symbol == s}


def detect_earnings_volume_drift_signals(
    series: MarketSeries,
    events: tuple[EarningsEvent, ...],
) -> tuple[EarningsDriftSignal, ...]:
    """Frozen GIL v0.1 formation only. No outcome/exit logic lives here."""
    bars = series.bars
    if len(bars) < 21:
        return ()
    event_dates = _event_dates(events, series.instrument.symbol)
    refs = {e.earnings_date: e.source_reference for e in events if e.symbol == series.instrument.symbol.upper()}
    out: list[EarningsDriftSignal] = []
    for i in range(20, len(bars)):
        bar: MarketBar = bars[i]
        d = bar.timestamp.date()
        if d not in event_dates:
            continue
        baseline = sum((x.volume for x in bars[i - 20:i]), Decimal("0")) / Decimal("20")
        if baseline <= 0:
            continue
        ratio = bar.volume / baseline
        if ratio < Decimal("3"):
            continue
        prev = bars[i - 1]
        direction = None
        if bar.close > prev.close and bar.close > bar.open:
            direction = EarningsDriftDirection.LONG
        elif bar.close < prev.close and bar.close < bar.open:
            direction = EarningsDriftDirection.SHORT
        if direction is None:
            continue
        out.append(EarningsDriftSignal(
            symbol=series.instrument.symbol,
            signal_date=d,
            direction=direction,
            signal_bar_high=bar.high,
            signal_bar_low=bar.low,
            volume_ratio=ratio,
            catalyst_reference=refs[d],
        ))
    return tuple(out)
