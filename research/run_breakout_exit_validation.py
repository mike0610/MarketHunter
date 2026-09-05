"""GIL-bounded BREAKOUT LONG exit validation for the fixed 3R hypothesis.

Research-only. Reuses the existing BREAKOUT entry evidence and TradeSimulator.
No sizing, leverage, Risk/MM, Stage5/6, broker, or production semantics.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from math import isfinite

from backtesting.trade_simulator import TradeSimulator
from market_data.foundation import MarketSeries
from market_data.yahoo_provider import YahooChartDailyProvider
from models.position import Position
from research.breakout_validation import BreakoutValidationSummary
from research.run_breakout_validation import (
    HISTORY_BARS,
    UNIVERSE,
    split_and_validate,
)


TARGET_R = Decimal("3")
OOS_WARMUP_BARS = 50


@dataclass(frozen=True, slots=True)
class _FloatCandle:
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True, slots=True)
class ExitTradeEvidence:
    symbol: str
    signal_time: str
    entry: float
    stop: float
    target: float
    exit_reason: str
    holding_bars: int
    pnl_1unit: float
    fees_1unit: float
    net_r: float
    gap_stop: bool
    gap_target: bool
    ambiguous_stop_target_bar: bool


@dataclass(frozen=True, slots=True)
class ExitSummary:
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
    stop_hits: int
    target_hits: int
    gap_stops: int
    gap_targets: int
    ambiguous_stop_target_bars: int


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
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def simulate_filled_observations(
    series: MarketSeries,
    summary: BreakoutValidationSummary,
) -> tuple[ExitTradeEvidence, ...]:
    simulator = TradeSimulator()
    evidence: list[ExitTradeEvidence] = []
    bars = series.bars

    for obs in summary.observations:
        if obs.status != "FILLED":
            continue
        if obs.fill_price is None or obs.fill_index is None:
            raise ValueError("FILLED observation missing fill evidence")

        entry = Decimal(obs.fill_price)
        stop = Decimal(obs.invalidation_price)
        risk = entry - stop
        if risk <= 0:
            raise ValueError("non-positive structural risk in filled BREAKOUT observation")
        target = entry + TARGET_R * risk

        source_candles = bars[obs.fill_index :]
        if not source_candles:
            raise ValueError("filled observation has no forward candles")
        candles = tuple(
            _FloatCandle(
                open=float(bar.open),
                high=float(bar.high),
                low=float(bar.low),
                close=float(bar.close),
            )
            for bar in source_candles
        )

        position = Position(
            symbol=obs.symbol,
            market="RESEARCH",
            side="LONG",
            quantity=1.0,
            entry=float(entry),
            stop_loss=float(stop),
            take_profit=float(target),
            opened_at=float(obs.fill_index),
            current_price=float(entry),
        )
        result = simulator.long(position, candles)
        exit_bar = candles[result.exit_offset]
        ambiguous = (
            exit_bar.low <= float(stop)
            and exit_bar.high >= float(target)
        )
        gap_stop = result.exit_reason == "stop" and exit_bar.open < float(stop)
        gap_target = result.exit_reason == "target" and exit_bar.open > float(target)

        net_r = result.pnl / float(risk)
        if not isfinite(net_r):
            raise ValueError("non-finite R result")

        evidence.append(
            ExitTradeEvidence(
                symbol=obs.symbol,
                signal_time=str(obs.signal_time),
                entry=float(entry),
                stop=float(stop),
                target=float(target),
                exit_reason=result.exit_reason,
                holding_bars=int(result.exit_offset),
                pnl_1unit=float(result.pnl),
                fees_1unit=float(result.fees),
                net_r=float(net_r),
                gap_stop=gap_stop,
                gap_target=gap_target,
                ambiguous_stop_target_bar=ambiguous,
            )
        )
    return tuple(evidence)


def summarize(trades: tuple[ExitTradeEvidence, ...]) -> ExitSummary:
    resolved = [t for t in trades if t.exit_reason in {"stop", "target"}]
    wins = sum(t.exit_reason == "target" for t in resolved)
    losses = sum(t.exit_reason == "stop" for t in resolved)
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
    return ExitSummary(
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
        stop_hits=losses,
        target_hits=wins,
        gap_stops=sum(t.gap_stop for t in trades),
        gap_targets=sum(t.gap_target for t in trades),
        ambiguous_stop_target_bars=sum(t.ambiguous_stop_target_bar for t in trades),
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
        ExitTradeEvidence(**trade)
        for symbol in symbols
        for trade in symbol["oos_trades"]
    )
    return {
        "hypothesis": "BREAKOUT_LONG_STRUCTURAL_STOP_FIXED_3R",
        "target_r": float(TARGET_R),
        "universe": list(UNIVERSE),
        "symbols": symbols,
        "oos_total": asdict(summarize(all_oos)),
        "notes": {
            "pnl_unit": "1-unit trade PnL; not portfolio PnL or sizing evidence",
            "drawdown_unit": "cumulative trade R; not portfolio drawdown",
            "ambiguity_policy": "existing TradeSimulator stop_first",
            "broker": "ZERO",
            "live_money": "ZERO",
        },
    }


def main() -> None:
    print(json.dumps(asyncio.run(run()), sort_keys=True))


if __name__ == "__main__":
    main()
