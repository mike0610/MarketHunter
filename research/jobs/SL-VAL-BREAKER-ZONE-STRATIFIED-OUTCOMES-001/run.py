import argparse,json,random,re,statistics,subprocess
from pathlib import Path

OBJECT_ID='SL-VAL-BREAKER-ZONE-STRATIFIED-OUTCOMES-001'
REPO='/home/ubuntu/MarketHunter'
SNAP_COMMIT='3035e381ca64333c6c744b667f461ce9ce68c5cc'
SNAP='data/outcome_intelligence/latest/trades.json'
ZONE_RE=re.compile(r'Zone\s+([0-9.eE+-]+)-([0-9.eE+-]+)',re.I)
MIN_GROUP_N=8
MIN_OUTCOME_COVERAGE=0.80
EQUIV_BAND_PP=0.50
BOOT_N=20000
SEED=20260911

def emit(out,state,**payload):
 p=Path(out);p.mkdir(parents=True,exist_ok=True)
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

def percentile(xs,q):
 ys=sorted(xs)
 if not ys:return None
 k=(len(ys)-1)*q
 lo=int(k);hi=min(lo+1,len(ys)-1);w=k-lo
 return ys[lo]*(1-w)+ys[hi]*w

def bootstrap_diff(inside,outside):
 rng=random.Random(SEED);vals=[]
 for _ in range(BOOT_N):
  a=[inside[rng.randrange(len(inside))] for _ in range(len(inside))]
  b=[outside[rng.randrange(len(outside))] for _ in range(len(outside))]
  vals.append(statistics.fmean(b)-statistics.fmean(a))
 return percentile(vals,0.025),percentile(vals,0.975)

def summary(xs):
 return {'n':len(xs),'mean_pp':statistics.fmean(xs) if xs else None,'median_pp':statistics.median(xs) if xs else None,'loss_rate':sum(x<0 for x in xs)/len(xs) if xs else None,'sum_pp':sum(xs) if xs else None}

def main(out,job):
 try:
  cfg=json.loads(Path(job).read_text())
  if cfg.get('object_id')!=OBJECT_ID: raise ValueError('object_id mismatch')
  snap=load_snapshot(); parsed=[]
  for t in snap.get('trades',[]):
   if str(t.get('strategy','')).strip().lower()!='breaker' or t.get('market') not in ('spot','futures'): continue
   z=zone_from_trade(t); entry=t.get('entry_price')
   if not z or not isinstance(entry,(int,float)) or not entry: continue
   lo,hi=z;inside=lo<=float(entry)<=hi
   p=t.get('profit_percent')
   parsed.append({'id':t.get('id'),'inside':inside,'profit_percent':float(p) if isinstance(p,(int,float)) else None,'symbol':t.get('symbol'),'market':t.get('market'),'direction':t.get('direction'),'status':t.get('status'),'close_reason':t.get('close_reason')})
  outcomes=[r for r in parsed if r['profit_percent'] is not None]
  coverage=len(outcomes)/len(parsed) if parsed else 0.0
  inside=[r['profit_percent'] for r in outcomes if r['inside']]
  outside=[r['profit_percent'] for r in outcomes if not r['inside']]
  base={'snapshot_commit':SNAP_COMMIT,'snapshot_captured_at_utc':snap.get('captured_at_utc'),'snapshot_source_revision':snap.get('source_revision'),'snapshot_total':snap.get('total'),'zone_parsed_n':len(parsed),'numeric_outcome_n':len(outcomes),'outcome_coverage':coverage,'inside':summary(inside),'outside':summary(outside),'frozen_contract':{'min_group_n':MIN_GROUP_N,'min_outcome_coverage':MIN_OUTCOME_COVERAGE,'equivalence_band_pp':EQUIV_BAND_PP,'bootstrap_n':BOOT_N,'seed':SEED,'estimand':'outside_mean_profit_percent - inside_mean_profit_percent'},'parameter_tuning':False}
  if len(parsed)==0 or coverage<MIN_OUTCOME_COVERAGE or len(inside)<MIN_GROUP_N or len(outside)<MIN_GROUP_N:
   emit(out,'BLOCKED-EVIDENCE',**base,reason='frozen sufficiency gate failed; no effect inference',retest='Reopen only on a newer immutable cohort satisfying the same frozen gates.')
   return
  diff=statistics.fmean(outside)-statistics.fmean(inside);lo,hi=bootstrap_diff(inside,outside)
  loss_diff=(sum(x<0 for x in outside)/len(outside))-(sum(x<0 for x in inside)/len(inside))
  base.update({'difference_mean_pp':diff,'difference_loss_rate':loss_diff,'bootstrap_95_ci_pp':[lo,hi]})
  if hi < -EQUIV_BAND_PP or lo > EQUIV_BAND_PP:
   state='STRATIFIED-DIFFERENCE-SUPPORTED';reason='95% bootstrap CI lies wholly outside the frozen practical-equivalence band.'
  elif lo >= -EQUIV_BAND_PP and hi <= EQUIV_BAND_PP:
   state='NO-MATERIAL-DIFFERENCE';reason='95% bootstrap CI lies wholly inside the frozen practical-equivalence band.'
  else:
   state='INCONCLUSIVE';reason='95% bootstrap CI overlaps the frozen practical-equivalence boundary.'
  emit(out,state,**base,reason=reason,interpretation='Entry-zone validity is a stratification variable only if this frozen outcome contrast supports a material difference. This test does not establish Breaker edge, causality, invalidation-path quality, sizing, leverage, or allocation.')
 except Exception as e:
  emit(out,'PROVIDER-BLOCKED',snapshot_commit=SNAP_COMMIT,reason=repr(e),parameter_tuning=False)

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
