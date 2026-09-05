"""GIL-bounded BREAKOUT LONG trend-structure exit validation.

Predeclared contract: structural stop remains fixed at breakout_level; no fixed-R
target; exit on the first completed daily close <= SMA20. Research/paper only.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from math import isfinite

from backtesting.trade_simulator import ExecutionAssumptions
from market_data.foundation import MarketSeries
from market_data.yahoo_provider import YahooChartDailyProvider
from models.position import Position
from research.breakout_validation import BreakoutValidationSummary
from research.run_breakout_validation import HISTORY_BARS, UNIVERSE, split_and_validate


SMA_PERIOD = 20
OOS_WARMUP_BARS = 50


@dataclass(frozen=True, slots=True)
class TrendExitTradeEvidence:
    symbol: str
    signal_time: str
    entry: float
    stop: float
    exit_reason: str
    holding_bars: int
    pnl_1unit: float
    fees_1unit: float
    net_r: float
    gap_stop: bool


@dataclass(frozen=True, slots=True)
class TrendExitSummary:
    trades: int
    wins: int
    losses: int
    unresolved: int
    win_rate: float | None
    average_net_r: float | None
    profit_factor_r: float | None
    net_pnl_1unit: float
    max_cumulative_r_drawdown: float
    average_holding_bars: float | None
    median_holding_bars: float | None
    structural_stop_exits: int
    sma20_exits: int
    gap_stops: int


def _slice(series: MarketSeries, start: int, end: int) -> MarketSeries:
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


def _median(values: list[int]) -> float | None:
    if not values:
        return None
    values = sorted(values)
    mid = len(values) // 2
    return float(values[mid]) if len(values) % 2 else (values[mid - 1] + values[mid]) / 2.0


def _sma20_before_or_at(bars, index: int) -> float | None:
    start = index - SMA_PERIOD + 1
    if start < 0:
        return None
    closes = bars[start : index + 1]
    if len(closes) != SMA_PERIOD:
        return None
    return float(sum(bar.close for bar in closes) / SMA_PERIOD)


def simulate_filled_observations(
    series: MarketSeries,
    summary: BreakoutValidationSummary,
) -> tuple[TrendExitTradeEvidence, ...]:
    assumptions = ExecutionAssumptions()
    evidence: list[TrendExitTradeEvidence] = []
    bars = series.bars

    for obs in summary.observations:
        if obs.status != "FILLED":
            continue
        if obs.fill_price is None or obs.fill_index is None:
            raise ValueError("FILLED observation missing fill evidence")

        entry = float(obs.fill_price)
        stop = float(obs.invalidation_price)
        risk = entry - stop
        if risk <= 0:
            raise ValueError("non-positive structural risk in filled BREAKOUT observation")

        raw_exit = None
        exit_index = None
        exit_reason = None
        gap_stop = False

        # Exit evidence begins strictly after the fill bar. This prevents
        # same-bar look-ahead for the completed-bar SMA20 condition.
        for index in range(obs.fill_index + 1, len(bars)):
            bar = bars[index]
            if float(bar.low) <= stop:
                raw_exit = stop
                exit_index = index
                exit_reason = "structural_stop"
                gap_stop = float(bar.open) < stop
                break

            sma20 = _sma20_before_or_at(bars, index)
            if sma20 is None:
                raise ValueError("missing SMA20 evidence after filled BREAKOUT observation")
            if float(bar.close) <= sma20:
                raw_exit = float(bar.close)
                exit_index = index
                exit_reason = "sma20_close"
                break

        if raw_exit is None:
            raw_exit = float(bars[-1].close)
            exit_index = len(bars) - 1
            exit_reason = "window_close"

        slippage_rate = assumptions.slippage_bps_per_side / 10_000.0
        fee_rate = assumptions.fee_bps_per_side / 10_000.0
        entry_fill = entry * (1.0 + slippage_rate)
        exit_fill = raw_exit * (1.0 - slippage_rate)
        gross_pnl = exit_fill - entry_fill
        fees = (entry_fill + exit_fill) * fee_rate
        pnl = gross_pnl - fees
        net_r = pnl / risk
        if not isfinite(net_r):
            raise ValueError("non-finite R result")

        evidence.append(
            TrendExitTradeEvidence(
                symbol=obs.symbol,
                signal_time=str(obs.signal_time),
                entry=entry,
                stop=stop,
                exit_reason=exit_reason,
                holding_bars=int(exit_index - obs.fill_index),
                pnl_1unit=float(pnl),
                fees_1unit=float(fees),
                net_r=float(net_r),
                gap_stop=gap_stop,
            )
        )
    return tuple(evidence)


def summarize(trades: tuple[TrendExitTradeEvidence, ...]) -> TrendExitSummary:
    resolved = [t for t in trades if t.exit_reason != "window_close"]
    wins = sum(t.net_r > 0 for t in resolved)
    losses = sum(t.net_r <= 0 for t in resolved)
    unresolved = sum(t.exit_reason == "window_close" for t in trades)
    positive = sum(t.net_r for t in resolved if t.net_r > 0)
    negative = sum(t.net_r for t in resolved if t.net_r < 0)

    peak = 0.0
    equity = 0.0
    max_dd = 0.0
    for trade in sorted(trades, key=lambda t: t.signal_time):
        equity += trade.net_r
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)

    holding = [t.holding_bars for t in trades]
    return TrendExitSummary(
        trades=len(trades),
        wins=wins,
        losses=losses,
        unresolved=unresolved,
        win_rate=(wins / len(resolved)) if resolved else None,
        average_net_r=(sum(t.net_r for t in trades) / len(trades)) if trades else None,
        profit_factor_r=(positive / abs(negative)) if negative < 0 else None,
        net_pnl_1unit=sum(t.pnl_1unit for t in trades),
        max_cumulative_r_drawdown=max_dd,
        average_holding_bars=(sum(holding) / len(holding)) if holding else None,
        median_holding_bars=_median(holding),
        structural_stop_exits=sum(t.exit_reason == "structural_stop" for t in trades),
        sma20_exits=sum(t.exit_reason == "sma20_close" for t in trades),
        gap_stops=sum(t.gap_stop for t in trades),
    )


def validate_symbol(series: MarketSeries) -> dict:
    split = split_and_validate(series)
    dev_series = _slice(series, 0, split.split_index)
    oos_start = max(0, split.split_index - OOS_WARMUP_BARS)
    oos_series = _slice(series, oos_start, len(series.bars))

    dev_trades = simulate_filled_observations(dev_series, split.development)
    oos_trades = simulate_filled_observations(oos_series, split.out_of_sample)
    return {
        "symbol": series.instrument.symbol,
        "development": asdict(summarize(dev_trades)),
        "oos": asdict(summarize(oos_trades)),
        "oos_trades": [asdict(t) for t in oos_trades],
    }


async def run() -> dict:
    provider = YahooChartDailyProvider(UNIVERSE)
    instruments = await provider.universe()
    symbols = []
    for instrument in instruments:
        series = await provider.history(instrument, limit=HISTORY_BARS)
        symbols.append(validate_symbol(series))

    all_oos = tuple(
        TrendExitTradeEvidence(**trade)
        for symbol in symbols
        for trade in symbol["oos_trades"]
    )
    return {
        "hypothesis": "BREAKOUT_LONG_STRUCTURAL_STOP_SMA20_CLOSE_EXIT",
        "sma_period": SMA_PERIOD,
        "universe": list(UNIVERSE),
        "symbols": symbols,
        "oos_total": asdict(summarize(all_oos)),
        "notes": {
            "pnl_unit": "1-unit trade PnL; not portfolio PnL or sizing evidence",
            "drawdown_unit": "cumulative trade R; not portfolio drawdown",
            "structural_stop": "fixed breakout_level; never trailed",
            "trend_exit": "first completed daily close <= SMA20 after fill bar",
            "broker": "ZERO",
            "live_money": "ZERO",
        },
    }


def main() -> None:
    print(json.dumps(asyncio.run(run()), sort_keys=True))


if __name__ == "__main__":
    main()
