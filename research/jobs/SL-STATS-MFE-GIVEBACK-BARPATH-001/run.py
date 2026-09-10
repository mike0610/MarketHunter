import argparse
import hashlib
import json
import math
import subprocess
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OBJECT_ID = 'SL-STATS-MFE-GIVEBACK-BARPATH-001'
REPO = '/home/ubuntu/MarketHunter'
SNAP = 'data/outcome_intelligence/latest/trades.json'
SNAP_BRANCH = 'outcome-intelligence-snapshots'
MFE_MIN = 2.0
MIN_PRIMARY_N = 100
MIN_TIMESTAMP_COVERAGE = 0.80
MIN_FETCH_COVERAGE = 0.90
MIN_EXTREMA_MATCH_RATE = 0.90
EXTREMA_TOLERANCE_PP = 0.25
MAX_GAP_MULTIPLIER = 1.5
REQUEST_TIMEOUT_SECONDS = 20

INTERVAL_MS = {
    '1m': 60_000, '3m': 180_000, '5m': 300_000, '15m': 900_000,
    '30m': 1_800_000, '1h': 3_600_000, '2h': 7_200_000,
    '4h': 14_400_000, '6h': 21_600_000, '8h': 28_800_000,
    '12h': 43_200_000, '1d': 86_400_000, '3d': 259_200_000,
    '1w': 604_800_000,
}


def emit(out, state, **payload):
    p = Path(out)
    p.mkdir(parents=True, exist_ok=True)
    (p / 'terminal_result.json').write_text(
        json.dumps({'object_id': OBJECT_ID, 'terminal_state': state, **payload}, indent=2, sort_keys=True)
    )


def finite_number(v):
    return isinstance(v, (int, float)) and math.isfinite(float(v))


def parse_ms(v):
    if not v:
        return None
    s = str(v).replace('Z', '+00:00')
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def load_snapshot():
    subprocess.run(
        ['git', '-C', REPO, 'fetch', 'origin', SNAP_BRANCH], check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=90,
    )
    raw = subprocess.run(
        ['git', '-C', REPO, 'show', f'FETCH_HEAD:{SNAP}'], check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30,
    ).stdout
    return json.loads(raw), hashlib.sha256(raw.encode()).hexdigest()


def endpoint(market):
    if market == 'spot':
        return 'https://api.binance.com/api/v3/klines'
    if market == 'futures':
        return 'https://fapi.binance.com/fapi/v1/klines'
    raise ValueError(f'unsupported market: {market}')


def fetch_bars(symbol, market, interval, start_ms, end_ms):
    step = INTERVAL_MS.get(interval)
    if step is None:
        raise ValueError(f'unsupported interval: {interval}')
    rows = []
    cursor = max(0, start_ms - step)
    while cursor <= end_ms:
        params = urllib.parse.urlencode({
            'symbol': symbol, 'interval': interval, 'startTime': cursor,
            'endTime': end_ms, 'limit': 1000,
        })
        req = urllib.request.Request(endpoint(market) + '?' + params, headers={'User-Agent': 'MarketHunter-Research/1.0'})
        last_err = None
        data = None
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as r:
                    data = json.loads(r.read().decode('utf-8'))
                break
            except Exception as e:
                last_err = e
                if attempt == 0:
                    time.sleep(0.25)
        if data is None:
            raise RuntimeError(f'binance request failed: {last_err!r}')
        if not isinstance(data, list):
            raise RuntimeError(f'unexpected Binance payload: {type(data).__name__}')
        if not data:
            break
        rows.extend(data)
        nxt = int(data[-1][0]) + step
        if nxt <= cursor:
            raise RuntimeError('non-advancing kline pagination')
        cursor = nxt
        if len(data) < 1000:
            break
    # TradeMonitor activates at entry candle close; extremes begin on strictly later completed candles.
    selected = [r for r in rows if int(r[6]) > start_ms and int(r[6]) <= end_ms]
    selected.sort(key=lambda r: int(r[0]))
    return selected, step


def reconstruct(trade, bars, step):
    entry = float(trade['entry_price'])
    if entry <= 0:
        raise ValueError('non-positive entry')
    if not bars:
        return None
    opens = [int(r[0]) for r in bars]
    gap_ok = all((b - a) <= int(step * MAX_GAP_MULTIPLIER) for a, b in zip(opens, opens[1:]))
    direction = str(trade.get('direction') or '').upper()
    if direction not in ('LONG', 'SHORT'):
        raise ValueError(f'unsupported direction: {direction}')
    mfe = 0.0
    mae = 0.0
    compact = []
    for r in bars:
        high, low = float(r[2]), float(r[3])
        if direction == 'LONG':
            fav = (high - entry) / entry * 100.0
            adv = (low - entry) / entry * 100.0
        else:
            fav = (entry - low) / entry * 100.0
            adv = (entry - high) / entry * 100.0
        mfe = max(mfe, fav)
        mae = min(mae, adv)
        compact.append([int(r[0]), int(r[6]), str(r[1]), str(r[2]), str(r[3]), str(r[4]), str(r[5])])
    stored_mfe = float(trade['max_profit_percent'])
    stored_mae = float(trade['max_drawdown_percent'])
    mfe_diff = abs(mfe - stored_mfe)
    mae_diff = abs(mae - stored_mae)
    return {
        'gap_ok': gap_ok,
        'bar_n': len(bars),
        'reconstructed_mfe_percent': mfe,
        'reconstructed_mae_percent': mae,
        'stored_mfe_percent': stored_mfe,
        'stored_mae_percent': stored_mae,
        'mfe_abs_diff_pp': mfe_diff,
        'mae_abs_diff_pp': mae_diff,
        'extrema_match': gap_ok and mfe_diff <= EXTREMA_TOLERANCE_PP and mae_diff <= EXTREMA_TOLERANCE_PP,
        'bars': compact,
    }


def main(out, job):
    try:
        cfg = json.loads(Path(job).read_text())
        if cfg.get('object_id') != OBJECT_ID:
            raise ValueError('object_id mismatch')
        snap, snap_sha = load_snapshot()
        trades = snap.get('trades')
        if not isinstance(trades, list):
            raise ValueError('snapshot trades missing')
        primary = [
            t for t in trades
            if t.get('market') in ('spot', 'futures')
            and t.get('status') in ('closed', 'expired')
            and finite_number(t.get('entry_price')) and float(t['entry_price']) > 0
            and finite_number(t.get('max_profit_percent')) and float(t['max_profit_percent']) >= MFE_MIN
            and finite_number(t.get('max_drawdown_percent'))
        ]
        if len(primary) < MIN_PRIMARY_N:
            emit(out, 'BLOCKED-EVIDENCE', reason='primary MFE cohort below predeclared minimum', primary_n=len(primary), minimum_n=MIN_PRIMARY_N)
            return
        timestamped = []
        missing_timestamp = []
        for t in primary:
            start_ms = parse_ms(t.get('opened_at'))
            end_ms = parse_ms(t.get('closed_at'))
            if start_ms is None or end_ms is None or end_ms <= start_ms:
                missing_timestamp.append(str(t.get('id')))
                continue
            timestamped.append((t, start_ms, end_ms))
        ts_cov = len(timestamped) / len(primary)
        if ts_cov < MIN_TIMESTAMP_COVERAGE:
            emit(out, 'BLOCKED-EVIDENCE', reason='insufficient deterministic trade-window timestamp coverage', primary_n=len(primary), timestamped_n=len(timestamped), timestamp_coverage=ts_cov, minimum_timestamp_coverage=MIN_TIMESTAMP_COVERAGE, missing_timestamp_trade_ids=missing_timestamp)
            return

        evidence = []
        failures = []
        matches = 0
        fetched = 0
        for t, start_ms, end_ms in sorted(timestamped, key=lambda x: str(x[0].get('id'))):
            try:
                bars, step = fetch_bars(str(t['symbol']), str(t['market']), str(t['timeframe']), start_ms, end_ms)
                rec = reconstruct(t, bars, step)
                if rec is None:
                    failures.append({'trade_id': str(t.get('id')), 'reason': 'no-bars'})
                    continue
                fetched += 1
                if rec['extrema_match']:
                    matches += 1
                payload = {
                    'trade_id': str(t.get('id')), 'symbol': t['symbol'], 'market': t['market'],
                    'timeframe': t['timeframe'], 'direction': t.get('direction'), 'entry_price': t['entry_price'],
                    'opened_at': t.get('opened_at'), 'closed_at': t.get('closed_at'),
                    **rec,
                }
                raw = json.dumps(payload['bars'], separators=(',', ':'), sort_keys=False).encode()
                payload['bars_sha256'] = hashlib.sha256(raw).hexdigest()
                evidence.append(payload)
            except Exception as e:
                failures.append({'trade_id': str(t.get('id')), 'symbol': t.get('symbol'), 'reason': repr(e)})

        fetch_cov = fetched / len(timestamped) if timestamped else 0.0
        match_rate = matches / fetched if fetched else 0.0
        artifact = {
            'object_id': OBJECT_ID,
            'snapshot': {'captured_at_utc': snap.get('captured_at_utc'), 'source': snap.get('source'), 'source_revision': snap.get('source_revision'), 'snapshot_sha256': snap_sha},
            'contract': {
                'mfe_min_percent': MFE_MIN, 'min_primary_n': MIN_PRIMARY_N,
                'min_timestamp_coverage': MIN_TIMESTAMP_COVERAGE, 'min_fetch_coverage': MIN_FETCH_COVERAGE,
                'min_extrema_match_rate': MIN_EXTREMA_MATCH_RATE, 'extrema_tolerance_pp': EXTREMA_TOLERANCE_PP,
                'bar_selection': 'candle.close_time > opened_at and <= closed_at',
                'intrabar_semantics': 'unresolved; no exit-policy counterfactual evaluated',
            },
            'counts': {'primary_n': len(primary), 'timestamped_n': len(timestamped), 'fetched_n': fetched, 'extrema_match_n': matches},
            'rates': {'timestamp_coverage': ts_cov, 'fetch_coverage': fetch_cov, 'extrema_match_rate': match_rate},
            'failures': failures,
            'evidence': evidence,
        }
        p = Path(out)
        p.mkdir(parents=True, exist_ok=True)
        ev_raw = json.dumps(artifact, indent=2, sort_keys=True)
        (p / 'barpath_evidence.json').write_text(ev_raw)
        ev_sha = hashlib.sha256(ev_raw.encode()).hexdigest()

        if fetch_cov < MIN_FETCH_COVERAGE:
            state = 'BLOCKED-EVIDENCE'
            reason = 'public Binance bar retrieval coverage below frozen threshold'
        elif match_rate < MIN_EXTREMA_MATCH_RATE:
            state = 'BARPATH-INCONSISTENT'
            reason = 'reconstructed OHLC extrema do not reproduce stored trade extrema often enough'
        else:
            state = 'BARPATH-ADEQUATE'
            reason = 'bar-ordered Binance paths reproduce stored trade extrema at frozen coverage and tolerance gates'
        emit(out, state, reason=reason, primary_n=len(primary), timestamped_n=len(timestamped), fetched_n=fetched, extrema_match_n=matches, timestamp_coverage=ts_cov, fetch_coverage=fetch_cov, extrema_match_rate=match_rate, extrema_tolerance_pp=EXTREMA_TOLERANCE_PP, evidence_file='barpath_evidence.json', evidence_sha256=ev_sha, snapshot={'captured_at_utc': snap.get('captured_at_utc'), 'source': snap.get('source'), 'source_revision': snap.get('source_revision'), 'snapshot_sha256': snap_sha}, interpretation='Evidence-adequacy test only. No trailing stop, breakeven, TP, sizing, strategy promotion or rejection is authorized. Same-bar ordering remains unresolved.')
    except Exception as e:
        emit(out, 'PROVIDER-BLOCKED', reason=repr(e))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--job', required=True)
    ap.add_argument('--output', required=True)
    args = ap.parse_args()
    main(args.output, args.job)
