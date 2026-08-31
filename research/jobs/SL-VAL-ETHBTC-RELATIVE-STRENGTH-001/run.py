import argparse
import csv
import io
import json
import math
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

OBJ = 'SL-VAL-ETHBTC-RELATIVE-STRENGTH-001'
SYM = 'ETHBTC'
START = datetime(2022, 1, 1, tzinfo=timezone.utc)
END = datetime(2026, 8, 1, tzinfo=timezone.utc)
SPLIT = datetime(2025, 1, 1, tzinfo=timezone.utc)

parser = argparse.ArgumentParser()
parser.add_argument('--job', required=False)
parser.add_argument('--output', default='research_output')
args = parser.parse_args()
OUT = Path(args.output)
OUT.mkdir(parents=True, exist_ok=True)


def month_iter(start_year, start_month, end_year, end_month):
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        yield y, m
        m += 1
        if m == 13:
            y += 1
            m = 1


def parse_time(raw):
    value = int(raw)
    seconds = value / (1_000_000 if value > 10**14 else 1_000)
    return datetime.fromtimestamp(seconds, tz=timezone.utc)


def load_month(y, m):
    name = f'{SYM}-4h-{y}-{m:02d}.zip'
    url = f'https://data.binance.vision/data/spot/monthly/klines/{SYM}/4h/{name}'
    try:
        raw = urllib.request.urlopen(url, timeout=30).read()
    except Exception:
        return []

    rows = []
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        with zf.open(zf.namelist()[0]) as fh:
            text = io.TextIOWrapper(fh, encoding='utf-8')
            reader = csv.reader(text)
            for r in reader:
                if len(r) < 5:
                    continue
                try:
                    rows.append({
                        'time': parse_time(r[0]),
                        'open': float(r[1]),
                        'high': float(r[2]),
                        'low': float(r[3]),
                        'close': float(r[4]),
                    })
                except (ValueError, OverflowError):
                    continue
    return rows


rows = []
for y, m in month_iter(2021, 10, 2026, 8):
    rows.extend(load_month(y, m))
if not rows:
    raise RuntimeError('no data')

by_time = {r['time']: r for r in rows if datetime(2021, 10, 1, tzinfo=timezone.utc) <= r['time'] <= END}
rows = [by_time[t] for t in sorted(by_time)]

trades = []
next_allowed = -1
for i in range(42, len(rows) - 19):
    prior_high42 = max(r['close'] for r in rows[i - 42:i])
    signal = rows[i]['close'] > prior_high42
    if i < next_allowed or not signal or rows[i]['time'] < START:
        continue
    entry_i = i + 1
    exit_i = entry_i + 18
    if exit_i >= len(rows):
        break
    entry = rows[entry_i]['open']
    exitp = rows[exit_i]['open']
    gross = exitp / entry - 1.0
    trades.append({
        'signal_time': rows[i]['time'],
        'entry_time': rows[entry_i]['time'],
        'exit_time': rows[exit_i]['time'],
        'gross_return': gross,
        'sample': 'IS' if rows[entry_i]['time'] < SPLIT else 'OOS',
    })
    next_allowed = i + 18


def metrics(items, cost_bps):
    if not items:
        return {'n': 0}
    net = [t['gross_return'] - cost_bps / 10000.0 for t in items]
    positives = [r for r in net if r > 0]
    negatives = [-r for r in net if r < 0]
    pos = sum(positives)
    neg = sum(negatives)

    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in net:
        equity *= 1.0 + r
        peak = max(peak, equity)
        max_dd = min(max_dd, equity / peak - 1.0)

    wins = sorted(positives, reverse=True)
    top_share = wins[0] / sum(wins) if wins and sum(wins) > 0 else None

    loss = 0
    max_loss = 0
    for r in net:
        loss = loss + 1 if r < 0 else 0
        max_loss = max(max_loss, loss)

    ordered = sorted(net)
    n = len(ordered)
    if n % 2:
        median = ordered[n // 2]
    else:
        median = (ordered[n // 2 - 1] + ordered[n // 2]) / 2.0

    return {
        'n': len(net),
        'mean_pct': sum(net) / len(net) * 100.0,
        'median_pct': median * 100.0,
        'hit_rate': sum(1 for r in net if r > 0) / len(net),
        'profit_factor': pos / neg if neg > 0 else None,
        'cumulative_pct': (equity - 1.0) * 100.0,
        'max_drawdown_pct': max_dd * 100.0,
        'top_positive_trade_share': top_share,
        'max_loss_streak': max_loss,
    }


is_trades = [t for t in trades if t['sample'] == 'IS']
oos_trades = [t for t in trades if t['sample'] == 'OOS']
res = {
    'object_id': OBJ,
    'terminal_state': 'OUTCOME-COMPLETE',
    'market': SYM,
    'book': 'SPOT',
    'leverage': 1.0,
    'total_events': len(trades),
    'is_10bps': metrics(is_trades, 10),
    'oos_10bps': metrics(oos_trades, 10),
    'oos_20bps': metrics(oos_trades, 20),
}

o = res['oos_10bps']
s = res['oos_20bps']
if o.get('n', 0) < 30:
    verdict = 'BLOCKED-EVIDENCE'
elif o['mean_pct'] > 0 and o['profit_factor'] is not None and o['profit_factor'] > 1 and s['mean_pct'] > 0 and (o['top_positive_trade_share'] or 1) < 0.5:
    verdict = 'CANDIDATE'
else:
    verdict = 'REJECTED'
res['terminal_verdict'] = verdict

monthly = {}
for t in oos_trades:
    key = t['entry_time'].strftime('%Y-%m')
    monthly.setdefault(key, []).append(t['gross_return'] - 0.001)
res['oos_monthly'] = [
    {'month': month, 'count': len(vals), 'mean': sum(vals) / len(vals), 'sum': sum(vals)}
    for month, vals in sorted(monthly.items())
]

with (OUT / 'trades.csv').open('w', newline='', encoding='utf-8') as fh:
    writer = csv.DictWriter(fh, fieldnames=['signal_time', 'entry_time', 'exit_time', 'gross_return', 'sample'])
    writer.writeheader()
    for t in trades:
        writer.writerow({
            **t,
            'signal_time': t['signal_time'].isoformat(),
            'entry_time': t['entry_time'].isoformat(),
            'exit_time': t['exit_time'].isoformat(),
        })

(OUT / 'terminal_result.json').write_text(json.dumps(res, indent=2), encoding='utf-8')
print(json.dumps(res, indent=2))
