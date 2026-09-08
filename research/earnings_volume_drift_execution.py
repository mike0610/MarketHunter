from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from market_data.foundation import MarketBar, MarketSeries
from research.earnings_volume_drift import EarningsDriftDirection, EarningsDriftSignal


@dataclass(frozen=True, slots=True)
class EarningsDriftTrade:
    direction: EarningsDriftDirection
    signal_index: int
    entry_index: int
    entry_price: Decimal
    exit_index: int
    exit_price: Decimal
    exit_reason: str


def simulate_signal(series: MarketSeries, signal: EarningsDriftSignal) -> EarningsDriftTrade | None:
    bars=series.bars
    si=next((i for i,b in enumerate(bars) if b.timestamp.date()==signal.signal_date),None)
    if si is None:return None

    entry_i=None; entry_price=None
    # Frozen v0.1: next 3 trading sessions only; opposite signal-bar boundary invalidates pre-fill.
    for i in range(si+1,min(si+4,len(bars))):
        b=bars[i]
        if signal.direction is EarningsDriftDirection.LONG:
            trigger=b.high>=signal.signal_bar_high
            invalid=b.low<=signal.signal_bar_low
            if trigger and invalid:
                return None  # intrabar ordering unknowable; never fabricate a fill
            if invalid:return None
            if trigger:
                entry_i=i; entry_price=max(b.open,signal.signal_bar_high); break
        else:
            trigger=b.low<=signal.signal_bar_low
            invalid=b.high>=signal.signal_bar_high
            if trigger and invalid:return None
            if invalid:return None
            if trigger:
                entry_i=i; entry_price=min(b.open,signal.signal_bar_low); break
    if entry_i is None:return None

    # Exit at structural boundary or after 20 completed trading sessions, whichever first.
    time_i=min(entry_i+20,len(bars)-1)
    for i in range(entry_i+1,time_i+1):
        b=bars[i]
        if signal.direction is EarningsDriftDirection.LONG and b.low<=signal.signal_bar_low:
            return EarningsDriftTrade(signal.direction,si,entry_i,entry_price,i,min(b.open,signal.signal_bar_low),"STRUCTURAL_INVALIDATION")
        if signal.direction is EarningsDriftDirection.SHORT and b.high>=signal.signal_bar_high:
            return EarningsDriftTrade(signal.direction,si,entry_i,entry_price,i,max(b.open,signal.signal_bar_high),"STRUCTURAL_INVALIDATION")
    if entry_i+20>=len(bars):
        return None  # insufficient forward evidence for the frozen time exit
    return EarningsDriftTrade(signal.direction,si,entry_i,entry_price,entry_i+20,bars[entry_i+20].close,"TIME_EXIT")
