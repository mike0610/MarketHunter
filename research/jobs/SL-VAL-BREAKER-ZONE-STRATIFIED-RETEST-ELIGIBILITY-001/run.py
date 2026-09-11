import argparse,json,re,subprocess
from pathlib import Path

OBJECT_ID='SL-VAL-BREAKER-ZONE-STRATIFIED-RETEST-ELIGIBILITY-001'
REPO='/home/ubuntu/MarketHunter'
SNAP_COMMIT='614fd31472c9fc616cdee4a068609e6def67cb77'
SNAP='data/outcome_intelligence/latest/trades.json'
ZONE_RE=re.compile(r'Zone\s+([0-9.eE+-]+)\s*-\s*([0-9.eE+-]+)',re.I)
MIN_GROUP_N=8
MIN_OUTCOME_COVERAGE=0.80

def emit(out,state,**payload):
    p=Path(out); p.mkdir(parents=True,exist_ok=True)
    (p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':state,**payload},indent=2,sort_keys=True))

def load_snapshot():
    subprocess.run(['git','-C',REPO,'fetch','origin','outcome-intelligence-snapshots'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=90)
    subprocess.run(['git','-C',REPO,'cat-file','-e',SNAP_COMMIT+'^{commit}'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=15)
    raw=subprocess.run(['git','-C',REPO,'show',f'{SNAP_COMMIT}:{SNAP}'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30).stdout
    return json.loads(raw)

def zone_from_trade(t):
    for r in (t.get('reasons') or []):
        m=ZONE_RE.search(str(r))
        if m:
            a,b=map(float,m.groups())
            return min(a,b),max(a,b)
    return None

def main(out,job):
    try:
        cfg=json.loads(Path(job).read_text())
        if cfg.get('object_id')!=OBJECT_ID:
            raise ValueError('object_id mismatch')
        snap=load_snapshot()
        parsed=[]
        for t in snap.get('trades',[]):
            if str(t.get('strategy','')).strip().lower()!='breaker' or t.get('market') not in ('spot','futures'):
                continue
            z=zone_from_trade(t); entry=t.get('entry_price')
            if not z or not isinstance(entry,(int,float)) or not entry:
                continue
            lo,hi=z
            p=t.get('profit_percent')
            parsed.append({
                'inside': lo <= float(entry) <= hi,
                'numeric_outcome': isinstance(p,(int,float)),
                'status': t.get('status'),
                'outcome_group': t.get('outcome_group')
            })
        outcomes=[r for r in parsed if r['numeric_outcome']]
        inside_n=sum(1 for r in outcomes if r['inside'])
        outside_n=sum(1 for r in outcomes if not r['inside'])
        coverage=(len(outcomes)/len(parsed)) if parsed else 0.0
        failed=[]
        if len(parsed)==0: failed.append('zone_parsed_n')
        if coverage < MIN_OUTCOME_COVERAGE: failed.append('outcome_coverage')
        if inside_n < MIN_GROUP_N: failed.append('inside_n')
        if outside_n < MIN_GROUP_N: failed.append('outside_n')
        base={
            'snapshot_commit': SNAP_COMMIT,
            'snapshot_captured_at_utc': snap.get('captured_at_utc'),
            'snapshot_source_revision': snap.get('source_revision'),
            'snapshot_total': snap.get('total'),
            'zone_parsed_n': len(parsed),
            'numeric_outcome_n': len(outcomes),
            'outcome_coverage': coverage,
            'inside_numeric_outcome_n': inside_n,
            'outside_numeric_outcome_n': outside_n,
            'failed_gates': failed,
            'frozen_contract': {
                'min_group_n': MIN_GROUP_N,
                'min_outcome_coverage': MIN_OUTCOME_COVERAGE,
                'parser_semantics': 'same Breaker strategy/market/Zone/entry classification as SL-VAL-BREAKER-ZONE-STRATIFIED-OUTCOMES-001'
            },
            'effect_inference_executed': False,
            'parameter_tuning': False
        }
        if failed:
            emit(out,'COHORT-STILL-INSUFFICIENT',**base,reason='newer immutable cohort still fails one or more unchanged frozen sufficiency gates',retest='Do not rerun the blocked effect test on this cohort. Reopen only on a materially newer immutable cohort satisfying all unchanged gates.')
        else:
            emit(out,'RETEST-ELIGIBLE',**base,reason='newer immutable cohort satisfies all unchanged frozen sufficiency gates',retest='A separate bounded object may rerun the previously frozen stratified effect test without changing thresholds, parser semantics, estimand, bootstrap count, seed, or practical-equivalence band.')
    except Exception as e:
        emit(out,'PROVIDER-BLOCKED',snapshot_commit=SNAP_COMMIT,reason=repr(e),effect_inference_executed=False,parameter_tuning=False)

if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('--job',required=True); a.add_argument('--output',required=True); q=a.parse_args(); main(q.output,q.job)
