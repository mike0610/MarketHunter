import argparse
import hashlib
import json
import math
import statistics
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

OBJECT_ID = 'SL-VAL-MARGINAL-EDGE-STABILITY-BLOCKED-ATTRIBUTION-001'
PARENT_OBJECT_ID = 'SL-VAL-STRATEGY-MARGINAL-EDGE-STABILITY-001'
PARENT_RUN_ID = '34582281738'
SNAPSHOT_COMMIT = 'f8c72efa5bb343e797aec28c874d02000da99127'
SNAPSHOT_PATH = 'data/outcome_intelligence/latest/trades.json'
SNAPSHOT_URL = f'https://raw.githubusercontent.com/mike0610/MarketHunter/{SNAPSHOT_COMMIT}/{SNAPSHOT_PATH}'
MIN_TOTAL_TRADES = 120
MIN_STRATEGIES = 5
MIN_PER_STRATEGY = 16
MIN_HALF = 8
MIN_TS_COVERAGE = 0.90
MIN_DISCOVERY_NEGATIVE = 2
KNOWN_CONFOUNDED_STRATEGIES = {'Breaker'}


def emit(out, state, **payload):
    p = Path(out)
    p.mkdir(parents=True, exist_ok=True)
    result = {
        'object_id': OBJECT_ID,
        'terminal_state': state,
        'parent_object_id': PARENT_OBJECT_ID,
        'parent_run_id': PARENT_RUN_ID,
        'parameter_tuning': False,
        **payload,
    }
    (p / 'terminal_result.json').write_text(json.dumps(result, indent=2, sort_keys=True))


def parse_ts(x):
    if not x:
        return None
    try:
        return datetime.fromisoformat(str(x).replace('Z', '+00:00'))
    except ValueError:
        return None


def mean(xs):
    return sum(xs) / len(xs)


def load_snapshot():
    req = urllib.request.Request(SNAPSHOT_URL, headers={'User-Agent': 'MarketHunter-Research-Attribution/1.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode('utf-8')
    return json.loads(raw), hashlib.sha256(raw.encode()).hexdigest()


def main(out, job_path):
    try:
        cfg = json.loads(Path(job_path).read_text())
        if cfg.get('object_id') != OBJECT_ID:
            raise ValueError('object_id mismatch')

        snap, snap_sha = load_snapshot()
        trades = snap.get('trades')
        if not isinstance(trades, list):
            raise ValueError('snapshot trades missing')

        base = []
        exclusions = Counter()
        for t in trades:
            if t.get('research_group') != 'core' or t.get('is_experimental'):
                exclusions['not_core_or_experimental'] += 1
                continue
            if t.get('status') not in ('closed', 'expired') or t.get('outcome_group') not in ('positive', 'negative'):
                exclusions['not_completed_binary_outcome'] += 1
                continue
            try:
                pp = float(t.get('profit_percent'))
            except (TypeError, ValueError):
                exclusions['missing_profit_percent'] += 1
                continue
            if not math.isfinite(pp) or pp == 0:
                exclusions['invalid_or_zero_profit_percent'] += 1
                continue
            strategy = str(t.get('strategy') or '').strip()
            if not strategy:
                exclusions['missing_strategy'] += 1
                continue
            ts = parse_ts(t.get('closed_at'))
            base.append({
                'id': str(t.get('id')),
                'strategy': strategy,
                'closed_at': ts,
                'profit_percent': pp,
            })

        valid = [r for r in base if r['closed_at'] is not None]
        ts_cov = (len(valid) / len(base)) if base else 0.0
        valid.sort(key=lambda r: (r['closed_at'], r['id']))
        by = defaultdict(list)
        for r in valid:
            by[r['strategy']].append(r)

        primary = {}
        confounded = {}
        insufficient = {}
        for s, rows in sorted(by.items()):
            if len(rows) < MIN_PER_STRATEGY:
                insufficient[s] = {'n': len(rows), 'reason': f'n<{MIN_PER_STRATEGY}'}
                continue
            mid = len(rows) // 2
            first, second = rows[:mid], rows[mid:]
            if len(first) < MIN_HALF or len(second) < MIN_HALF:
                insufficient[s] = {'n': len(rows), 'first_n': len(first), 'second_n': len(second), 'reason': f'half<{MIN_HALF}'}
                continue
            rec = {
                'strategy': s,
                'n': len(rows),
                'first_n': len(first),
                'second_n': len(second),
                'first_mean_pp': mean([x['profit_percent'] for x in first]),
                'second_mean_pp': mean([x['profit_percent'] for x in second]),
                'full_mean_pp': mean([x['profit_percent'] for x in rows]),
            }
            if s in KNOWN_CONFOUNDED_STRATEGIES:
                confounded[s] = rec
            else:
                primary[s] = rec

        primary_strategies = sorted(primary)
        discovery_negative = [s for s in primary_strategies if primary[s]['first_mean_pp'] < 0]

        gate_values = {
            'eligible_timestamped_trades': len(valid),
            'minimum_eligible_timestamped_trades': MIN_TOTAL_TRADES,
            'timestamp_coverage': ts_cov,
            'minimum_timestamp_coverage': MIN_TS_COVERAGE,
            'primary_strategies': len(primary_strategies),
            'minimum_primary_strategies': MIN_STRATEGIES,
            'discovery_negative_strategies': len(discovery_negative),
            'minimum_discovery_negative_strategies': MIN_DISCOVERY_NEGATIVE,
        }
        failed = []
        if len(valid) < MIN_TOTAL_TRADES:
            failed.append('eligible_timestamped_trades')
        if len(primary_strategies) < MIN_STRATEGIES:
            failed.append('primary_strategies')
        if ts_cov < MIN_TS_COVERAGE:
            failed.append('timestamp_coverage')
        if len(discovery_negative) < MIN_DISCOVERY_NEGATIVE:
            failed.append('discovery_negative_strategies')

        evidence = {
            'snapshot_commit': SNAPSHOT_COMMIT,
            'snapshot_sha256': snap_sha,
            'snapshot_captured_at_utc': snap.get('captured_at_utc'),
            'snapshot_source_revision': snap.get('source_revision'),
            'snapshot_total': snap.get('total'),
            'eligible_before_timestamp': len(base),
            'gate_values': gate_values,
            'failed_gates': failed,
            'primary_strategy_breakdown': [primary[s] for s in primary_strategies],
            'discovery_negative_strategies': discovery_negative,
            'known_confounded_strategy_breakdown': list(confounded.values()),
            'insufficient_strategy_breakdown': insufficient,
            'exclusions': dict(exclusions),
            'contract_note': 'Exact parent eligibility, per-strategy breadth, chronological split, Breaker exclusion, and gate logic reproduced without bootstrap or threshold changes. Snapshot is pinned to the branch commit that was already current before and remained current after parent run 34582281738.',
        }
        ep = Path(out)
        ep.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(evidence, indent=2, sort_keys=True)
        (ep / 'blocked_attribution_evidence.json').write_text(raw)
        ev_sha = hashlib.sha256(raw.encode()).hexdigest()

        if failed:
            emit(out, 'ATTRIBUTED-GATE-FAILURE',
                 reason='parent BLOCKED-EVIDENCE reproduced by one or more frozen pre-bootstrap gates',
                 failed_gates=failed,
                 gate_values=gate_values,
                 discovery_negative_strategies=discovery_negative,
                 evidence_file='blocked_attribution_evidence.json',
                 evidence_sha256=ev_sha,
                 snapshot_commit=SNAPSHOT_COMMIT,
                 snapshot_sha256=snap_sha)
        else:
            emit(out, 'PARENT-BLOCK-NOT-REPRODUCED',
                 reason='all frozen pre-bootstrap gates pass on the pinned parent snapshot; parent BLOCKED-EVIDENCE therefore requires separate execution/data-failure attribution',
                 failed_gates=[],
                 gate_values=gate_values,
                 discovery_negative_strategies=discovery_negative,
                 evidence_file='blocked_attribution_evidence.json',
                 evidence_sha256=ev_sha,
                 snapshot_commit=SNAPSHOT_COMMIT,
                 snapshot_sha256=snap_sha)
    except Exception as e:
        emit(out, 'ATTRIBUTION-BLOCKED-DATA', reason=f'attribution execution/data failure: {e!r}', snapshot_commit=SNAPSHOT_COMMIT)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--job', required=True)
    ap.add_argument('--output', required=True)
    a = ap.parse_args()
    main(a.output, a.job)
