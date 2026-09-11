import argparse
import hashlib
import json
import math
import random
import statistics
import subprocess
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

OBJECT_ID='SL-VAL-STRATEGY-MARGINAL-EDGE-STABILITY-001'
REPO='/home/ubuntu/MarketHunter'
SNAP_BRANCH='outcome-intelligence-snapshots'
SNAP='data/outcome_intelligence/latest/trades.json'
MIN_TOTAL_TRADES=120
MIN_STRATEGIES=5
MIN_PER_STRATEGY=16
MIN_HALF=8
MIN_TS_COVERAGE=0.90
MIN_DISCOVERY_NEGATIVE=2
BOOTSTRAPS=10000
SEED=20260911
KNOWN_CONFOUNDED_STRATEGIES={'Breaker'}

def emit(out,state,**payload):
    p=Path(out); p.mkdir(parents=True,exist_ok=True)
    (p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':state,**payload},indent=2,sort_keys=True))

def load_snapshot():
    subprocess.run(['git','-C',REPO,'fetch','origin',SNAP_BRANCH],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=90)
    raw=subprocess.run(['git','-C',REPO,'show',f'FETCH_HEAD:{SNAP}'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30).stdout
    return json.loads(raw),hashlib.sha256(raw.encode()).hexdigest()

def parse_ts(x):
    if not x: return None
    try: return datetime.fromisoformat(str(x).replace('Z','+00:00'))
    except ValueError: return None

def mean(xs):
    return sum(xs)/len(xs)

def pctile(xs,q):
    ys=sorted(xs)
    if not ys: return None
    pos=(len(ys)-1)*q
    lo=int(math.floor(pos)); hi=int(math.ceil(pos))
    return ys[lo] if lo==hi else ys[lo]+(ys[hi]-ys[lo])*(pos-lo)

def main(out,job_path):
    try:
        cfg=json.loads(Path(job_path).read_text())
        if cfg.get('object_id')!=OBJECT_ID: raise ValueError('object_id mismatch')
        snap,snap_sha=load_snapshot()
        trades=snap.get('trades')
        if not isinstance(trades,list): raise ValueError('snapshot trades missing')

        base=[]; exclusions=Counter()
        for t in trades:
            if t.get('research_group')!='core' or t.get('is_experimental'):
                exclusions['not_core_or_experimental']+=1; continue
            if t.get('status') not in ('closed','expired') or t.get('outcome_group') not in ('positive','negative'):
                exclusions['not_completed_binary_outcome']+=1; continue
            try: pp=float(t.get('profit_percent'))
            except (TypeError,ValueError): exclusions['missing_profit_percent']+=1; continue
            if not math.isfinite(pp) or pp==0:
                exclusions['invalid_or_zero_profit_percent']+=1; continue
            strategy=str(t.get('strategy') or '').strip()
            if not strategy:
                exclusions['missing_strategy']+=1; continue
            ts=parse_ts(t.get('closed_at'))
            base.append({'id':str(t.get('id')),'strategy':strategy,'closed_at':ts,'profit_percent':pp,
                         'symbol':str(t.get('symbol') or 'UNKNOWN'),'market':str(t.get('market') or 'UNKNOWN'),
                         'timeframe':str(t.get('timeframe') or 'UNKNOWN')})

        valid=[r for r in base if r['closed_at'] is not None]
        ts_cov=(len(valid)/len(base)) if base else 0.0
        valid.sort(key=lambda r:(r['closed_at'],r['id']))
        by=defaultdict(list)
        for r in valid: by[r['strategy']].append(r)

        primary={}
        descriptive_confounded={}
        for s,rows in sorted(by.items()):
            if len(rows)<MIN_PER_STRATEGY: continue
            mid=len(rows)//2
            first,second=rows[:mid],rows[mid:]
            if len(first)<MIN_HALF or len(second)<MIN_HALF: continue
            rec={'strategy':s,'n':len(rows),'first_n':len(first),'second_n':len(second),
                 'first_mean_pp':mean([x['profit_percent'] for x in first]),
                 'second_mean_pp':mean([x['profit_percent'] for x in second]),
                 'first_median_pp':statistics.median([x['profit_percent'] for x in first]),
                 'second_median_pp':statistics.median([x['profit_percent'] for x in second]),
                 'full_mean_pp':mean([x['profit_percent'] for x in rows])}
            if s in KNOWN_CONFOUNDED_STRATEGIES:
                descriptive_confounded[s]=rec
            else:
                primary[s]=(rec,first,second)

        primary_strategies=sorted(primary)
        discovery_negative=[s for s in primary_strategies if primary[s][0]['first_mean_pp']<0]
        validated_negative=[s for s in discovery_negative if primary[s][0]['second_mean_pp']<0]
        discovery_positive=[s for s in primary_strategies if primary[s][0]['first_mean_pp']>0]
        positive_stable=[s for s in discovery_positive if primary[s][0]['second_mean_pp']>0]

        contract={
            'question':'Do negative strategy marginal returns discovered in an earlier chronological half persist in the later half, after excluding known lifecycle-confounded strategy evidence from the primary test?',
            'design':'Within each sufficiently represented strategy, deterministic chronological half split by closed_at,id. Discovery-negative is first-half mean profit_percent < 0. Primary validation is the equal-strategy mean of second-half means for discovery-negative strategies. A deterministic within-strategy bootstrap of second-half trades estimates a 95% CI for that validation basket.',
            'anti_leakage':'Strategy selection uses first-half outcomes only. Second-half outcomes are used only for validation. No named losing strategy is selected from full-snapshot results. Breaker is excluded from primary inference because an independently established entry-zone validity confound exists; it remains descriptive.',
            'minimums':{'eligible_timestamped_trades':MIN_TOTAL_TRADES,'primary_strategies':MIN_STRATEGIES,'trades_per_strategy':MIN_PER_STRATEGY,'trades_per_half':MIN_HALF,'timestamp_coverage':MIN_TS_COVERAGE,'discovery_negative_strategies':MIN_DISCOVERY_NEGATIVE},
            'bootstrap':{'iterations':BOOTSTRAPS,'seed':SEED,'weighting':'equal strategy weight; resample second-half trades within each discovery-negative strategy'},
            'terminal_logic':{
                'PERSISTENT-NEGATIVE-MARGINALS':'upper bound of frozen 95% bootstrap CI for equal-strategy second-half mean is < 0',
                'NO-PERSISTENT-NEGATIVE-MARGINALS':'lower bound of frozen 95% bootstrap CI is >= 0',
                'MIXED-MARGINAL-STABILITY':'95% CI spans 0',
                'BLOCKED-EVIDENCE':'any frozen breadth/timestamp/discovery gate fails or execution/data failure occurs'
            },
            'interpretation':'Historical edge-stability evidence only. No sizing, allocation, leverage, capital rule, canonical promotion, or causal regime claim follows.'
        }
        counts={'eligible_before_timestamp':len(base),'eligible_timestamped':len(valid),'timestamp_coverage':ts_cov,
                'primary_strategies':len(primary_strategies),'discovery_negative_strategies':len(discovery_negative),
                'known_confounded_strategies_present':sorted(descriptive_confounded),'exclusions':dict(exclusions)}
        common={'snapshot':{'captured_at_utc':snap.get('captured_at_utc'),'source':snap.get('source'),'source_revision':snap.get('source_revision'),'snapshot_sha256':snap_sha},
                'contract':contract,'counts':counts}

        if len(valid)<MIN_TOTAL_TRADES or len(primary_strategies)<MIN_STRATEGIES or ts_cov<MIN_TS_COVERAGE or len(discovery_negative)<MIN_DISCOVERY_NEGATIVE:
            emit(out,'BLOCKED-EVIDENCE',reason='frozen sample/strategy/timestamp/discovery-negative gate not met',
                 strategy_breakdown=[primary[s][0] for s in primary_strategies],
                 confounded_strategy_breakdown=list(descriptive_confounded.values()),**common); return

        second_means=[primary[s][0]['second_mean_pp'] for s in discovery_negative]
        observed_equal_strategy_mean=mean(second_means)
        rng=random.Random(SEED)
        boot=[]
        for _ in range(BOOTSTRAPS):
            strat_means=[]
            for s in discovery_negative:
                vals=[x['profit_percent'] for x in primary[s][2]]
                sample=[vals[rng.randrange(len(vals))] for _ in range(len(vals))]
                strat_means.append(mean(sample))
            boot.append(mean(strat_means))
        lo=pctile(boot,0.025); hi=pctile(boot,0.975)
        if hi < 0:
            state='PERSISTENT-NEGATIVE-MARGINALS'
            reason='later-half equal-strategy mean for first-half negative strategies remains below zero at the frozen 95% bootstrap interval'
        elif lo >= 0:
            state='NO-PERSISTENT-NEGATIVE-MARGINALS'
            reason='later-half equal-strategy mean for first-half negative strategies is non-negative at the frozen 95% bootstrap interval'
        else:
            state='MIXED-MARGINAL-STABILITY'
            reason='later-half validation interval spans zero; persistence is not resolved'

        details=[primary[s][0] for s in primary_strategies]
        evidence={
            **common,
            'primary':{
                'discovery_negative_strategies':discovery_negative,
                'validated_negative_strategies':validated_negative,
                'negative_sign_retention_rate':len(validated_negative)/len(discovery_negative),
                'validation_equal_strategy_second_half_mean_pp':observed_equal_strategy_mean,
                'bootstrap_ci95_pp':[lo,hi],
                'discovery_positive_strategies':discovery_positive,
                'positive_sign_retention_rate':(len(positive_stable)/len(discovery_positive)) if discovery_positive else None
            },
            'strategy_breakdown':details,
            'confounded_strategy_breakdown':list(descriptive_confounded.values())
        }
        ep=Path(out); ep.mkdir(parents=True,exist_ok=True)
        raw=json.dumps(evidence,indent=2,sort_keys=True)
        (ep/'marginal_edge_stability_evidence.json').write_text(raw)
        ev_sha=hashlib.sha256(raw.encode()).hexdigest()
        emit(out,state,reason=reason,evidence_file='marginal_edge_stability_evidence.json',evidence_sha256=ev_sha,
             discovery_negative_strategies=discovery_negative,validated_negative_strategies=validated_negative,
             negative_sign_retention_rate=len(validated_negative)/len(discovery_negative),
             validation_equal_strategy_second_half_mean_pp=observed_equal_strategy_mean,
             bootstrap_ci95_pp=[lo,hi],**common)
    except Exception as e:
        emit(out,'BLOCKED-EVIDENCE',reason=f'execution/data failure: {e!r}',parameter_tuning=False)

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--job',required=True)
    ap.add_argument('--output',required=True)
    a=ap.parse_args()
    main(a.output,a.job)
