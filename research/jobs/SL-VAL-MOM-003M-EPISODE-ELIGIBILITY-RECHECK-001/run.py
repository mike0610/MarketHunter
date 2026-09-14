import argparse, json, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

OBJECT_ID = 'SL-VAL-MOM-003M-EPISODE-ELIGIBILITY-RECHECK-001'
SYMBOL = 'BTCUSDT'
INTERVAL = '1d'
START = datetime(2026, 1, 5, tzinfo=timezone.utc)
END = datetime(2026, 9, 14, tzinfo=timezone.utc)
FORMATION_DAYS = 84
API = 'https://api.binance.com/api/v3/klines'


def emit(out, state, **payload):
    p = Path(out)
    p.mkdir(parents=True, exist_ok=True)
    (p / 'terminal_result.json').write_text(
        json.dumps({'object_id': OBJECT_ID, 'terminal_state': state, **payload}, indent=2, sort_keys=True)
    )


def fetch_daily(start, end):
    params = urllib.parse.urlencode({
        'symbol': SYMBOL,
        'interval': INTERVAL,
        'startTime': int(start.timestamp() * 1000),
        'endTime': int(end.timestamp() * 1000),
        'limit': 1000,
    })
    req = urllib.request.Request(API + '?' + params, headers={'User-Agent': 'MarketHunter-Research/1.0'})
    with urllib.request.urlopen(req, timeout=25) as r:
        rows = json.loads(r.read().decode('utf-8'))
    opens = {}
    for row in rows:
        ts = int(row[0])
        dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        if dt in opens:
            raise ValueError(f'duplicate open time {dt.isoformat()}')
        opens[dt] = float(row[1])
    return opens


def main(out, job):
    try:
        cfg = json.loads(Path(job).read_text())
        assert cfg['object_id'] == OBJECT_ID and cfg['executor'] == 'vps'

        need_start = START - timedelta(days=FORMATION_DAYS)
        opens = fetch_daily(need_start, END)
        if not opens:
            return emit(out, 'PROVIDER-BLOCKED', reason='no Binance REST rows acquired')

        d = need_start
        missing = []
        while d <= END:
            if d not in opens:
                missing.append(d.isoformat())
            d += timedelta(days=1)
        if missing:
            return emit(
                out,
                'PROVIDER-BLOCKED',
                reason='missing required daily Binance REST rows',
                missing_count=len(missing),
                missing=missing[:20],
            )

        mondays = []
        t = START
        while t <= END:
            mondays.append(t)
            t += timedelta(days=7)

        long_flags = []
        for a, b in zip(mondays[:-1], mondays[1:]):
            lag = a - timedelta(days=FORMATION_DAYS)
            formation = opens[a] / opens[lag] - 1.0
            long_flags.append({'start': a.isoformat(), 'end': b.isoformat(), 'long': formation > 0})

        # Preserve predecessor episode-grouping semantics exactly for eligibility only:
        # contiguous LONG weekly intervals form one episode; a terminal LONG block at END
        # is counted exactly as in the frozen predecessor runner. No return/P&L is computed.
        episodes = []
        cur = []
        for w in long_flags:
            if w['long']:
                cur.append(w)
            elif cur:
                episodes.append({'start': cur[0]['start'], 'end': cur[-1]['end'], 'weeks': len(cur)})
                cur = []
        if cur:
            episodes.append({'start': cur[0]['start'], 'end': cur[-1]['end'], 'weeks': len(cur)})

        count = len(episodes)
        state = 'ELIGIBLE-RETEST' if count >= 3 else 'INSUFFICIENT-EPISODES'
        emit(
            out,
            state,
            reason='outcome-blind natural-time episode eligibility recheck under frozen 12-week LONG/FLAT rule',
            contract={
                'symbol': SYMBOL,
                'interval': INTERVAL,
                'window': '2026-01-05T00:00:00Z to 2026-09-14T00:00:00Z',
                'formation_days': FORMATION_DAYS,
                'signal': 'LONG iff prior 84-calendar-day formation return > 0, else FLAT',
                'execution_boundary': 'Monday 00:00 UTC daily open',
                'eligibility_gate': '>=3 completed LONG episodes under predecessor grouping semantics',
                'outcome_blind': True,
                'pnl_computed': False,
                'parameter_tuning': False,
            },
            completed_weekly_intervals=len(long_flags),
            completed_long_episodes=count,
            episodes=episodes,
            provider='Binance public REST /api/v3/klines',
        )
    except Exception as e:
        emit(
            out,
            'PROVIDER-BLOCKED',
            reason=f'provider/data/execution failure: {e!r}',
            contract_frozen=True,
            outcome_blind=True,
        )


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--job', required=True)
    ap.add_argument('--output', required=True)
    a = ap.parse_args()
    main(a.output, a.job)
