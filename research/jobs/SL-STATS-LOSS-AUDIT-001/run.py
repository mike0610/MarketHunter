import argparse,json,subprocess
from collections import defaultdict
from pathlib import Path
O='SL-STATS-LOSS-AUDIT-001'
REPO='/home/ubuntu/MarketHunter'
SNAP='data/outcome_intelligence/latest/trades.json'
BRANCH='outcome-intelligence-snapshots'
def emit(out,state,**x):
 p=Path(out);p.mkdir(parents=True,exist_ok=True);(p/'terminal_result.json').write_text(json.dumps({'object_id':O,'terminal_state':state,**x},indent=2,sort_keys=True))
def load_snapshot():
 subprocess.run(['git','-C',REPO,'fetch','origin',BRANCH],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=90)
 raw=subprocess.run(['git','-C',REPO,'show',f'FETCH_HEAD:{SNAP}'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30).stdout
 return json.loads(raw)
def main(out,job):
 try:
  if json.loads(Path(job).read_text()).get('object_id')!=O: raise ValueError('object')
  snap=load_snapshot();trades=snap['trades']
  crypto=[t for t in trades if t.get('market') in ('spot','futures')]
  done=[t for t in crypto if t.get('status') in ('closed','expired') and isinstance(t.get('profit_percent'),(int,float))]
  ranked=sorted(done,key=lambda t:t.get('profit_percent',0))
  fields=['id','symbol','market','timeframe','strategy','direction','status','outcome_group','outcome_type','close_reason','profit_percent','profit_amount','rr','max_drawdown_percent','max_profit_percent','entry_price','stop_loss','take_profit','probability','score','research_group','experiment_tag','opened_at','closed_at','reasons']
  worst=[{k:t.get(k) for k in fields} for t in ranked[:20]]
  g=defaultdict(list)
  for t in done:g[t.get('strategy') or 'UNKNOWN'].append(t)
  agg=[]
  for s,a in g.items():
   ps=[float(t.get('profit_percent',0)) for t in a]
   wins=sum(x>0 for x in ps);loss=sum(x<0 for x in ps);flat=sum(x==0 for x in ps)
   agg.append({'strategy':s,'n':len(a),'wins':wins,'losses':loss,'flat':flat,'win_rate':wins/len(a) if a else None,'sum_profit_percent':sum(ps),'mean_profit_percent':sum(ps)/len(ps) if ps else None,'worst_profit_percent':min(ps) if ps else None,'best_profit_percent':max(ps) if ps else None})
  agg.sort(key=lambda x:x['sum_profit_percent'])
  emit(out,'OUTCOME-COMPLETE',snapshot={'captured_at_utc':snap.get('captured_at_utc'),'source':snap.get('source'),'source_revision':snap.get('source_revision'),'total':snap.get('total')},scope={'markets':['spot','futures'],'completed_statuses':['closed','expired'],'completed_n':len(done)},worst_trades=worst,strategy_aggregate=agg)
 except Exception as e: emit(out,'PROVIDER-BLOCKED',reason=repr(e))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
# trigger: job.json present
