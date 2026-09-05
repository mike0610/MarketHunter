"""Dataset/OOS runner for the bounded BREAKOUT LONG entry hypothesis.

Research-only. Produces entry-contract evidence, not a trading authorization.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal

from market_data.yahoo_provider import YahooChartDailyProvider
from research.breakout_validation import BreakoutValidationSummary, validate_breakout_entries
from research.validation_core import ValidationSpec, validate_chronologically


UNIVERSE = ("SPY", "QQQ", "AAPL", "MSFT", "NVDA")
HISTORY_BARS = 1300
VALIDATION_SPEC = ValidationSpec(development_fraction=Decimal("0.70"), minimum_bars=250, warmup_bars=50)\nDEVELOPMENT_FRACTION = VALIDATION_SPEC.development_fraction


@dataclass(frozen=True, slots=True)
class SymbolSplitResult:
    symbol: str
    total_bars: int
    split_index: int
    development: BreakoutValidationSummary
    out_of_sample: BreakoutValidationSummary


@dataclass(frozen=True, slots=True)
class DatasetValidationResult:
    symbols: tuple[SymbolSplitResult, ...]

    @property
    def oos_signals(self) -> int:
        return sum(s.out_of_sample.signals for s in self.symbols)

    @property
    def oos_fills(self) -> int:
        return sum(s.out_of_sample.fills for s in self.symbols)


def _slice_series(series, start: int, end: int):
    from market_data.foundation import MarketSeries
    bars = series.bars[start:end]
    return MarketSeries(
        instrument=series.instrument,
        timeframe=series.timeframe,
        bars=bars,
        provider=series.provider,
        source_reference=series.source_reference,
        observed_at=series.observed_at,
        available_at=series.available_at,
    )


def split_and_validate(series) -> SymbolSplitResult:
    """Chronological 70/30 split, declared once for every symbol."""
    if len(series.bars) < 250:
        raise ValueError("insufficient history for bounded validation")
    split = int(Decimal(len(series.bars)) * DEVELOPMENT_FRACTION)
    # OOS needs 50 pre-split bars only to warm canonical SMA50/formation.
    # Results whose signal is in the warmup region are discarded by slicing
    # the observations after validation.
    development_series = _slice_series(series, 0, split)
    oos_start = max(0, split - 50)
    oos_series = _slice_series(series, oos_start, len(series.bars))
    dev = validate_breakout_entries(development_series)
    raw_oos = validate_breakout_entries(oos_series)
    warmup = split - oos_start
    kept = tuple(o for o in raw_oos.observations if o.signal_index >= warmup)
    oos = BreakoutValidationSummary(
        signals=len(kept),
        fills=sum(o.status == "FILLED" for o in kept),
        expired=sum(o.status == "EXPIRED" for o in kept),
        invalidated_before_fill=sum(
            o.status in {"INVALIDATED_BEFORE_FILL", "AMBIGUOUS_NO_FILL"} for o in kept
        ),
        gap_entries=sum(
            o.status == "FILLED" and o.fill_price is not None and o.fill_price > o.trigger_price
            for o in kept
        ),
        observations=kept,
    )
    return SymbolSplitResult(
        symbol=series.instrument.symbol,
        total_bars=len(series.bars),
        split_index=split,
        development=dev,
        out_of_sample=oos,
    )


async def run_yahoo_breakout_validation() -> DatasetValidationResult:
    provider = YahooChartDailyProvider(UNIVERSE)
    instruments = await provider.universe()
    results = []
    for instrument in instruments:
        series = await provider.history(instrument, limit=HISTORY_BARS)
        results.append(split_and_validate(series))
    return DatasetValidationResult(tuple(results))


def main() -> None:
    result = asyncio.run(run_yahoo_breakout_validation())
    for item in result.symbols:
        print(
            f"{item.symbol}: bars={item.total_bars} "
            f"dev signals/fills={item.development.signals}/{item.development.fills} "
            f"oos signals/fills={item.out_of_sample.signals}/{item.out_of_sample.fills} "
            f"oos expired={item.out_of_sample.expired} "
            f"oos invalidated={item.out_of_sample.invalidated_before_fill} "
            f"oos gaps={item.out_of_sample.gap_entries}"
        )
    print(f"OOS TOTAL: signals={result.oos_signals} fills={result.oos_fills}")


if __name__ == "__main__":
    main()
