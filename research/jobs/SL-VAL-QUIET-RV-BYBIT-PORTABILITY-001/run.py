"""
SL-VAL-QUIET-RV-BYBIT-PORTABILITY-001

Cross-venue PRICE portability check for the frozen Quiet-RV signal
(parent object: SL-VAL-QUIET-RV-001). The exact frozen signal rule,
8-asset universe, and parameters are copied unchanged from the parent
job's own run.py. Only the price source changes: Binance Spot monthly
klines (the parent's own source) versus Bybit USDT linear-perpetual
public klines (price only - no funding rate, no open interest, no
account/order endpoint anywhere in this script).

Self-contained, stdlib-only, matching every other frozen job in this
harness - this script is shipped to the VPS on its own and must not
import anything from the wider MarketHunter repository.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import time
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

OBJECT_ID = 'SL-VAL-QUIET-RV-BYBIT-PORTABILITY-001'
ASSETS = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT', 'XRPUSDT', 'DOGEUSDT', 'LINKUSDT', 'LTCUSDT']
TF = '4h'
INTERVAL_MS = 4 * 3600 * 1000
BYBIT_INTERVAL = '240'  # Bybit's own vocabulary for 4h

WARM = datetime(2022, 1, 1, tzinfo=timezone.utc)
START = datetime(2022, 7, 1, tzinfo=timezone.utc)
SPLIT = datetime(2025, 1, 1, tzinfo=timezone.utc)
END = datetime(2026, 8, 1, tzinfo=timezone.utc)

# Exact frozen Quiet-RV parameters - copied unchanged from SL-VAL-QUIET-RV-001/run.py.
VOL_WIN, VOL_LOOK, VOL_Q = 42, 540, .30
DEV_WIN, DEV_LOOK, DEV_Q = 42, 540, .90
HOLD, DECLUSTER = 6, 6
COST, COST_STRESS = .001, .002

# Stay well inside the harness's 20-minute hard cap so a slow network
# produces an honest partial result instead of a silent hard kill with
# zero evidence.
SOFT_DEADLINE_SECONDS = 16 * 60


def emit(out, state, **extra):
    p = Path(out)
    p.mkdir(parents=True, exist_ok=True)
    (p / 'terminal_result.json').write_text(
        json.dumps({'object_id': OBJECT_ID, 'terminal_state': state, **extra}, indent=2, sort_keys=True, default=str)
    )


def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={'User-Agent': 'MarketHunter-Research/1.0'})
    return urllib.request.urlopen(req, timeout=timeout).read()


def check_deadline(deadline, stage):
    if time.monotonic() > deadline:
        raise TimeoutError(f'soft deadline exceeded during {stage}')


# ---------------------------------------------------------------- Binance
def binance_month(symbol, year, month):
    base = f'https://data.binance.vision/data/spot/monthly/klines/{symbol}/{TF}'
    name = f'{symbol}-{TF}-{year}-{month:02d}.zip'
    url = f'{base}/{name}'
    blob = http_get(url)
    expected = http_get(url + '.CHECKSUM').decode().split()[0].lower()
    actual = hashlib.sha256(blob).hexdigest()
    if expected != actual:
        raise ValueError(f'checksum mismatch {name}')
    rows = []
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        inner = [n for n in zf.namelist() if not n.endswith('/')][0]
        for parts in csv.reader(io.TextIOWrapper(zf.open(inner))):
            try:
                raw_ts = int(parts[0])
                open_px, close_px = float(parts[1]), float(parts[4])
            except (ValueError, IndexError):
                continue
            ts = int(raw_ts / 1e6 if raw_ts > 10 ** 14 else raw_ts / 1e3)
            rows.append((ts, open_px, close_px))
    return rows, {'symbol': symbol, 'venue': 'BINANCE', 'url': url, 'sha256': actual, 'rows': len(rows)}


def fetch_binance_asset(symbol, deadline):
    data = {}
    files = []
    y, m = WARM.year, WARM.month
    while datetime(y, m, 1, tzinfo=timezone.utc) < END:
        check_deadline(deadline, f'binance fetch {symbol} {y}-{m:02d}')
        rows, meta = binance_month(symbol, y, m)
        for ts, o, c in rows:
            data[ts] = (o, c)
        files.append(meta)
        m += 1
        if m > 12:
            m = 1
            y += 1
    return data, files


# ------------------------------------------------------------------ Bybit
def bybit_page(symbol, start_ms, end_ms, limit=1000):
    url = (
        'https://api.bybit.com/v5/market/kline'
        f'?category=linear&symbol={symbol}&interval={BYBIT_INTERVAL}'
        f'&start={start_ms}&end={end_ms}&limit={limit}'
    )
    payload = json.loads(http_get(url))
    if payload.get('retCode') != 0:
        raise ValueError(f'bybit retCode={payload.get("retCode")} retMsg={payload.get("retMsg")} symbol={symbol}')
    result = payload.get('result') or {}
    return result.get('list') or []


def fetch_bybit_asset(symbol, start_ms, end_ms, deadline):
    data = {}
    cursor_end = end_ms
    seen_min = None
    for _ in range(2000):  # generous safety cap, far above what the real range needs
        check_deadline(deadline, f'bybit fetch {symbol}')
        if cursor_end <= start_ms:
            break
        batch = bybit_page(symbol, start_ms, cursor_end)
        if not batch:
            break
        batch_min = None
        for row in batch:
            ts = int(row[0])
            open_px, close_px = float(row[1]), float(row[4])
            data[ts] = (open_px, close_px)
            if batch_min is None or ts < batch_min:
                batch_min = ts
        if seen_min is not None and batch_min >= seen_min:
            break  # no forward progress - stop rather than loop forever
        seen_min = batch_min
        cursor_end = batch_min - 1
    return data


# ------------------------------------------------------------- Diagnostics
def gaps_and_duplicates(sorted_ts):
    dup, gaps = [], []
    for prev, cur in zip(sorted_ts, sorted_ts[1:]):
        delta = cur - prev
        if delta == 0:
            dup.append(cur)
        elif delta > INTERVAL_MS // 1000:
            gaps.append([prev, cur])
    return dup, gaps


# ------------------------------------------------------------------- Stats
def qtl(values, q):
    s = sorted(values)
    x = (len(s) - 1) * q
    lo, hi = int(math.floor(x)), int(math.ceil(x))
    return s[lo] if lo == hi else s[lo] * (hi - x) + s[hi] * (x - lo)


def stdev(values):
    m = sum(values) / len(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / len(values))


def stats(returns):
    if not returns:
        return {'n': 0, 'mean': None, 'median': None, 'hit': None, 'pf': None, 'cum': None, 'max_dd': None}
    s = sorted(returns)
    median = s[len(s) // 2] if len(s) % 2 else (s[len(s) // 2 - 1] + s[len(s) // 2]) / 2
    gains = sum(r for r in returns if r > 0)
    losses = -sum(r for r in returns if r < 0)
    eq = peak = 1.0
    dd = 0.0
    for r in returns:
        eq *= 1 + r
        peak = max(peak, eq)
        dd = min(dd, eq / peak - 1)
    return {
        'n': len(returns), 'mean': sum(returns) / len(returns), 'median': median,
        'hit': sum(r > 0 for r in returns) / len(returns),
        'pf': gains / losses if losses else None,
        'cum': eq - 1, 'max_dd': dd,
    }


# ------------------------------------------------------------------ Signal
def run_signal(common_ts, data):
    """Exact frozen Quiet-RV rule, unchanged, applied to whichever venue's
    `data` (asset -> {ts: (open, close)}) is passed in, over `common_ts`
    (ascending, shared across venues for a fair comparison)."""
    n = len(common_ts)
    close_series = {s: [data[s][t][1] for t in common_ts] for s in ASSETS}
    ret = {s: [None] + [math.log(close_series[s][i] / close_series[s][i - 1]) for i in range(1, n)] for s in ASSETS}
    market = [None] + [sum(ret[s][i] for s in ASSETS) / len(ASSETS) for i in range(1, n)]
    rv = [None] * n
    dev = {s: [None] * n for s in ASSETS}
    for i in range(VOL_WIN + 1, n):
        rv[i] = stdev(market[i - VOL_WIN + 1:i + 1])
        for s in ASSETS:
            dev[s][i] = sum(ret[s][j] - market[j] for j in range(i - DEV_WIN + 1, i + 1))
    events = []
    last = -10 ** 9
    floor_i = max(VOL_LOOK, DEV_LOOK) + VOL_WIN + 1
    for i in range(floor_i, n - HOLD - 1):
        ts = common_ts[i]
        if ts < int(START.timestamp()) or ts >= int(END.timestamp()) or i - last < DECLUSTER:
            continue
        vol_hist = [x for x in rv[i - VOL_LOOK:i] if x is not None]
        if not vol_hist or rv[i] > qtl(vol_hist, VOL_Q):
            continue
        dev_hist = [abs(dev[s][j]) for j in range(i - DEV_LOOK, i) for s in ASSETS if dev[s][j] is not None]
        if not dev_hist:
            continue
        threshold = qtl(dev_hist, DEV_Q)
        candidate = max(ASSETS, key=lambda s: abs(dev[s][i]))
        if abs(dev[candidate][i]) <= threshold:
            continue
        side = 'SHORT' if dev[candidate][i] > 0 else 'LONG'
        entry = data[candidate][common_ts[i + 1]][0]
        exit_ = data[candidate][common_ts[i + HOLD]][0]
        gross = exit_ / entry - 1 if side == 'LONG' else entry / exit_ - 1
        events.append({
            'ts': ts, 'asset': candidate, 'side': side,
            'net10': gross - COST, 'net20': gross - COST_STRESS,
            'period': 'IS' if ts < int(SPLIT.timestamp()) else 'OOS',
        })
        last = i
    return events


def event_key(e):
    return (e['ts'], e['asset'], e['side'])


def main(out, job_path):
    deadline = time.monotonic() + SOFT_DEADLINE_SECONDS
    try:
        if json.loads(Path(job_path).read_text()).get('object_id') != OBJECT_ID:
            raise ValueError('object id mismatch')
    except Exception as e:
        emit(out, 'PROVIDER-BLOCKED', reason=repr(e), parameter_tuning=False)
        return

    # --- Binance: single try/except, matching parent job's own convention
    # (a source already proven reliable here - any failure is a genuine
    # provider block, not an expected portability finding).
    try:
        binance_data = {}
        binance_files = []
        for s in ASSETS:
            d, files = fetch_binance_asset(s, deadline)
            binance_data[s] = d
            binance_files += files
    except Exception as e:
        emit(out, 'PROVIDER-BLOCKED', reason=f'binance: {e!r}', parameter_tuning=False)
        return

    # --- Bybit: per-symbol, since a missing/unlisted perpetual for one
    # asset is itself a real portability finding, not a system fault -
    # never silently dropped, always reported by name.
    bybit_data = {}
    bybit_errors = {}
    start_ms = int(WARM.timestamp() * 1000)
    end_ms = int(END.timestamp() * 1000)
    try:
        for s in ASSETS:
            try:
                bybit_data[s] = fetch_bybit_asset(s, start_ms, end_ms, deadline)
            except TimeoutError:
                raise
            except Exception as e:
                bybit_errors[s] = repr(e)
    except TimeoutError as e:
        emit(
            out, 'PROVIDER-BLOCKED', reason=f'bybit soft-deadline: {e!r}',
            bybit_symbols_fetched_before_timeout=sorted(bybit_data), parameter_tuning=False,
        )
        return

    # --- Per-asset, per-venue gap/duplicate diagnostics on native (non-
    # intersected) timestamps - required evidence regardless of whether
    # the cross-venue signal comparison can run at all.
    diagnostics = {}
    for s in ASSETS:
        b_ts = sorted(binance_data.get(s, {}))
        y_ts = sorted(bybit_data.get(s, {}))
        b_dup, b_gaps = gaps_and_duplicates(b_ts)
        y_dup, y_gaps = gaps_and_duplicates(y_ts)
        diagnostics[s] = {
            'binance_rows': len(b_ts),
            'binance_duplicate_count': len(b_dup),
            'binance_gap_count': len(b_gaps),
            'binance_first_ts': b_ts[0] if b_ts else None,
            'binance_last_ts': b_ts[-1] if b_ts else None,
            'bybit_rows': len(y_ts),
            'bybit_duplicate_count': len(y_dup),
            'bybit_gap_count': len(y_gaps),
            'bybit_first_ts': y_ts[0] if y_ts else None,
            'bybit_last_ts': y_ts[-1] if y_ts else None,
            'bybit_fetch_error': bybit_errors.get(s),
        }

    missing_on_bybit = [s for s in ASSETS if not bybit_data.get(s)]
    if missing_on_bybit:
        emit(
            out, 'OUTCOME-COMPLETE',
            portability_verdict='INCONCLUSIVE',
            portability_verdict_reason=f'bybit has no usable data for {missing_on_bybit} - the frozen signal is an '
                                        f'{len(ASSETS)}-asset basket and cannot be computed on a partial universe '
                                        f'without changing the frozen rule, which this job will not do',
            asset_diagnostics=diagnostics,
            bybit_errors=bybit_errors,
            source_files_binance=binance_files,
            parameter_tuning=False,
        )
        return

    # --- Fair comparison window: identical bar set for both venues, so
    # only the price source differs, never the coverage window.
    binance_common = set.intersection(*[set(binance_data[s]) for s in ASSETS])
    bybit_common = set.intersection(*[set(bybit_data[s]) for s in ASSETS])
    both_common = sorted(binance_common & bybit_common)

    if len(both_common) < max(VOL_LOOK, DEV_LOOK) + VOL_WIN + HOLD + 2:
        emit(
            out, 'OUTCOME-COMPLETE',
            portability_verdict='INCONCLUSIVE',
            portability_verdict_reason=f'only {len(both_common)} bars overlap across all 8 assets on both venues - '
                                        f'below the frozen signal\'s own lookback+hold requirement, so no event can '
                                        f'be generated on either venue over the common window',
            asset_diagnostics=diagnostics,
            bybit_errors=bybit_errors,
            source_files_binance=binance_files,
            parameter_tuning=False,
        )
        return

    binance_events = run_signal(both_common, binance_data)
    bybit_events = run_signal(both_common, bybit_data)

    binance_oos = [e for e in binance_events if e['period'] == 'OOS']
    bybit_oos = [e for e in bybit_events if e['period'] == 'OOS']

    binance_keys = {event_key(e) for e in binance_oos}
    bybit_keys = {event_key(e) for e in bybit_oos}
    overlap = binance_keys & bybit_keys
    union = binance_keys | bybit_keys
    overlap_ratio = len(overlap) / len(union) if union else None

    def gate_verdict(oos_events):
        r10 = [e['net10'] for e in oos_events]
        r20 = [e['net20'] for e in oos_events]
        s10, s20 = stats(r10), stats(r20)
        wins = sorted([x for x in r10 if x > 0], reverse=True)
        top = wins[0] / sum(wins) if wins and sum(wins) > 0 else None
        if s10['n'] < 30:
            v = 'BLOCKED-EVIDENCE'
        elif s10['mean'] > 0 and (s10['pf'] or 0) > 1 and s20['mean'] > 0 and (top is None or top < .5):
            v = 'CANDIDATE'
        else:
            v = 'REJECTED'
        return s10, s20, top, v

    binance_s10, binance_s20, binance_top, binance_gate = gate_verdict(binance_oos)
    bybit_s10, bybit_s20, bybit_top, bybit_gate = gate_verdict(bybit_oos)

    if bybit_gate == 'BLOCKED-EVIDENCE':
        portability_verdict = 'INCONCLUSIVE'
        reason = f'only {bybit_s10["n"]} Bybit-sourced OOS events on the common window (<30 required by the frozen gate)'
    elif bybit_gate == 'CANDIDATE' and (overlap_ratio or 0) >= .70:
        portability_verdict = 'VENUE-PORTABLE'
        reason = f'Bybit-sourced OOS stats pass the identical frozen gate and event overlap with Binance is {overlap_ratio:.0%}'
    elif binance_gate == 'CANDIDATE' and bybit_gate != 'CANDIDATE':
        portability_verdict = 'BINANCE-SPECIFIC-CANDIDATE'
        reason = 'Binance-sourced OOS stats pass the frozen gate on the common window; Bybit-sourced stats do not'
    else:
        portability_verdict = 'INCONCLUSIVE'
        reason = f'neither venue-specific pattern applies cleanly (binance_gate={binance_gate}, bybit_gate={bybit_gate}, event_overlap={overlap_ratio})'

    emit(
        out, 'OUTCOME-COMPLETE',
        contract={
            'assets': ASSETS, 'tf': TF, 'common_window_bars': len(both_common),
            'common_window_first_ts': both_common[0], 'common_window_last_ts': both_common[-1],
            'split': SPLIT.date().isoformat(), 'parameter_tuning': False,
        },
        asset_diagnostics=diagnostics,
        bybit_errors=bybit_errors,
        binance_oos_stats_10bps=binance_s10, binance_oos_stats_20bps=binance_s20,
        binance_oos_top_positive_trade_share=binance_top, binance_gate_verdict=binance_gate,
        binance_event_count=len(binance_events),
        bybit_oos_stats_10bps=bybit_s10, bybit_oos_stats_20bps=bybit_s20,
        bybit_oos_top_positive_trade_share=bybit_top, bybit_gate_verdict=bybit_gate,
        bybit_event_count=len(bybit_events),
        oos_event_overlap_ratio=overlap_ratio,
        oos_event_overlap_count=len(overlap), oos_event_union_count=len(union),
        portability_verdict=portability_verdict,
        portability_verdict_reason=reason,
        source_files_binance=binance_files,
        limitations=[
            'entry/exit use each bar\'s open price, exactly as the frozen parent rule does',
            'comparison window is the intersection of both venues\' full-universe coverage - a late Bybit '
            'listing for any one asset shrinks the common window for all 8, honestly, not silently',
            'Bybit category=linear (USDT perpetual) is the closest Bybit venue equivalent to a continuously '
            'tradeable price series; this is a price-only comparison, funding/OI are not requested or used',
            'no parameter, asset, threshold, holding-period, or cost change from the frozen parent rule',
        ],
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    main(args.output, args.job)
