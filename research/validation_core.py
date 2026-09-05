"""Reusable research-validation primitives.

This module deliberately contains no strategy, target, stop, sizing, leverage,
broker, or production-runtime policy. Strategy/GIL adapters supply observations;
the core supplies deterministic chronological splitting and aggregate evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Generic, Protocol, TypeVar

from market_data.foundation import MarketSeries


T = TypeVar("T")


class ObservationSummary(Protocol):
    observations: tuple


@dataclass(frozen=True, slots=True)
class ChronologicalSplit:
    development_end: int
    oos_start: int
    warmup_bars: int


@dataclass(frozen=True, slots=True)
class ValidationSpec:
    development_fraction: Decimal = Decimal("0.70")
    minimum_bars: int = 250
    warmup_bars: int = 50

    def __post_init__(self) -> None:
        if not Decimal("0") < self.development_fraction < Decimal("1"):
            raise ValueError("development_fraction must be between zero and one")
        if self.minimum_bars <= self.warmup_bars:
            raise ValueError("minimum_bars must exceed warmup_bars")
        if self.warmup_bars < 0:
            raise ValueError("warmup_bars cannot be negative")


@dataclass(frozen=True, slots=True)
class SymbolValidation(Generic[T]):
    symbol: str
    total_bars: int
    split: ChronologicalSplit
    development: T
    out_of_sample: T


def slice_series(series: MarketSeries, start: int, end: int) -> MarketSeries:
    bars = series.bars[start:end]
    if not bars:
        raise ValueError("validation slice must contain bars")
    return MarketSeries(
        instrument=series.instrument,
        timeframe=series.timeframe,
        bars=bars,
        provider=series.provider,
        source_reference=series.source_reference,
        observed_at=series.observed_at,
        available_at=series.available_at,
    )


def chronological_split(series: MarketSeries, spec: ValidationSpec | None = None) -> ChronologicalSplit:
    s = spec or ValidationSpec()
    if len(series.bars) < s.minimum_bars:
        raise ValueError("insufficient history for validation")
    development_end = int(Decimal(len(series.bars)) * s.development_fraction)
    oos_start = max(0, development_end - s.warmup_bars)
    return ChronologicalSplit(development_end, oos_start, development_end - oos_start)


def validate_chronologically(
    series: MarketSeries,
    evaluator: Callable[[MarketSeries], T],
    *,
    filter_oos: Callable[[T, int], T],
    spec: ValidationSpec | None = None,
) -> SymbolValidation[T]:
    """Run one evaluator on development and untouched OOS with historical warmup."""
    s = spec or ValidationSpec()
    split = chronological_split(series, s)
    development = evaluator(slice_series(series, 0, split.development_end))
    raw_oos = evaluator(slice_series(series, split.oos_start, len(series.bars)))
    oos = filter_oos(raw_oos, split.warmup_bars)
    return SymbolValidation(
        symbol=series.instrument.symbol,
        total_bars=len(series.bars),
        split=split,
        development=development,
        out_of_sample=oos,
    )
