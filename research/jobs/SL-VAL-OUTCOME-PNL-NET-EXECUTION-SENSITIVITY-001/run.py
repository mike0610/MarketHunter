import argparse
import hashlib
import json
import math
import random
import subprocess
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

OBJECT_ID = 'SL-VAL-OUTCOME-PNL-NET-EXECUTION-SENSITIVITY-001'
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
FEE_BPS_PER_SIDE = 4.0
SLIPPAGE_BPS_PER_SIDE = 2.0
ROUND_TRIP_COST_PP = 2.0 * (FEE_BPS_PER_SIDE + SLIPPAGE_BPS_PER_SIDE) / 100.0


def emit(out, state, **payload):
    p = Path(out); p.mkdir(parents=True, exist_ok=True)
    (p / 'terminal_result.json').write_text(json.dumps({'object_id': OBJECT_ID, 'terminal_state': state, **payload}, indent=2, sort_keys=True))


def parse_ts(x):
    if not x: return None
    try: return datetime.fromisoformat(str(x).replace('Z', '+00:00'))
    except ValueError: return None


def mean(xs): return sum(xs) / len(xs)


def pctile(xs, q):
    ys = sorted(xs); pos = (len(ys) - 1) * q
    lo, hi = int(math.floor(pos)), int(math.ceil(pos))
    return ys[lo] if lo == hi else ys[lo] + (ys[hi] - ys[lo]) * (pos - lo)


def classify(discovery_mean, lo, hi):
    if discovery_mean > 0:
        if lo > 0: return 'SIGN-PERSISTS'
        if hi < 0: return 'SIGN-REVERSES'
    elif discovery_mean < 0:
        if hi < 0: return 'SIGN-PERSISTS'
        if lo > 0: return 'SIGN-REVERSES'
    return 'MIXED-STABILITY'


def boot_ci(vals):
    rng = random.Random(SEED); out = []
    for _ in range(BOOTSTRAPS):
        out.append(mean([vals[rng.randrange(len(vals))] for _ in range(len(vals))]))
    return [pctile(out, 0.025), pctile(out, 0.975)]


def main(out, job_path):
    try:
        cfg = json.loads(Path(job_path).read_text())
        if cfg.get('object_id') != OBJECT_ID: raise ValueError('object_id mismatch')
        subprocess.run(['git','-C',REPO,'fetch','origin',SNAP_BRANCH], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=90)
        subprocess.run(['git','-C',REPO,'cat-file','-e',f'{SNAP_COMMIT}^{{commit}}'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
        raw = subprocess.run(['git','-C',REPO,'show',f'{SNAP_COMMIT}:{SNAP}'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30).stdout
        snap = json.loads(raw); trades = snap.get('trades')
        if not isinstance(trades, list): raise ValueError('snapshot trades missing')

        by = defaultdict(list); exclusions = Counter()
        for t in trades:
            if t.get('research_group') != 'core' or t.get('is_experimental'):
                exclusions['not_core_or_experimental'] += 1; continue
            if t.get('status') not in ('closed','expired') or t.get('outcome_group') not in ('positive','negative'):
                exclusions['not_completed_binary_outcome'] += 1; continue
            try: pp = float(t.get('profit_percent'))
            except (TypeError, ValueError): exclusions['missing_profit_percent'] += 1; continue
            if not math.isfinite(pp) or pp == 0:
                exclusions['invalid_or_zero_profit_percent'] += 1; continue
            strategy = str(t.get('strategy') or '').strip()
            if not strategy: exclusions['missing_strategy'] += 1; continue
            if strategy in EXCLUDED_STRATEGIES: exclusions['known_confounded_strategy'] += 1; continue
            by[strategy].append({'id': str(t.get('id')), 'closed_at': parse_ts(t.get('closed_at')), 'profit_percent': pp})

        candidates = {}
        counts = []
        for strategy, rows in sorted(by.items()):
            before = len(rows); valid = [r for r in rows if r['closed_at'] is not None]
            valid.sort(key=lambda r: (r['closed_at'], r['id']))
            coverage = len(valid) / before if before else 0.0; mid = len(valid)//2
            first, second = valid[:mid], valid[mid:]
            eligible = len(valid)>=MIN_PER_STRATEGY and coverage>=MIN_TS_COVERAGE and len(first)>=MIN_HALF and len(second)>=MIN_HALF
            rec = {'strategy':strategy,'eligible_before_timestamp':before,'eligible_timestamped':len(valid),'timestamp_coverage':coverage,'first_n':len(first),'second_n':len(second),'candidate':eligible}
            counts.append(rec)
            if eligible: candidates[strategy]=(rec,first,second)
        if not candidates:
            emit(out,'BLOCKED-EVIDENCE',reason='no non-Breaker strategy met frozen evidence gates',candidate_counts=counts); return

        selected = sorted(candidates, key=lambda s:(-candidates[s][0]['eligible_timestamped'],s))[0]
        rec, first, second = candidates[selected]
        gross_d = [r['profit_percent'] for r in first]; gross_h = [r['profit_percent'] for r in second]
        net_d = [x - ROUND_TRIP_COST_PP for x in gross_d]; net_h = [x - ROUND_TRIP_COST_PP for x in gross_h]
        gross_ci = boot_ci(gross_h); net_ci = boot_ci(net_h)
        gross_state = classify(mean(gross_d), *gross_ci); net_state = classify(mean(net_d), *net_ci)
        state = {'SIGN-PERSISTS':'COST-ADJUSTED-SIGN-PERSISTS','SIGN-REVERSES':'COST-ADJUSTED-SIGN-REVERSES','MIXED-STABILITY':'COST-ADJUSTED-MIXED-STABILITY'}[net_state]
        evidence = {
            'snapshot': {'pinned_commit':SNAP_COMMIT,'captured_at_utc':snap.get('captured_at_utc'),'source':snap.get('source'),'source_revision':snap.get('source_revision'),'snapshot_sha256':hashlib.sha256(raw.encode()).hexdigest()},
            'contract': {
                'selection':'Identical outcome-blind rank-1 eligible non-Breaker selection and chronological 50/50 split as the frozen single-strategy stability object.',
                'cost_model': {'fee_bps_per_side':FEE_BPS_PER_SIDE,'slippage_bps_per_side':SLIPPAGE_BPS_PER_SIDE,'round_trip_cost_bps':12.0,'round_trip_cost_percentage_points':ROUND_TRIP_COST_PP,'application':'subtract fixed round-trip cost from every stored gross profit_percent observation; no parameter tuning'},
                'provenance':'MarketHunter default StrategyReplayConfig assumption on master 5776a96113764fef3eef6d2c9a7298f5571adbd7: 4 bps fee + 2 bps slippage per side.',
                'fill_limit':'Sensitivity adjusts stored returns for fixed costs only. It does not reconstruct spread path, queue position, market impact, latency, funding, or whether a touch would have filled.',
                'bootstrap': {'iterations':BOOTSTRAPS,'seed':SEED,'interval':'95% held-out mean CI'},
                'interpretation':'Execution-cost sensitivity of historical stability only; no promotion/rejection, sizing, leverage, allocation or canonical claim.'
            },
            'selected_strategy':selected,'selected_counts':rec,'candidate_counts':counts,'exclusions':dict(exclusions),
            'gross':{'discovery_mean_pp':mean(gross_d),'heldout_mean_pp':mean(gross_h),'heldout_ci95_pp':gross_ci,'stability':gross_state},
            'cost_adjusted':{'discovery_mean_pp':mean(net_d),'heldout_mean_pp':mean(net_h),'heldout_ci95_pp':net_ci,'stability':net_state},
            'verdict_changed_by_cost_model': gross_state != net_state,
            'selection_outcome_blind':True,'parameter_tuning':False
        }
        p=Path(out); p.mkdir(parents=True,exist_ok=True); eraw=json.dumps(evidence,indent=2,sort_keys=True)
        (p/'net_execution_sensitivity_evidence.json').write_text(eraw)
        emit(out,state,reason='frozen 12 bps round-trip cost sensitivity completed',evidence_file='net_execution_sensitivity_evidence.json',evidence_sha256=hashlib.sha256(eraw.encode()).hexdigest(),**evidence)
    except Exception as e:
        emit(out,'BLOCKED-EVIDENCE',reason=f'execution/data failure: {e!r}',pinned_commit=SNAP_COMMIT,parameter_tuning=False)


if __name__ == '__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--job',required=True); ap.add_argument('--output',required=True); a=ap.parse_args(); main(a.output,a.job)
