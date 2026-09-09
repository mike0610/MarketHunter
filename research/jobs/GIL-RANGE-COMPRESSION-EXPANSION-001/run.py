#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

OBJECT_ID = "GIL-RANGE-COMPRESSION-EXPANSION-001"
UNIVERSE = ("SPY", "QQQ", "IWM", "GLD", "TLT", "UUP", "USO", "SLV")
HISTORY_YEARS = "10y"
DEV_FRACTION = 0.70
ATR_WINDOW = 20
BASELINE_WINDOW = 100
COMPRESSION_RATIO = 0.70
COMPRESSION_STREAK = 5
ENTRY_EXPIRY = 5
MAX_HOLD = 10
FEE_BPS_PER_SIDE = 4.0
SLIPPAGE_BPS_PER_SIDE = 2.0


@dataclass(frozen=True)
class Bar:
    ts: int
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class Trade:
    symbol: str
    side: str
    signal_ts: int
    fill_ts: int
    exit_ts: int
    entry_raw: float
    entry_fill: float
    stop: float
    exit_raw: float
    exit_fill: float
    exit_reason: str
    holding_sessions: int
    gross_return: float
    net_return: float
    fees_return: float
    gap_entry: bool
    gap_stop: bool


def fetch(symbol: str) -> list[Bar]:
    quoted = urllib.parse.quote(symbol, safe="")
    q = urllib.parse.urlencode({"range": HISTORY_YEARS, "interval": "1d", "events": "history"})
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quoted}?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (MarketHunter research)"})
    with urllib.request.urlopen(req, timeout=25) as r:
        payload = json.loads(r.read().decode("utf-8"))
    chart = payload["chart"]
    if chart.get("error"):
        raise RuntimeError(f"{symbol}: {chart['error']}")
    result = chart["result"][0]
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]
    bars = []
    for i, ts in enumerate(timestamps):
        vals = [quote[k][i] for k in ("open", "high", "low", "close")]
        if any(v is None for v in vals):
            continue
        bars.append(Bar(int(ts), *(float(v) for v in vals)))
    if len(bars) < 500:
        raise RuntimeError(f"{symbol}: insufficient bars={len(bars)}")
    return bars


def true_ranges(bars: list[Bar]) -> list[float]:
    out = []
    for i, b in enumerate(bars):
        prev = bars[i - 1].close if i else b.close
        out.append(max(b.high - b.low, abs(b.high - prev), abs(b.low - prev)))
    return out


def rolling_atr20(tr: list[float]) -> list[float | None]:
    out: list[float | None] = [None] * len(tr)
    for i in range(ATR_WINDOW - 1, len(tr)):
        out[i] = sum(tr[i - ATR_WINDOW + 1:i + 1]) / ATR_WINDOW
    return out


def compression_flags(bars: list[Bar]) -> list[bool]:
    atr = rolling_atr20(true_ranges(bars))
    flags = [False] * len(bars)
    for i in range(len(bars)):
        if atr[i] is None or i < BASELINE_WINDOW:
            continue
        prior = [x for x in atr[i - BASELINE_WINDOW:i] if x is not None]
        if len(prior) != BASELINE_WINDOW:
            continue
        baseline = statistics.median(prior)
        flags[i] = bool(baseline > 0 and atr[i] <= COMPRESSION_RATIO * baseline)
    return flags


def signal_indices(bars: list[Bar]) -> list[int]:
    flags = compression_flags(bars)
    signals = []
    for i in range(COMPRESSION_STREAK - 1, len(bars)):
        if not all(flags[i - COMPRESSION_STREAK + 1:i + 1]):
            continue
        # Exactly one signal per compression episode, on the first bar
        # that reaches the frozen >=5-consecutive-bars condition.
        prior_i = i - COMPRESSION_STREAK
        if prior_i >= 0 and flags[prior_i]:
            continue
        signals.append(i)
    return signals


def adverse_entry(side: str, raw: float) -> float:
    slip = SLIPPAGE_BPS_PER_SIDE / 10000.0
    return raw * (1 + slip if side == "LONG" else 1 - slip)


def adverse_exit(side: str, raw: float) -> float:
    slip = SLIPPAGE_BPS_PER_SIDE / 10000.0
    return raw * (1 - slip if side == "LONG" else 1 + slip)


def simulate_one(
    symbol: str,
    bars: list[Bar],
    signal_i: int,
    side: str,
    end_i: int,
) -> Trade | None:
    ref = bars[signal_i - COMPRESSION_STREAK + 1:signal_i + 1]
    ref_high = max(b.high for b in ref)
    ref_low = min(b.low for b in ref)
    trigger = ref_high if side == "LONG" else ref_low
    stop = ref_low if side == "LONG" else ref_high

    fill_i = None
    entry_raw = None
    last_entry_i = min(signal_i + ENTRY_EXPIRY, end_i - 1)
    for j in range(signal_i + 1, last_entry_i + 1):
        b = bars[j]
        if side == "LONG":
            invalid = b.low <= stop
            triggered = b.high >= trigger
        else:
            invalid = b.high >= stop
            triggered = b.low <= trigger
        # Fail closed on unknown intraday sequence: invalidation wins.
        if invalid:
            return None
        if triggered:
            fill_i = j
            if side == "LONG":
                entry_raw = max(trigger, b.open)
            else:
                entry_raw = min(trigger, b.open)
            break

    if fill_i is None or entry_raw is None:
        return None

    entry_fill = adverse_entry(side, entry_raw)
    last_hold_i = min(fill_i + MAX_HOLD - 1, end_i - 1)
    exit_i = last_hold_i
    exit_reason = "time"
    exit_raw = bars[last_hold_i].close
    gap_stop = False

    for j in range(fill_i, last_hold_i + 1):
        b = bars[j]
        stop_hit = b.low <= stop if side == "LONG" else b.high >= stop
        if stop_hit:
            exit_i = j
            exit_reason = "stop"
            if side == "LONG":
                gap_stop = b.open < stop
                exit_raw = min(stop, b.open) if gap_stop else stop
            else:
                gap_stop = b.open > stop
                exit_raw = max(stop, b.open) if gap_stop else stop
            break

    exit_fill = adverse_exit(side, exit_raw)
    if side == "LONG":
        gross = (exit_fill - entry_fill) / entry_fill
    else:
        gross = (entry_fill - exit_fill) / entry_fill
    fee_rate = FEE_BPS_PER_SIDE / 10000.0
    fees = fee_rate * (1.0 + exit_fill / entry_fill)
    net = gross - fees

    return Trade(
        symbol=symbol,
        side=side,
        signal_ts=bars[signal_i].ts,
        fill_ts=bars[fill_i].ts,
        exit_ts=bars[exit_i].ts,
        entry_raw=entry_raw,
        entry_fill=entry_fill,
        stop=stop,
        exit_raw=exit_raw,
        exit_fill=exit_fill,
        exit_reason=exit_reason,
        holding_sessions=exit_i - fill_i + 1,
        gross_return=gross,
        net_return=net,
        fees_return=fees,
        gap_entry=abs(entry_raw - trigger) > 1e-12,
        gap_stop=gap_stop,
    )


def summarize(trades: list[Trade]) -> dict:
    n = len(trades)
    wins = [t.net_return for t in trades if t.net_return > 0]
    losses = [t.net_return for t in trades if t.net_return < 0]
    eq = peak = max_dd = 0.0
    for t in sorted(trades, key=lambda x: (x.signal_ts, x.symbol, x.side)):
        eq += t.net_return
        peak = max(peak, eq)
        max_dd = min(max_dd, eq - peak)
    return {
        "trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / n if n else None,
        "net_expectancy": sum(t.net_return for t in trades) / n if n else None,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "net_return_sum": sum(t.net_return for t in trades),
        "max_cumulative_drawdown": max_dd,
        "avg_holding_sessions": sum(t.holding_sessions for t in trades) / n if n else None,
        "median_holding_sessions": statistics.median([t.holding_sessions for t in trades]) if n else None,
        "stop_exits": sum(t.exit_reason == "stop" for t in trades),
        "time_exits": sum(t.exit_reason == "time" for t in trades),
        "gap_entries": sum(t.gap_entry for t in trades),
        "gap_stops": sum(t.gap_stop for t in trades),
    }


def year(ts: int) -> int:
    return datetime.fromtimestamp(ts, tz=timezone.utc).year


def validate(data: dict[str, list[Bar]]) -> dict:
    all_dev: dict[str, list[Trade]] = {"LONG": [], "SHORT": []}
    all_oos: dict[str, list[Trade]] = {"LONG": [], "SHORT": []}
    per_symbol = {}

    for symbol, bars in data.items():
        split = int(math.floor(len(bars) * DEV_FRACTION))
        if split < 250 or len(bars) - split < 100:
            raise RuntimeError(f"{symbol}: split too small")
        sigs = signal_indices(bars)
        record = {"bars": len(bars), "split_index": split, "signals": len(sigs)}
        for side in ("LONG", "SHORT"):
            dev = []
            oos = []
            for i in sigs:
                if i < split:
                    t = simulate_one(symbol, bars, i, side, split)
                    if t is not None:
                        dev.append(t)
                else:
                    t = simulate_one(symbol, bars, i, side, len(bars))
                    if t is not None:
                        oos.append(t)
            all_dev[side].extend(dev)
            all_oos[side].extend(oos)
            record[side] = {"development": summarize(dev), "oos": summarize(oos)}
        per_symbol[symbol] = record

    result = {"per_symbol": per_symbol, "sides": {}}
    for side in ("LONG", "SHORT"):
        oos = all_oos[side]
        loo_symbol = {}
        for omitted in UNIVERSE:
            subset = [t for t in oos if t.symbol != omitted]
            loo_symbol[omitted] = summarize(subset)
        years = sorted({year(t.signal_ts) for t in oos})
        loo_year = {}
        for omitted in years:
            subset = [t for t in oos if year(t.signal_ts) != omitted]
            loo_year[str(omitted)] = summarize(subset)
        result["sides"][side] = {
            "development": summarize(all_dev[side]),
            "oos": summarize(oos),
            "leave_one_symbol_out": loo_symbol,
            "leave_one_year_out": loo_year,
            "oos_trades": [asdict(t) for t in oos],
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    try:
        data = {s: fetch(s) for s in UNIVERSE}
        core1 = validate(data)
        core2 = validate(data)
        deterministic = core1 == core2
        if not deterministic:
            raise RuntimeError("deterministic rerun mismatch")

        def side_pass(side_result: dict) -> bool:
            def summary_pass(s: dict) -> bool:
                if not s["trades"] or s["net_expectancy"] is None or s["net_expectancy"] <= 0:
                    return False
                if s["losses"] == 0:
                    return s["wins"] > 0
                return s["profit_factor"] is not None and s["profit_factor"] > 1.0

            if not summary_pass(side_result["oos"]):
                return False
            if any(not summary_pass(s) for s in side_result["leave_one_symbol_out"].values()):
                return False
            if any(not summary_pass(s) for s in side_result["leave_one_year_out"].values()):
                return False
            return True

        long_pass = side_pass(core1["sides"]["LONG"])
        short_pass = side_pass(core1["sides"]["SHORT"])
        long_state = "PROMOTION" if long_pass else "REJECTED"
        short_state = "PROMOTION" if short_pass else "REJECTED"
        terminal_state = f"LONG-{long_state}__SHORT-{short_state}"

        payload = {
            "object_id": OBJECT_ID,
            "terminal_state": terminal_state,
            "executed_at_utc": datetime.now(timezone.utc).isoformat(),
            "hypothesis": "RANGE_COMPRESSION_EXPANSION_v0.1",
            "frozen_universe": list(UNIVERSE),
            "universe_rationale": "liquid executable US-listed proxies spanning equity beta, small caps, gold, rates, USD, crude oil and silver; selected before outcome inspection to avoid futures roll ambiguity",
            "parameters": {
                "atr_window": ATR_WINDOW,
                "baseline_window": BASELINE_WINDOW,
                "compression_ratio": COMPRESSION_RATIO,
                "compression_streak": COMPRESSION_STREAK,
                "entry_expiry_sessions": ENTRY_EXPIRY,
                "max_hold_sessions": MAX_HOLD,
                "fee_bps_per_side": FEE_BPS_PER_SIDE,
                "slippage_bps_per_side": SLIPPAGE_BPS_PER_SIDE,
                "ambiguity_policy": "pre-fill invalidation wins; post-fill stop first",
                "split": "chronological 70/30",
            },
            "deterministic_rerun_pass": deterministic,
            "evidence": core1,
            "boundaries": {
                "broker": "ZERO",
                "live_money": "ZERO",
                "paper_admission": "NOT_AUTHORIZED_BY_THIS_JOB",
                "terminal_verdict_owner": "GIL",
            },
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        (out / "terminal_result.json").write_bytes(raw)
        (out / "validation_pretty.json").write_text(json.dumps(payload, indent=2, sort_keys=True))
        (out / "evidence.sha256").write_text(hashlib.sha256(raw).hexdigest() + "  terminal_result.json\n")
        print("TERMINAL_STATE=" + terminal_state)
        return 0
    except Exception as exc:
        payload = {
            "object_id": OBJECT_ID,
            "terminal_state": "BLOCKED-EVIDENCE",
            "executed_at_utc": datetime.now(timezone.utc).isoformat(),
            "reason": f"{type(exc).__name__}: {exc}",
            "frozen_universe": list(UNIVERSE),
        }
        (out / "terminal_result.json").write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        print("TERMINAL_STATE=BLOCKED-EVIDENCE")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
