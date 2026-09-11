import argparse
import hashlib
import json
import math
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

OBJECT_ID = 'SL-VAL-MARGINAL-EDGE-COHORT-SUFFICIENCY-001'
PARENT_OBJECT_ID = 'SL-VAL-STRATEGY-MARGINAL-EDGE-STABILITY-001'
ATTRIBUTION_OBJECT_ID = 'SL-VAL-MARGINAL-EDGE-STABILITY-BLOCKED-ATTRIBUTION-001'
SNAPSHOT_COMMIT = '3035e381ca64333c6c744b667f461ce9ce68c5cc'
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
        'attribution_object_id': ATTRIBUTION_OBJECT_ID,
        'parameter_tuning': False,
        'edge_inference_rerun': False,
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
    req = urllib.request.Request(SNAPSHOT_URL, headers={'User-Agent': 'MarketHunter-Research-Cohort-Sufficiency/1.0'})
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read().decode('utf-8')
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
        for trade in trades:
            if trade.get('research_group') != 'core' or trade.get('is_experimental'):
                exclusions['not_core_or_experimental'] += 1
                continue
            if trade.get('status') not in ('closed', 'expired') or trade.get('outcome_group') not in ('positive', 'negative'):
                exclusions['not_completed_binary_outcome'] += 1
                continue
            try:
                pp = float(trade.get('profit_percent'))
            except (TypeError, ValueError):
                exclusions['missing_profit_percent'] += 1
                continue
            if not math.isfinite(pp) or pp == 0:
                exclusions['invalid_or_zero_profit_percent'] += 1
                continue
            strategy = str(trade.get('strategy') or '').strip()
            if not strategy:
                exclusions['missing_strategy'] += 1
                continue
            base.append({
                'id': str(trade.get('id')),
                'strategy': strategy,
                'closed_at': parse_ts(trade.get('closed_at')),
                'profit_percent': pp,
            })

        valid = [row for row in base if row['closed_at'] is not None]
        ts_cov = (len(valid) / len(base)) if base else 0.0
        valid.sort(key=lambda row: (row['closed_at'], row['id']))
        by_strategy = defaultdict(list)
        for row in valid:
            by_strategy[row['strategy']].append(row)

        primary = {}
        confounded = {}
        insufficient = {}
        for strategy, rows in sorted(by_strategy.items()):
            if len(rows) < MIN_PER_STRATEGY:
                insufficient[strategy] = {'n': len(rows), 'reason': f'n<{MIN_PER_STRATEGY}'}
                continue
            mid = len(rows) // 2
            first, second = rows[:mid], rows[mid:]
            if len(first) < MIN_HALF or len(second) < MIN_HALF:
                insufficient[strategy] = {
                    'n': len(rows),
                    'first_n': len(first),
                    'second_n': len(second),
                    'reason': f'half<{MIN_HALF}',
                }
                continue
            rec = {
                'strategy': strategy,
                'n': len(rows),
                'first_n': len(first),
                'second_n': len(second),
                'first_mean_pp': mean([x['profit_percent'] for x in first]),
                'second_mean_pp': mean([x['profit_percent'] for x in second]),
                'full_mean_pp': mean([x['profit_percent'] for x in rows]),
            }
            if strategy in KNOWN_CONFOUNDED_STRATEGIES:
                confounded[strategy] = rec
            else:
                primary[strategy] = rec

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
            'contract_note': 'Checks the newest pinned immutable cohort against the exact parent pre-bootstrap evidence gates. No bootstrap, edge inference, threshold change, sizing, allocation, or Breaker promotion is performed.',
        }
        output_path = Path(out)
        output_path.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(evidence, indent=2, sort_keys=True)
        (output_path / 'cohort_sufficiency_evidence.json').write_text(raw)
        evidence_sha = hashlib.sha256(raw.encode()).hexdigest()

        common = {
            'failed_gates': failed,
            'gate_values': gate_values,
            'discovery_negative_strategies': discovery_negative,
            'evidence_file': 'cohort_sufficiency_evidence.json',
            'evidence_sha256': evidence_sha,
            'snapshot_commit': SNAPSHOT_COMMIT,
            'snapshot_sha256': snap_sha,
            'snapshot_captured_at_utc': snap.get('captured_at_utc'),
            'snapshot_source_revision': snap.get('source_revision'),
        }
        if failed:
            emit(out, 'COHORT-STILL-INSUFFICIENT',
                 reason='one or more unchanged frozen pre-bootstrap evidence gates still fail on the newest pinned cohort',
                 **common)
        else:
            emit(out, 'COHORT-SUFFICIENT',
                 reason='all unchanged frozen pre-bootstrap evidence gates pass on the newest pinned cohort; this only reopens eligibility for a separate edge-inference object',
                 **common)
    except Exception as exc:
        emit(out, 'BLOCKED-DATA',
             reason=f'cohort sufficiency execution/data failure: {exc!r}',
             snapshot_commit=SNAPSHOT_COMMIT)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    main(args.output, args.job)
