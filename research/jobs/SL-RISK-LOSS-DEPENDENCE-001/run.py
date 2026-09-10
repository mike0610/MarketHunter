import argparse
import hashlib
import json
import math
import random
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

OBJECT_ID = 'SL-RISK-LOSS-DEPENDENCE-001'
REPO = '/home/ubuntu/MarketHunter'
SNAP_BRANCH = 'outcome-intelligence-snapshots'
SNAP = 'data/outcome_intelligence/latest/trades.json'
SEED = 20260911
N_PERM = 10000
MIN_TRADES = 100
MIN_STRATEGIES = 3
MIN_PRIMARY_PAIRS = 100
SIGNAL_P = 0.05
SIGNAL_RATIO = 1.50
NO_SIGNAL_P = 0.10
NO_SIGNAL_RATIO = 1.20


def emit(out, state, **payload):
    p = Path(out)
    p.mkdir(parents=True, exist_ok=True)
    (p / 'terminal_result.json').write_text(json.dumps({'object_id': OBJECT_ID, 'terminal_state': state, **payload}, indent=2, sort_keys=True))


def parse_dt(v):
    if not v:
        return None
    dt = datetime.fromisoformat(str(v).replace('Z', '+00:00'))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def load_snapshot():
    subprocess.run(['git', '-C', REPO, 'fetch', 'origin', SNAP_BRANCH], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=90)
    raw = subprocess.run(['git', '-C', REPO, 'show', f'FETCH_HEAD:{SNAP}'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30).stdout
    return json.loads(raw), hashlib.sha256(raw.encode()).hexdigest()


def eligible_trade(t):
    if t.get('research_group') != 'core' or t.get('is_experimental'):
        return False
    if t.get('status') not in ('closed', 'expired') or t.get('outcome_group') not in ('positive', 'negative'):
        return False
    if not t.get('strategy') or not t.get('symbol') or str(t.get('direction', '')).upper() not in ('LONG', 'SHORT'):
        return False
    a, b = parse_dt(t.get('opened_at')), parse_dt(t.get('closed_at'))
    return a is not None and b is not None and b > a


def overlaps(a, b):
    return max(a['start'], b['start']) < min(a['end'], b['end'])


def build_pairs(rows):
    primary, same_symbol, all_cross = [], [], []
    for i in range(len(rows)):
        a = rows[i]
        for j in range(i + 1, len(rows)):
            b = rows[j]
            if a['strategy'] == b['strategy'] or not overlaps(a, b):
                continue
            all_cross.append((i, j))
            if a['direction'] != b['direction']:
                continue
            if a['symbol'] == b['symbol']:
                same_symbol.append((i, j))
            else:
                primary.append((i, j))
    return primary, same_symbol, all_cross


def joint_loss_count(pairs, labels):
    return sum(1 for i, j in pairs if labels[i] and labels[j])


def main(out, job):
    try:
        cfg = json.loads(Path(job).read_text())
        if cfg.get('object_id') != OBJECT_ID:
            raise ValueError('object_id mismatch')
        snap, snap_sha = load_snapshot()
        trades = snap.get('trades')
        if not isinstance(trades, list):
            raise ValueError('snapshot trades missing')

        rows = []
        for t in trades:
            if eligible_trade(t):
                rows.append({'id': str(t.get('id')), 'strategy': str(t['strategy']), 'symbol': str(t['symbol']), 'direction': str(t['direction']).upper(), 'start': parse_dt(t['opened_at']), 'end': parse_dt(t['closed_at']), 'loss': t['outcome_group'] == 'negative'})
        rows.sort(key=lambda x: x['id'])
        strategies = sorted({r['strategy'] for r in rows})
        primary, same_symbol, all_cross = build_pairs(rows)
        base = {
            'snapshot': {'captured_at_utc': snap.get('captured_at_utc'), 'source': snap.get('source'), 'source_revision': snap.get('source_revision'), 'snapshot_sha256': snap_sha},
            'contract': {
                'eligibility': 'core non-experimental closed/expired trades with positive/negative outcome and valid exposure window',
                'primary_pair': 'overlapping exposure windows; different strategies; same direction; different symbols',
                'null': '10000 deterministic permutations of loss labels within strategy, preserving strategy loss counts and all exposure windows',
                'seed': SEED,
                'signal_gate': {'p_le': SIGNAL_P, 'observed_to_null_median_ge': SIGNAL_RATIO},
                'no_signal_gate': {'p_ge': NO_SIGNAL_P, 'observed_to_null_median_le': NO_SIGNAL_RATIO},
                'interpretation': 'descriptive common-mode loss-dependence test only; no sizing/allocation/strategy rule inferred'
            },
            'counts': {'eligible_trades': len(rows), 'strategies': len(strategies), 'primary_pairs': len(primary), 'same_symbol_same_direction_pairs': len(same_symbol), 'all_cross_strategy_overlap_pairs': len(all_cross), 'loss_trades': sum(r['loss'] for r in rows)}
        }
        if len(rows) < MIN_TRADES or len(strategies) < MIN_STRATEGIES or len(primary) < MIN_PRIMARY_PAIRS:
            emit(out, 'BLOCKED-EVIDENCE', reason='frozen sample/pair breadth gate not met', **base)
            return

        labels = [r['loss'] for r in rows]
        observed = joint_loss_count(primary, labels)
        by_strategy = defaultdict(list)
        for idx, r in enumerate(rows):
            by_strategy[r['strategy']].append(idx)
        rng = random.Random(SEED)
        perm_counts = []
        for _ in range(N_PERM):
            perm = labels[:]
            for idxs in by_strategy.values():
                vals = [labels[i] for i in idxs]
                rng.shuffle(vals)
                for i, v in zip(idxs, vals):
                    perm[i] = v
            perm_counts.append(joint_loss_count(primary, perm))

        ps = sorted(perm_counts)
        median = (ps[N_PERM // 2 - 1] + ps[N_PERM // 2]) / 2.0
        p_upper = (1 + sum(x >= observed for x in perm_counts)) / (N_PERM + 1)
        ratio = observed / median if median > 0 else (math.inf if observed > 0 else 1.0)
        contrib = Counter()
        for i, j in primary:
            if labels[i] and labels[j]:
                contrib[' | '.join(sorted((rows[i]['strategy'], rows[j]['strategy'])))] += 1
        top = [{'strategy_pair': k, 'joint_loss_pairs': v} for k, v in contrib.most_common(10)]
        top_share = top[0]['joint_loss_pairs'] / observed if observed and top else 0.0
        evidence = {**base, 'observed': {'joint_loss_pairs': observed, 'null_median_joint_loss_pairs': median, 'observed_to_null_median_ratio': ratio, 'permutation_upper_p': p_upper, 'top_strategy_pair_share_of_joint_loss_pairs': top_share, 'top_strategy_pair_contributions': top}, 'null_summary': {'min': ps[0], 'p05': ps[int(0.05 * (N_PERM - 1))], 'median': median, 'p95': ps[int(0.95 * (N_PERM - 1))], 'max': ps[-1]}}
        p = Path(out)
        p.mkdir(parents=True, exist_ok=True)
        ev_raw = json.dumps(evidence, indent=2, sort_keys=True)
        (p / 'loss_dependence_evidence.json').write_text(ev_raw)
        ev_sha = hashlib.sha256(ev_raw.encode()).hexdigest()

        if p_upper <= SIGNAL_P and ratio >= SIGNAL_RATIO:
            state = 'COMMON-MODE-LOSS-SIGNAL'
            reason = 'cross-strategy same-direction distinct-symbol overlapping losses exceed the strategy-marginal permutation null at frozen significance and effect-size gates'
        elif p_upper >= NO_SIGNAL_P and ratio <= NO_SIGNAL_RATIO:
            state = 'NO-BROAD-LOSS-DEPENDENCE'
            reason = 'primary loss coincidence does not exceed the frozen broad-signal gates'
        else:
            state = 'INCONCLUSIVE-LOSS-DEPENDENCE'
            reason = 'evidence falls between frozen signal and no-broad-signal gates'
        emit(out, state, reason=reason, evidence_file='loss_dependence_evidence.json', evidence_sha256=ev_sha, observed_joint_loss_pairs=observed, null_median_joint_loss_pairs=median, observed_to_null_median_ratio=ratio, permutation_upper_p=p_upper, top_strategy_pair_share=top_share, **base)
    except Exception as e:
        emit(out, 'BLOCKED-EVIDENCE', reason=f'execution/data failure: {e!r}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--job', required=True)
    ap.add_argument('--output', required=True)
    args = ap.parse_args()
    main(args.output, args.job)
