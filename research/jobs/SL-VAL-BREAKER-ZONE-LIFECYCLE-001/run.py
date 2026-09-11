import argparse,json,re,subprocess
from pathlib import Path

OBJECT_ID='SL-VAL-BREAKER-ZONE-LIFECYCLE-001'
REPO='/home/ubuntu/MarketHunter'
BRANCH='outcome-intelligence-snapshots'
SNAP='data/outcome_intelligence/latest/trades.json'
ZONE_RE=re.compile(r'Zone\s+([0-9.eE+-]+)-([0-9.eE+-]+)',re.I)

def emit(out,state,**payload):
 p=Path(out);p.mkdir(parents=True,exist_ok=True)
 (p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':state,**payload},indent=2,sort_keys=True))

def load_snapshot():
 subprocess.run(['git','-C',REPO,'fetch','origin',BRANCH],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=90)
 raw=subprocess.run(['git','-C',REPO,'show',f'FETCH_HEAD:{SNAP}'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30).stdout
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
  if json.loads(Path(job).read_text()).get('object_id')!=OBJECT_ID: raise ValueError('object')
  snap=load_snapshot()
  trades=[t for t in snap.get('trades',[]) if str(t.get('strategy','')).strip().lower()=='breaker' and t.get('market') in ('spot','futures')]
  rows=[]
  parsed=0;inside=0;outside=0
  side_counts={'LONG':0,'SHORT':0}
  outside_loss_sum=0.0;inside_loss_sum=0.0
  for t in trades:
   z=zone_from_trade(t)
   if not z or not isinstance(t.get('entry_price'),(int,float)): continue
   parsed+=1
   lo,hi=z;entry=float(t['entry_price']);direction=str(t.get('direction') or '').upper();side_counts[direction]=side_counts.get(direction,0)+1
   is_inside=lo<=entry<=hi
   if is_inside: inside+=1
   else: outside+=1
   p=t.get('profit_percent')
   if isinstance(p,(int,float)) and p<0:
    if is_inside: inside_loss_sum+=float(p)
    else: outside_loss_sum+=float(p)
   dist=0.0
   if entry<lo: dist=(lo-entry)/entry*100 if entry else None
   elif entry>hi: dist=(entry-hi)/entry*100 if entry else None
   rows.append({'id':t.get('id'),'symbol':t.get('symbol'),'market':t.get('market'),'timeframe':t.get('timeframe'),'direction':direction,'entry_price':entry,'zone_low':lo,'zone_high':hi,'entry_inside_zone':is_inside,'outside_distance_percent':dist,'profit_percent':p,'close_reason':t.get('close_reason'),'status':t.get('status')})
  rows.sort(key=lambda x: (x['entry_inside_zone'], -(x['outside_distance_percent'] or 0)))
  outside_rows=[x for x in rows if not x['entry_inside_zone']]
  verdict='SUPPORTED' if parsed>=5 and outside>=1 else ('NOT-SUPPORTED' if parsed>=5 and outside==0 else 'BLOCKED-EVIDENCE')
  emit(out,'OUTCOME-COMPLETE',snapshot={'captured_at_utc':snap.get('captured_at_utc'),'source_revision':snap.get('source_revision'),'total':snap.get('total')},scope={'breaker_trades':len(trades),'zone_parsed':parsed},summary={'inside_entry_n':inside,'outside_entry_n':outside,'outside_entry_rate':outside/parsed if parsed else None,'side_counts':side_counts,'outside_entry_negative_return_sum':outside_loss_sum,'inside_entry_negative_return_sum':inside_loss_sum},worst_outside_examples=outside_rows[:20],terminal_verdict=verdict,interpretation='Tests only the historical entry-zone defect. It does not claim invalidation-exit performance because completed-candle path data is not present in the trade snapshot.',parameter_tuning=False)
 except Exception as e:
  emit(out,'PROVIDER-BLOCKED',reason=repr(e),parameter_tuning=False)

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
