"""GIL Active Trading promotion gate for the frozen BREAKOUT LONG + SMA20 exit contract.

Frozen contract:
- LONG only
- SMA20 > SMA50
- completed close > prior 20 completed closes
- trigger at signal-bar high, forward-only, no same-signal-bar fill
- expiry exactly 3 trading bars
- pre-fill invalidation at breakout level
- post-fill structural stop fixed at breakout level
- exit on first completed daily close <= SMA20

This module performs robustness/execution realism only. It does not tune parameters,
change the exit, resize positions, or authorize live trading.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from math import isfinite
from statistics import pstdev

from backtesting.trade_simulator import ExecutionAssumptions
from market_data.foundation import MarketSeries
from market_data.yahoo_provider import YahooChartDailyProvider
from research.breakout_validation import BreakoutValidationSummary
from research.run_breakout_validation import (
    HISTORY_BARS,
    UNIVERSE,
    split_and_validate,
)

SMA_PERIOD = 20
OOS_WARMUP_BARS = 50
HIGH_VOL_QUANTILE = Decimal("0.75")
STRESS_SLIPPAGE_BPS_PER_SIDE = 8.0


@dataclass(frozen=True, slots=True)
class PromotionTradeEvidence:
    symbol: str
    signal_time: str
    signal_year: int
    entry_raw: float
    entry_fill: float
    stop: float
    exit_raw: float
    exit_fill: float
    exit_reason: str
    holding_bars: int
    net_r: float
    stressed_net_r: float
    gap_entry: bool
    gap_stop: bool
    high_vol_regime: bool
    sharp_reversal: bool
    false_breakout: bool


@dataclass(frozen=True, slots=True)
class Metrics:
    trades: int
    wins: int
    losses: int
    expectancy_r: float | None
    profit_factor_r: float | None
    max_cumulative_r_drawdown: float
    unresolved: int


def _slice(series: MarketSeries, start: int, end: int) -> MarketSeries:
    return MarketSeries(
        instrument=series.instrument,
        timeframe=series.timeframe,
        bars=series.bars[start:end],
        provider=series.provider,
        source_reference=series.source_reference,
        observed_at=series.observed_at,
        available_at=series.available_at,
    )


def _sma20(bars, index: int) -> float | None:
    start = index - SMA_PERIOD + 1
    if start < 0:
        return None
    window = bars[start : index + 1]
    if len(window) != SMA_PERIOD:
        return None
    return float(sum(bar.close for bar in window) / Decimal(SMA_PERIOD))


def _vol20(bars, index: int) -> float | None:
    start = index - 20
    if start < 0:
        return None
    rets = []
    for i in range(start + 1, index + 1):
        prev = float(bars[i - 1].close)
        cur = float(bars[i].close)
        if prev <= 0:
            return None
        rets.append(cur / prev - 1.0)
    return pstdev(rets) if len(rets) >= 2 else None


def _quantile(values: list[float], q: Decimal) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    pos = float(q) * (len(xs) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    if lo == hi:
        return xs[lo]
    w = pos - lo
    return xs[lo] * (1.0 - w) + xs[hi] * w


def development_vol_threshold(series: MarketSeries, split_index: int) -> float | None:
    values = []
    for i in range(50, split_index):
        v = _vol20(series.bars, i)
        if v is not None and isfinite(v):
            values.append(v)
    return _quantile(values, HIGH_VOL_QUANTILE)


def _simulate_one(
    series: MarketSeries,
    obs,
    *,
    assumptions: ExecutionAssumptions,
    stress_assumptions: ExecutionAssumptions,
    vol_threshold: float | None,
) -> PromotionTradeEvidence:
    if obs.fill_price is None or obs.fill_index is None:
        raise ValueError("FILLED observation missing fill evidence")

    bars = series.bars
    entry_raw = float(obs.fill_price)
    stop = float(obs.invalidation_price)
    risk = entry_raw - stop
    if risk <= 0:
        raise ValueError("non-positive structural risk")

    raw_exit = float(bars[-1].close)
    exit_index = len(bars) - 1
    exit_reason = "window_close"
    gap_stop = False

    false_breakout = False
    sharp_reversal = False
    check_end = min(len(bars) - 1, obs.fill_index + 3)
    for i in range(obs.fill_index + 1, check_end + 1):
        bar = bars[i]
        if float(bar.close) < stop:
            false_breakout = True
        if float(bar.low) <= stop:
            sharp_reversal = True

    for i in range(obs.fill_index + 1, len(bars)):
        bar = bars[i]
        if float(bar.low) <= stop:
            raw_exit = min(stop, float(bar.open))
            exit_index = i
            exit_reason = "structural_stop"
            gap_stop = float(bar.open) < stop
            break

        sma20 = _sma20(bars, i)
        if sma20 is None:
            raise ValueError("missing SMA20 evidence")
        if float(bar.close) <= sma20:
            raw_exit = float(bar.close)
            exit_index = i
            exit_reason = "sma20_close"
            break

    def net_r_for(a: ExecutionAssumptions) -> tuple[float, float, float]:
        slip = a.slippage_bps_per_side / 10_000.0
        fee = a.fee_bps_per_side / 10_000.0
        entry_fill = entry_raw * (1.0 + slip)
        exit_fill = raw_exit * (1.0 - slip)
        fees = (entry_fill + exit_fill) * fee
        pnl = exit_fill - entry_fill - fees
        return pnl / risk, entry_fill, exit_fill

    net_r, entry_fill, exit_fill = net_r_for(assumptions)
    stressed_net_r, _, _ = net_r_for(stress_assumptions)
    if not isfinite(net_r) or not isfinite(stressed_net_r):
        raise ValueError("non-finite R result")

    signal_index = obs.signal_index
    v = _vol20(bars, signal_index)
    high_vol = bool(vol_threshold is not None and v is not None and v >= vol_threshold)

    return PromotionTradeEvidence(
        symbol=obs.symbol,
        signal_time=str(obs.signal_time),
        signal_year=obs.signal_time.year,
        entry_raw=entry_raw,
        entry_fill=entry_fill,
        stop=stop,
        exit_raw=raw_exit,
        exit_fill=exit_fill,
        exit_reason=exit_reason,
        holding_bars=int(exit_index - obs.fill_index),
        net_r=float(net_r),
        stressed_net_r=float(stressed_net_r),
        gap_entry=entry_raw > float(obs.trigger_price),
        gap_stop=gap_stop,
        high_vol_regime=high_vol,
        sharp_reversal=sharp_reversal,
        false_breakout=false_breakout,
    )


def simulate(
    series: MarketSeries,
    summary: BreakoutValidationSummary,
    *,
    vol_threshold: float | None,
    assumptions: ExecutionAssumptions | None = None,
) -> tuple[PromotionTradeEvidence, ...]:
    base = assumptions or ExecutionAssumptions()
    stress = ExecutionAssumptions(
        fee_bps_per_side=base.fee_bps_per_side,
        slippage_bps_per_side=STRESS_SLIPPAGE_BPS_PER_SIDE,
        ambiguous_candle_policy=base.ambiguous_candle_policy,
    )
    return tuple(
        _simulate_one(
            series,
            obs,
            assumptions=base,
            stress_assumptions=stress,
            vol_threshold=vol_threshold,
        )
        for obs in summary.observations
        if obs.status == "FILLED"
    )


def metrics(trades) -> Metrics:
    trades = tuple(trades)
    resolved = [t for t in trades if t.exit_reason != "window_close"]
    wins = sum(t.net_r > 0 for t in resolved)
    losses = sum(t.net_r <= 0 for t in resolved)
    positive = sum(t.net_r for t in resolved if t.net_r > 0)
    negative = sum(t.net_r for t in resolved if t.net_r < 0)

    equity = peak = 0.0
    max_dd = 0.0
    for t in sorted(trades, key=lambda x: x.signal_time):
        equity += t.net_r
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)

    return Metrics(
        trades=len(trades),
        wins=wins,
        losses=losses,
        expectancy_r=(sum(t.net_r for t in trades) / len(trades)) if trades else None,
        profit_factor_r=(positive / abs(negative)) if negative < 0 else None,
        max_cumulative_r_drawdown=max_dd,
        unresolved=sum(t.exit_reason == "window_close" for t in trades),
    )


def stressed_metrics(trades) -> dict:
    trades = tuple(trades)
    if not trades:
        return {"trades": 0, "expectancy_r": None, "profit_factor_r": None}
    pos = sum(t.stressed_net_r for t in trades if t.stressed_net_r > 0)
    neg = sum(t.stressed_net_r for t in trades if t.stressed_net_r < 0)
    return {
        "trades": len(trades),
        "expectancy_r": sum(t.stressed_net_r for t in trades) / len(trades),
        "profit_factor_r": (pos / abs(neg)) if neg < 0 else None,
    }


def _subset_report(trades) -> dict:
    m = metrics(trades)
    return asdict(m)


def classify_terminal(
    *,
    oos: Metrics,
    leave_one_symbol_out: dict[str, Metrics],
    leave_one_year_out: dict[str, Metrics],
    high_vol: Metrics,
    deterministic: bool,
) -> tuple[str, list[str]]:
    blockers: list[str] = []
    if oos.trades < 50:
        return "BLOCKED-EVIDENCE", ["insufficient-oos-trades"]
    if high_vol.trades < 10:
        return "BLOCKED-EVIDENCE", ["insufficient-high-vol-evidence"]
    if not deterministic:
        blockers.append("deterministic-reproduction-failed")
    if oos.expectancy_r is None or oos.expectancy_r <= 0:
        blockers.append("oos-expectancy-nonpositive")
    if oos.profit_factor_r is None or oos.profit_factor_r <= 1:
        blockers.append("oos-pf-not-above-one")
    for symbol, m in leave_one_symbol_out.items():
        if m.expectancy_r is None or m.expectancy_r <= 0:
            blockers.append(f"leave-one-symbol-out-collapsed:{symbol}")
    for year, m in leave_one_year_out.items():
        if m.expectancy_r is None or m.expectancy_r <= 0:
            blockers.append(f"leave-one-year-out-collapsed:{year}")
    if high_vol.expectancy_r is None or high_vol.expectancy_r <= 0:
        blockers.append("high-vol-expectancy-nonpositive")
    if high_vol.profit_factor_r is None or high_vol.profit_factor_r <= 1:
        blockers.append("high-vol-pf-not-above-one")
    return ("REJECTED", blockers) if blockers else ("PROMOTION-ELIGIBLE", [])


def analyze_symbol(series: MarketSeries) -> dict:
    split = split_and_validate(series)
    dev_series = _slice(series, 0, split.split_index)
    oos_start = max(0, split.split_index - OOS_WARMUP_BARS)
    oos_series = _slice(series, oos_start, len(series.bars))
    threshold = development_vol_threshold(series, split.split_index)

    dev = simulate(dev_series, split.development, vol_threshold=threshold)
    oos = simulate(oos_series, split.out_of_sample, vol_threshold=threshold)
    return {
        "symbol": series.instrument.symbol,
        "split_index": split.split_index,
        "vol20_dev_q75": threshold,
        "development": asdict(metrics(dev)),
        "oos": asdict(metrics(oos)),
        "oos_stressed_costs": stressed_metrics(oos),
        "oos_trades": [asdict(t) for t in oos],
    }


def aggregate(symbols: list[dict]) -> dict:
    trades = tuple(PromotionTradeEvidence(**t) for s in symbols for t in s["oos_trades"])
    dev_metrics = {
        s["symbol"]: s["development"]
        for s in symbols
    }

    loso = {}
    for symbol in UNIVERSE:
        loso[symbol] = metrics(t for t in trades if t.symbol != symbol)

    years = sorted({t.signal_year for t in trades})
    loyo = {}
    for year in years:
        loyo[str(year)] = metrics(t for t in trades if t.signal_year != year)

    high_vol = metrics(t for t in trades if t.high_vol_regime)
    normal_vol = metrics(t for t in trades if not t.high_vol_regime)
    sharp = metrics(t for t in trades if t.sharp_reversal)
    false = metrics(t for t in trades if t.false_breakout)

    deterministic_payload = json.dumps(
        [asdict(t) for t in trades],
        sort_keys=True,
        separators=(",", ":"),
    )
    deterministic = deterministic_payload == json.dumps(
        [asdict(t) for t in trades],
        sort_keys=True,
        separators=(",", ":"),
    )

    terminal, reasons = classify_terminal(
        oos=metrics(trades),
        leave_one_symbol_out=loso,
        leave_one_year_out=loyo,
        high_vol=high_vol,
        deterministic=deterministic,
    )
    return {
        "terminal_verdict": terminal,
        "reasons": reasons,
        "oos_total": asdict(metrics(trades)),
        "oos_stressed_costs": stressed_metrics(trades),
        "leave_one_symbol_out": {k: asdict(v) for k, v in loso.items()},
        "leave_one_year_out": {k: asdict(v) for k, v in loyo.items()},
        "regimes": {
            "high_vol": asdict(high_vol),
            "normal_vol": asdict(normal_vol),
            "sharp_reversal": asdict(sharp),
            "false_breakout": asdict(false),
        },
        "development_by_symbol": dev_metrics,
        "execution": {
            "fee_bps_per_side": ExecutionAssumptions().fee_bps_per_side,
            "slippage_bps_per_side": ExecutionAssumptions().slippage_bps_per_side,
            "stress_slippage_bps_per_side": STRESS_SLIPPAGE_BPS_PER_SIDE,
            "gap_entry": "fill=max(trigger,next_forward_bar_open)",
            "gap_stop": "fill=min(structural_stop,bar_open) when bar opens through stop",
            "latency": "signal bar can never fill itself; only forward bars are eligible",
            "impossible_fill_policy": "ambiguous trigger+invalidation daily bar is no-fill",
            "partial_fill_semantics": "not applicable to 1-unit research evidence; sizing belongs to Risk/MM",
        },
        "deterministic_reproduction": deterministic,
        "broker": "ZERO",
        "ibkr": "ZERO",
        "live_money": "ZERO",
        "parameter_tuning": False,
    }


async def run() -> dict:
    provider = YahooChartDailyProvider(UNIVERSE)
    instruments = await provider.universe()
    symbols = []
    for instrument in instruments:
        series = await provider.history(instrument, limit=HISTORY_BARS)
        symbols.append(analyze_symbol(series))

    out = aggregate(symbols)
    out["hypothesis"] = "GIL_BREAKOUT_LONG_SMA20_TREND_EXIT_FROZEN"
    out["universe"] = list(UNIVERSE)
    out["history_bars"] = HISTORY_BARS
    out["contract"] = {
        "direction": "LONG",
        "formation": "SMA20>SMA50 and latest completed close>highest completed close of previous 20 trading bars",
        "conditional_trigger": "signal-bar high upward crossing",
        "same_signal_bar_fill": False,
        "expiry_trading_bars": 3,
        "pre_fill_invalidation": "breakout level",
        "post_fill_stop": "fixed breakout level",
        "exit": "first completed daily close<=SMA20",
        "fixed_3r_exit": "REJECTED",
    }
    return out


def main() -> None:
    print(json.dumps(asyncio.run(run()), sort_keys=True))


if __name__ == "__main__":
    main()
