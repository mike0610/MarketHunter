import argparse
import hashlib
import json
import math
import random
import subprocess
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

OBJECT_ID = 'SL-VAL-NONBREAKER-SINGLE-STRATEGY-DEPENDENCE-ROBUSTNESS-001'
REPO = '/home/ubuntu/MarketHunter'
SNAP_BRANCH = 'outcome-intelligence-snapshots'
SNAP_COMMIT = '614fd31472c9fc616cdee4a068609e6def67cb77'
SNAP = 'data/outcome_intelligence/latest/trades.json'
MIN_PER_STRATEGY = 16
MIN_HALF = 8
MIN_TS_COVERAGE = 0.90
MIN_CLUSTERS = 4
BOOTSTRAPS = 10000
SEED = 20260911
EXCLUDED_STRATEGIES = {'Breaker'}


def emit(out, state, **payload):
    p = Path(out)
    p.mkdir(parents=True, exist_ok=True)
    (p / 'terminal_result.json').write_text(json.dumps({'object_id': OBJECT_ID, 'terminal_state': state, **payload}, indent=2, sort_keys=True))


def load_snapshot():
    subprocess.run(['git', '-C', REPO, 'fetch', 'origin', SNAP_BRANCH], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=90)
    subprocess.run(['git', '-C', REPO, 'cat-file', '-e', f'{SNAP_COMMIT}^{{commit}}'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
    raw = subprocess.run(['git', '-C', REPO, 'show', f'{SNAP_COMMIT}:{SNAP}'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30).stdout
    return json.loads(raw), hashlib.sha256(raw.encode()).hexdigest()


def parse_ts(x):
    if not x:
        return None
    try:
        return datetime.fromisoformat(str(x).replace('Z', '+00:00'))
    except ValueError:
        return None


def mean(xs):
    return sum(xs) / len(xs)


def pctile(xs, q):
    ys = sorted(xs)
    pos = (len(ys) - 1) * q
    lo, hi = int(math.floor(pos)), int(math.ceil(pos))
    return ys[lo] if lo == hi else ys[lo] + (ys[hi] - ys[lo]) * (pos - lo)


def ci_state(ci):
    lo, hi = ci
    if lo > 0:
        return 'positive'
    if hi < 0:
        return 'negative'
    return 'mixed'


def bootstrap_trade(vals, rng):
    return [mean([vals[rng.randrange(len(vals))] for _ in range(len(vals))]) for _ in range(BOOTSTRAPS)]


def bootstrap_clusters(groups, rng):
    keys = sorted(groups)
    out = []
    for _ in range(BOOTSTRAPS):
        sampled = [keys[rng.randrange(len(keys))] for _ in range(len(keys))]
        vals = []
        for k in sampled:
            vals.extend(groups[k])
        out.append(mean(vals))
    return out


def main(out, job_path):
    try:
        cfg = json.loads(Path(job_path).read_text())
        if cfg.get('object_id') != OBJECT_ID:
            raise ValueError('object_id mismatch')
        snap, snap_sha = load_snapshot()
        trades = snap.get('trades')
        if not isinstance(trades, list):
            raise ValueError('snapshot trades missing')

        by = defaultdict(list)
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
            if strategy in EXCLUDED_STRATEGIES:
                exclusions['known_confounded_strategy'] += 1
                continue
            by[strategy].append({
                'id': str(t.get('id')),
                'closed_at': parse_ts(t.get('closed_at')),
                'profit_percent': pp,
                'symbol': str(t.get('symbol') or 'UNKNOWN'),
                'timeframe': str(t.get('timeframe') or 'UNKNOWN'),
            })

        candidates = {}
        candidate_counts = []
        for strategy, rows in sorted(by.items()):
            before = len(rows)
            valid = [r for r in rows if r['closed_at'] is not None]
            valid.sort(key=lambda r: (r['closed_at'], r['id']))
            coverage = len(valid) / before if before else 0.0
            mid = len(valid) // 2
            first, second = valid[:mid], valid[mid:]
            eligible = len(valid) >= MIN_PER_STRATEGY and coverage >= MIN_TS_COVERAGE and len(first) >= MIN_HALF and len(second) >= MIN_HALF
            rec = {'strategy': strategy, 'eligible_before_timestamp': before, 'eligible_timestamped': len(valid), 'timestamp_coverage': coverage, 'first_n': len(first), 'second_n': len(second), 'candidate': eligible}
            candidate_counts.append(rec)
            if eligible:
                candidates[strategy] = (rec, first, second)

        common = {
            'snapshot': {'pinned_commit': SNAP_COMMIT, 'captured_at_utc': snap.get('captured_at_utc'), 'source': snap.get('source'), 'source_revision': snap.get('source_revision'), 'snapshot_sha256': snap_sha},
            'contract': {
                'question': 'Does symbol-timeframe clustered dependence materially change the MIXED held-out inference for the same outcome-blind selected non-Breaker strategy?',
                'selection': 'Exactly the prior frozen outcome-blind rule: among non-Breaker strategies passing count/half/timestamp gates, select maximum eligible_timestamped count with lexical tie-breaker.',
                'split': 'Same deterministic chronological 50/50 split by closed_at,id.',
                'dependence_unit': 'symbol x timeframe within held-out half',
                'minimum_distinct_clusters': MIN_CLUSTERS,
                'bootstrap': {'iterations': BOOTSTRAPS, 'seed': SEED, 'naive': 'trade-level resampling with replacement', 'clustered': 'resample held-out symbol-timeframe clusters with replacement, retaining all trades in sampled clusters', 'interval': '95% percentile CI of held-out mean profit_percent'},
                'terminal_logic': {
                    'DEPENDENCE-ROBUST-MIXED': 'naive CI and clustered CI both span/touch zero',
                    'DEPENDENCE-SENSITIVE': 'naive CI spans/touches zero but clustered CI is wholly on one side of zero and is not opposite discovery sign',
                    'DEPENDENCE-ADVERSE': 'clustered CI is wholly opposite the discovery-half mean sign',
                    'BLOCKED-EVIDENCE': 'selection gates fail, fewer than four held-out symbol-timeframe clusters exist, prior naive inference is not MIXED on the frozen reconstruction, or execution/data failure occurs'
                },
                'interpretation': 'Dependence robustness only. No parameter tuning, strategy promotion/rejection, sizing, allocation, leverage, capital rule, canonical promotion, or causal regime claim.'
            },
            'candidate_counts': candidate_counts,
            'exclusions': dict(exclusions),
            'selection_outcome_blind': True,
            'parameter_tuning': False,
        }

        if not candidates:
            emit(out, 'BLOCKED-EVIDENCE', reason='no non-Breaker strategy met the frozen selection gates', **common)
            return
        selected = sorted(candidates, key=lambda s: (-candidates[s][0]['eligible_timestamped'], s))[0]
        rec, first, second = candidates[selected]
        discovery_mean = mean([r['profit_percent'] for r in first])
        vals = [r['profit_percent'] for r in second]
        groups = defaultdict(list)
        for r in second:
            groups[(r['symbol'], r['timeframe'])].append(r['profit_percent'])
        cluster_counts = {'|'.join(k): len(v) for k, v in sorted(groups.items())}
        max_cluster_share = max(cluster_counts.values()) / len(second)
        hhi = sum((n / len(second)) ** 2 for n in cluster_counts.values())

        if len(groups) < MIN_CLUSTERS:
            emit(out, 'BLOCKED-EVIDENCE', reason='held-out half has fewer than four distinct symbol-timeframe clusters for dependence-aware inference', selected_strategy=selected, selected_counts=rec, distinct_clusters=len(groups), cluster_counts=cluster_counts, max_cluster_share=max_cluster_share, cluster_hhi=hhi, **common)
            return

        naive_rng = random.Random(SEED)
        cluster_rng = random.Random(SEED + 1)
        naive_boot = bootstrap_trade(vals, naive_rng)
        cluster_boot = bootstrap_clusters(groups, cluster_rng)
        naive_ci = [pctile(naive_boot, 0.025), pctile(naive_boot, 0.975)]
        cluster_ci = [pctile(cluster_boot, 0.025), pctile(cluster_boot, 0.975)]
        naive_state = ci_state(naive_ci)
        cluster_state = ci_state(cluster_ci)
        discovery_sign = 'positive' if discovery_mean > 0 else ('negative' if discovery_mean < 0 else 'zero')

        if naive_state != 'mixed':
            state = 'BLOCKED-EVIDENCE'
            reason = 'frozen reconstruction did not reproduce the prior MIXED naive held-out inference; dependence attribution is not interpretable'
        elif discovery_sign != 'zero' and cluster_state != 'mixed' and cluster_state != discovery_sign:
            state = 'DEPENDENCE-ADVERSE'
            reason = 'dependence-aware clustered interval resolves wholly opposite the discovery-half sign'
        elif cluster_state != 'mixed':
            state = 'DEPENDENCE-SENSITIVE'
            reason = 'dependence-aware clustered interval changes the zero-crossing conclusion relative to the naive MIXED interval'
        else:
            state = 'DEPENDENCE-ROBUST-MIXED'
            reason = 'held-out uncertainty remains MIXED under both trade-level and symbol-timeframe clustered resampling'

        evidence = {
            **common,
            'selected_strategy': selected,
            'selected_counts': rec,
            'discovery_half_mean_pp': discovery_mean,
            'heldout_mean_pp': mean(vals),
            'discovery_sign': discovery_sign,
            'naive_ci95_pp': naive_ci,
            'clustered_ci95_pp': cluster_ci,
            'naive_ci_state': naive_state,
            'clustered_ci_state': cluster_state,
            'distinct_clusters': len(groups),
            'cluster_counts': cluster_counts,
            'max_cluster_share': max_cluster_share,
            'cluster_hhi': hhi,
        }
        ep = Path(out)
        ep.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(evidence, indent=2, sort_keys=True)
        (ep / 'dependence_robustness_evidence.json').write_text(raw)
        ev_sha = hashlib.sha256(raw.encode()).hexdigest()
        emit(out, state, reason=reason, evidence_file='dependence_robustness_evidence.json', evidence_sha256=ev_sha, selected_strategy=selected, selected_counts=rec, discovery_half_mean_pp=discovery_mean, heldout_mean_pp=mean(vals), naive_ci95_pp=naive_ci, clustered_ci95_pp=cluster_ci, distinct_clusters=len(groups), cluster_counts=cluster_counts, max_cluster_share=max_cluster_share, cluster_hhi=hhi, **common)
    except Exception as e:
        emit(out, 'BLOCKED-EVIDENCE', reason=f'execution/data failure: {e!r}', pinned_commit=SNAP_COMMIT, selection_outcome_blind=True, parameter_tuning=False)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--job', required=True)
    ap.add_argument('--output', required=True)
    args = ap.parse_args()
    main(args.output, args.job)
