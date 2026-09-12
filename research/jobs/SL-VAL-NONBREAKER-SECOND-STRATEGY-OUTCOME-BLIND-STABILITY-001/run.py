import argparse
import hashlib
import json
import math
import random
import subprocess
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

OBJECT_ID = 'SL-VAL-NONBREAKER-SECOND-STRATEGY-OUTCOME-BLIND-STABILITY-001'
REPO = '/home/ubuntu/MarketHunter'
SNAP_BRANCH = 'outcome-intelligence-snapshots'
SNAP_COMMIT = '614fd31472c9fc616cdee4a068609e6def67cb77'
SNAP = 'data/outcome_intelligence/latest/trades.json'
MIN_PER_STRATEGY = 16
MIN_HALF = 8
MIN_TS_COVERAGE = 0.90
BOOTSTRAPS = 10000
SEED = 20260911
EXCLUDED_STRATEGIES = {'Breaker'}
SELECTION_RANK = 2


def emit(out, state, **payload):
    p = Path(out)
    p.mkdir(parents=True, exist_ok=True)
    (p / 'terminal_result.json').write_text(
        json.dumps({'object_id': OBJECT_ID, 'terminal_state': state, **payload}, indent=2, sort_keys=True)
    )


def load_snapshot():
    subprocess.run(
        ['git', '-C', REPO, 'fetch', 'origin', SNAP_BRANCH],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=90
    )
    subprocess.run(
        ['git', '-C', REPO, 'cat-file', '-e', f'{SNAP_COMMIT}^{{commit}}'],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30
    )
    raw = subprocess.run(
        ['git', '-C', REPO, 'show', f'{SNAP_COMMIT}:{SNAP}'],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30
    ).stdout
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
    if not ys:
        return None
    pos = (len(ys) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return ys[lo]
    return ys[lo] + (ys[hi] - ys[lo]) * (pos - lo)


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
                'strategy': strategy,
                'closed_at': parse_ts(t.get('closed_at')),
                'profit_percent': pp,
                'symbol': str(t.get('symbol') or 'UNKNOWN'),
                'market': str(t.get('market') or 'UNKNOWN'),
                'timeframe': str(t.get('timeframe') or 'UNKNOWN'),
            })

        candidate_rows = []
        candidate_data = {}
        for strategy, rows in sorted(by.items()):
            before_ts = len(rows)
            valid = [r for r in rows if r['closed_at'] is not None]
            valid.sort(key=lambda r: (r['closed_at'], r['id']))
            coverage = (len(valid) / before_ts) if before_ts else 0.0
            mid = len(valid) // 2
            first = valid[:mid]
            second = valid[mid:]
            eligible = (
                len(valid) >= MIN_PER_STRATEGY
                and coverage >= MIN_TS_COVERAGE
                and len(first) >= MIN_HALF
                and len(second) >= MIN_HALF
            )
            rec = {
                'strategy': strategy,
                'eligible_before_timestamp': before_ts,
                'eligible_timestamped': len(valid),
                'timestamp_coverage': coverage,
                'first_n': len(first),
                'second_n': len(second),
                'candidate': eligible,
            }
            candidate_rows.append(rec)
            if eligible:
                candidate_data[strategy] = (rec, first, second)

        ranked = sorted(
            candidate_data,
            key=lambda s: (-candidate_data[s][0]['eligible_timestamped'], s)
        )
        common = {
            'snapshot': {
                'pinned_commit': SNAP_COMMIT,
                'captured_at_utc': snap.get('captured_at_utc'),
                'source': snap.get('source'),
                'source_revision': snap.get('source_revision'),
                'snapshot_sha256': snap_sha,
            },
            'contract': {
                'question': 'Does the discovery-half return sign of the second-most-represented eligible non-Breaker strategy, selected strictly by trade count, persist in the held-out chronological half?',
                'selection': 'Outcome-blind. Rank all strategies passing the frozen non-outcome evidence gates by descending eligible_timestamped trade count with lexical strategy name as deterministic tie-breaker; select rank 2. Breaker is excluded because of the independently established entry-zone validity confound.',
                'selection_rank': SELECTION_RANK,
                'split': 'Deterministic chronological 50/50 split by closed_at,id within the selected strategy.',
                'minimums': {
                    'timestamped_trades_per_strategy': MIN_PER_STRATEGY,
                    'trades_per_half': MIN_HALF,
                    'timestamp_coverage': MIN_TS_COVERAGE,
                },
                'bootstrap': {
                    'iterations': BOOTSTRAPS,
                    'seed': SEED,
                    'sampling': 'with replacement from held-out second-half trades of the selected strategy',
                    'interval': 'frozen 95% bootstrap CI of held-out mean profit_percent',
                },
                'terminal_logic': {
                    'DISCOVERY-SIGN-PERSISTS': 'held-out 95% CI lies wholly on the same side of zero as discovery-half mean',
                    'DISCOVERY-SIGN-REVERSES': 'held-out 95% CI lies wholly on the opposite side of zero from discovery-half mean',
                    'MIXED-SINGLE-STRATEGY-STABILITY': 'held-out 95% CI spans/touches zero, or discovery-half mean equals zero',
                    'BLOCKED-EVIDENCE': 'fewer than two strategies pass frozen non-outcome evidence gates or execution/data failure occurs',
                },
                'interpretation': 'Historical single-strategy temporal stability evidence only. No strategy promotion/rejection, sizing, allocation, leverage, capital rule, canonical promotion, or causal regime claim follows.',
            },
            'candidate_counts': candidate_rows,
            'eligible_rank_order': ranked,
            'exclusions': dict(exclusions),
            'selection_outcome_blind': True,
            'parameter_tuning': False,
        }

        if len(ranked) < SELECTION_RANK:
            emit(
                out, 'BLOCKED-EVIDENCE',
                reason='fewer than two non-Breaker strategies met frozen count/half/timestamp-coverage gates',
                **common
            )
            return

        selected = ranked[SELECTION_RANK - 1]
        rec, first, second = candidate_data[selected]
        discovery_vals = [r['profit_percent'] for r in first]
        validation_vals = [r['profit_percent'] for r in second]
        discovery_mean = mean(discovery_vals)
        validation_mean = mean(validation_vals)

        rng = random.Random(SEED)
        boot = []
        for _ in range(BOOTSTRAPS):
            sample = [validation_vals[rng.randrange(len(validation_vals))] for _ in range(len(validation_vals))]
            boot.append(mean(sample))
        lo = pctile(boot, 0.025)
        hi = pctile(boot, 0.975)

        if discovery_mean > 0:
            if lo > 0:
                state = 'DISCOVERY-SIGN-PERSISTS'
                reason = 'positive discovery-half mean remains positive across the frozen held-out 95% bootstrap interval'
            elif hi < 0:
                state = 'DISCOVERY-SIGN-REVERSES'
                reason = 'positive discovery-half mean is contradicted by a wholly negative frozen held-out 95% bootstrap interval'
            else:
                state = 'MIXED-SINGLE-STRATEGY-STABILITY'
                reason = 'held-out 95% interval spans/touches zero; positive discovery sign is not resolved as stable or reversed'
        elif discovery_mean < 0:
            if hi < 0:
                state = 'DISCOVERY-SIGN-PERSISTS'
                reason = 'negative discovery-half mean remains negative across the frozen held-out 95% bootstrap interval'
            elif lo > 0:
                state = 'DISCOVERY-SIGN-REVERSES'
                reason = 'negative discovery-half mean is contradicted by a wholly positive frozen held-out 95% bootstrap interval'
            else:
                state = 'MIXED-SINGLE-STRATEGY-STABILITY'
                reason = 'held-out 95% interval spans/touches zero; negative discovery sign is not resolved as stable or reversed'
        else:
            state = 'MIXED-SINGLE-STRATEGY-STABILITY'
            reason = 'discovery-half mean equals zero, so no directional discovery sign exists to validate'

        evidence = {
            **common,
            'selected_strategy': selected,
            'selected_rank': SELECTION_RANK,
            'selected_counts': rec,
            'discovery_half_mean_pp': discovery_mean,
            'heldout_half_mean_pp': validation_mean,
            'heldout_bootstrap_ci95_pp': [lo, hi],
            'discovery_sign': 'positive' if discovery_mean > 0 else ('negative' if discovery_mean < 0 else 'zero'),
        }
        ep = Path(out)
        ep.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(evidence, indent=2, sort_keys=True)
        (ep / 'second_strategy_stability_evidence.json').write_text(raw)
        ev_sha = hashlib.sha256(raw.encode()).hexdigest()
        emit(
            out, state,
            reason=reason,
            evidence_file='second_strategy_stability_evidence.json',
            evidence_sha256=ev_sha,
            selected_strategy=selected,
            selected_rank=SELECTION_RANK,
            selected_counts=rec,
            discovery_half_mean_pp=discovery_mean,
            heldout_half_mean_pp=validation_mean,
            heldout_bootstrap_ci95_pp=[lo, hi],
            **common
        )
    except Exception as e:
        emit(
            out, 'BLOCKED-EVIDENCE',
            reason=f'execution/data failure: {e!r}',
            pinned_commit=SNAP_COMMIT,
            selection_rank=SELECTION_RANK,
            selection_outcome_blind=True,
            parameter_tuning=False,
        )


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--job', required=True)
    ap.add_argument('--output', required=True)
    args = ap.parse_args()
    main(args.output, args.job)
