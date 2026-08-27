import json, math, sys, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

OBJECT_ID = "SL-VAL-RISK-014"
SYMBOL = "BTCUSDT"
INTERVAL = "1h"
START_MS = 1640995200000  # 2022-01-01T00:00:00Z
END_MS = 1669075200000    # 2022-11-22T00:00:00Z exclusive
EXPECTED_ROWS = 7800
KNOWN_SPOT_DAILY_CLOSE_MAX_DD = -0.6693


def emit(outdir, state, payload):
    p = Path(outdir)
    p.mkdir(parents=True, exist_ok=True)
    result = {
        "object_id": OBJECT_ID,
        "terminal_state": state,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    (p / "terminal_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )


def fetch_mark_klines():
    rows = []
    cur = START_MS
    while cur < END_MS:
        q = urllib.parse.urlencode(
            {
                "symbol": SYMBOL,
                "interval": INTERVAL,
                "startTime": cur,
                "endTime": END_MS - 1,
                "limit": 1500,
            }
        )
        url = "https://fapi.binance.com/fapi/v1/markPriceKlines?" + q
        with urllib.request.urlopen(url, timeout=20) as r:
            batch = json.loads(r.read().decode())
        if not batch:
            break
        rows.extend(batch)
        nxt = int(batch[-1][0]) + 3600000
        if nxt <= cur:
            raise RuntimeError("non-advancing provider cursor")
        cur = nxt
    return rows


def max_drawdown_from_closes(closes):
    peak = closes[0]
    max_dd = 0.0
    peak_i = 0
    trough_i = 0
    current_peak_i = 0
    for i, px in enumerate(closes):
        if px > peak:
            peak = px
            current_peak_i = i
        dd = px / peak - 1.0
        if dd < max_dd:
            max_dd = dd
            peak_i = current_peak_i
            trough_i = i
    return max_dd, peak_i, trough_i


def max_intrabar_low_drawdown(opens, highs, lows, closes):
    peak = opens[0]
    peak_i = 0
    max_dd = 0.0
    dd_peak_i = 0
    dd_trough_i = 0
    for i in range(len(closes)):
        # Information/order within an OHLC bar is unknown. Use prior confirmed peak plus current bar open/high
        # only as a descriptive path bound, not as executable sequencing.
        candidate_peak = max(peak, opens[i], highs[i])
        candidate_peak_i = i if candidate_peak > peak else peak_i
        dd = lows[i] / candidate_peak - 1.0
        if dd < max_dd:
            max_dd = dd
            dd_peak_i = candidate_peak_i
            dd_trough_i = i
        if highs[i] > peak:
            peak = highs[i]
            peak_i = i
        if closes[i] > peak:
            peak = closes[i]
            peak_i = i
    return max_dd, dd_peak_i, dd_trough_i


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat()


def main(outdir):
    try:
        rows = fetch_mark_klines()
    except Exception as e:
        emit(outdir, "BLOCKED-PROVIDER", {"reason": repr(e)})
        return

    opens_ms = [int(r[0]) for r in rows]
    if (
        len(rows) != EXPECTED_ROWS
        or len(set(opens_ms)) != len(opens_ms)
        or (opens_ms and opens_ms[0] != START_MS)
        or (opens_ms and opens_ms[-1] != END_MS - 3600000)
        or any(b - a != 3600000 for a, b in zip(opens_ms, opens_ms[1:]))
    ):
        emit(
            outdir,
            "DATA-INTEGRITY-FAIL",
            {
                "row_count": len(rows),
                "expected_rows": EXPECTED_ROWS,
                "first_open": opens_ms[0] if opens_ms else None,
                "last_open": opens_ms[-1] if opens_ms else None,
            },
        )
        return

    opens = [float(r[1]) for r in rows]
    highs = [float(r[2]) for r in rows]
    lows = [float(r[3]) for r in rows]
    closes = [float(r[4]) for r in rows]
    if any(
        (not math.isfinite(x) or x <= 0)
        for series in (opens, highs, lows, closes)
        for x in series
    ):
        emit(outdir, "DATA-INTEGRITY-FAIL", {"reason": "non-positive-or-non-finite-price"})
        return

    # Daily close proxy from the same mark-price source: close of each 23:00 UTC hourly bucket.
    daily_indices = [i for i, t in enumerate(opens_ms) if datetime.fromtimestamp(t / 1000, timezone.utc).hour == 23]
    daily_closes = [closes[i] for i in daily_indices]
    if len(daily_closes) != EXPECTED_ROWS // 24:
        emit(outdir, "DATA-INTEGRITY-FAIL", {"reason": "daily-close-proxy-count", "count": len(daily_closes)})
        return

    hourly_close_dd, hc_peak_i, hc_trough_i = max_drawdown_from_closes(closes)
    daily_close_dd, dc_peak_j, dc_trough_j = max_drawdown_from_closes(daily_closes)
    intrabar_low_dd, il_peak_i, il_trough_i = max_intrabar_low_drawdown(opens, highs, lows, closes)

    dc_peak_i = daily_indices[dc_peak_j]
    dc_trough_i = daily_indices[dc_trough_j]

    emit(
        outdir,
        "MARK-PATH-RESULT",
        {
            "contract": {
                "symbol": SYMBOL,
                "venue_surface": "Binance USD-M Futures markPriceKlines",
                "interval": INTERVAL,
                "start_utc": iso(START_MS),
                "end_utc_exclusive": iso(END_MS),
                "purpose": "measure intraday mark-price adverse excursion inside the already-frozen worst daily-close drawdown episode",
                "no_leverage_selection": True,
                "no_liquidation_inference": True,
            },
            "integrity": {
                "row_count": len(rows),
                "expected_rows": EXPECTED_ROWS,
                "first_open_utc": iso(opens_ms[0]),
                "last_open_utc": iso(opens_ms[-1]),
                "unique_monotonic_hourly": True,
                "daily_close_proxy_count": len(daily_closes),
            },
            "results": {
                "mark_hourly_close_max_drawdown": hourly_close_dd,
                "mark_hourly_close_peak_open_utc": iso(opens_ms[hc_peak_i]),
                "mark_hourly_close_trough_open_utc": iso(opens_ms[hc_trough_i]),
                "mark_daily_close_proxy_max_drawdown": daily_close_dd,
                "mark_daily_close_proxy_peak_open_utc": iso(opens_ms[dc_peak_i]),
                "mark_daily_close_proxy_trough_open_utc": iso(opens_ms[dc_trough_i]),
                "mark_intrabar_low_max_drawdown_bound": intrabar_low_dd,
                "mark_intrabar_peak_bucket_open_utc": iso(opens_ms[il_peak_i]),
                "mark_intrabar_trough_bucket_open_utc": iso(opens_ms[il_trough_i]),
                "intraday_minus_mark_daily_close_dd": intrabar_low_dd - daily_close_dd,
                "known_spot_daily_close_max_dd_reference": KNOWN_SPOT_DAILY_CLOSE_MAX_DD,
            },
            "interpretation_guardrails": [
                "The Binance USD-M mark-price path is not the Binance Spot close series used by the earlier controller test; cross-surface differences must not be attributed solely to intraday sampling.",
                "OHLC does not reveal within-bar event order; the intrabar-low statistic is a descriptive adverse-excursion bound, not an executable liquidation replay.",
                "No historical leverage bracket, maintenance-margin, funding, fee, slippage, fill or account-state inference is made.",
                "This result can falsify the adequacy of close-to-close drawdown as a complete path-risk descriptor, but cannot establish liquidation probability or live leverage headroom.",
            ],
        },
    )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
