import argparse,json,subprocess,urllib.request
from datetime import datetime,timezone
from pathlib import Path

O='SL-VAL-TRENDPULLBACK-MOMENTUM-CONFIRM-001'
REPO='/home/ubuntu/MarketHunter'
SNAP='data/outcome_intelligence/latest/trades.json'
BRANCH='outcome-intelligence-snapshots'
HOUR=3600000

def emit(out,state,**x):
 p=Path(out);p.mkdir(parents=True,exist_ok=True)
 (p/'terminal_result.json').write_text(json.dumps({'object_id':O,'terminal_state':state,**x},indent=2,sort_keys=True))

def load_snapshot():
 subprocess.run(['git','-C',REPO,'fetch','origin',BRANCH],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=90)
 raw=subprocess.run(['git','-C',REPO,'show',f'FETCH_HEAD:{SNAP}'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30).stdout
 return json.loads(raw)

def ms(v):
 if isinstance(v,(int,float)):return int(v)
 d=datetime.fromisoformat(str(v).replace('Z','+00:00'))
 if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
 return int(d.timestamp()*1000)

def klines(symbol,interval,start,end,limit=1500):
 url=f'https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&startTime={start}&endTime={end}&limit={limit}'
 with urllib.request.urlopen(url,timeout=30) as r: rows=json.loads(r.read())
 return [{'t':int(x[0]),'close_t':int(x[6]),'h':float(x[2]),'l':float(x[3]),'c':float(x[4])} for x in rows]

def completed(rows,entry_ms):
 return [x for x in rows if x['close_t'] < entry_ms]

def atr(b,n=14):
 if len(b)<n+1:return None
 tr=[]
 for i in range(1,len(b)):
  x,p=b[i],b[i-1]['c'];tr.append(max(x['h']-x['l'],abs(x['h']-p),abs(x['l']-p)))
 return sum(tr[-n:])/n

def ret(b,n):
 if len(b)<n+1:return None
 return b[-1]['c']/b[-1-n]['c']-1

def context(symbol,entry_ms,direction):
 h1=completed(klines(symbol,'1h',entry_ms-240*HOUR,entry_ms-1),entry_ms)
 h4=completed(klines(symbol,'4h',entry_ms-90*4*HOUR,entry_ms-1),entry_ms)
 if len(h1)<73 or len(h4)<25:return None
 a=atr(h1);c=h1[-1]['c'];r24=ret(h1,24);r72=ret(h1,72);r4=ret(h4,24)
 if None in (a,r24,r72,r4) or not a or not c:return None
 ht='UP' if r4>0 else 'DOWN' if r4<0 else 'FLAT'
 align=(direction=='LONG' and ht=='UP') or (direction=='SHORT' and ht=='DOWN')
 signed24=r24 if direction=='LONG' else -r24
 signed72=r72 if direction=='LONG' else -r72
 return {'pre_entry_return_24h':r24,'pre_entry_return_72h':r72,'directional_return_24h':signed24,'directional_return_72h':signed72,'impulse_atr_units':abs(r24)/(a/c),'htf_trend':ht,'trend_aligned':align}

def mean(xs):return sum(xs)/len(xs) if xs else None
def median(xs):
 s=sorted(xs);n=len(s)
 return None if not n else s[n//2] if n%2 else (s[n//2-1]+s[n//2])/2

def summary(rows,g):
 z=[r for r in rows if r['group']==g]
 keys=['pre_entry_return_24h','pre_entry_return_72h','directional_return_24h','directional_return_72h','impulse_atr_units']
 return {'n':len(z),'trend_aligned_rate':mean([1.0 if r['context']['trend_aligned'] else 0.0 for r in z]),**{k:{'mean':mean([r['context'][k] for r in z]),'median':median([r['context'][k] for r in z])} for k in keys}}

def main(out,job):
 try:
  cfg=json.loads(Path(job).read_text())
  if cfg.get('object_id')!=O:raise ValueError('object_id')
  snap=load_snapshot()
  eligible=[t for t in snap['trades'] if t.get('strategy')=='TrendPullback' and t.get('market')=='futures' and t.get('timeframe')=='1h' and t.get('status') in ('closed','expired') and isinstance(t.get('profit_percent'),(int,float)) and isinstance(t.get('max_profit_percent'),(int,float)) and t.get('entry_price') and t.get('opened_at')]
  rows=[];missing=[]
  for t in eligible:
   mfe=float(t['max_profit_percent']);p=float(t['profit_percent'])
   g='weak' if mfe<2.0 and p<0 else 'confirmed_move' if mfe>=2.0 else 'other'
   if g=='other':continue
   try:c=context(t['symbol'],ms(t['opened_at']),str(t.get('direction','')).upper())
   except Exception as e:c=None;missing.append({'id':t.get('id'),'symbol':t.get('symbol'),'reason':repr(e)})
   if c:rows.append({'id':t.get('id'),'symbol':t.get('symbol'),'direction':t.get('direction'),'profit_percent':p,'mfe_percent':mfe,'group':g,'context':c})
  weak=sum(r['group']=='weak' for r in rows);conf=sum(r['group']=='confirmed_move' for r in rows)
  if weak<3 or conf<3:return emit(out,'BLOCKED-EVIDENCE',eligible_n=len(eligible),reconstructed_n=len(rows),weak_n=weak,confirmed_move_n=conf,missing=missing[:30],reason='insufficient comparison groups')
  sw,sc=summary(rows,'weak'),summary(rows,'confirmed_move')
  effects={}
  for k in ('pre_entry_return_24h','pre_entry_return_72h','directional_return_24h','directional_return_72h','impulse_atr_units'):
   effects[k]={'mean_difference_weak_minus_confirmed':sw[k]['mean']-sc[k]['mean'],'median_difference_weak_minus_confirmed':sw[k]['median']-sc[k]['median']}
  # This object is descriptive by design. No post-hoc cutoff or automatic evidence claim.
  emit(out,'MOMENTUM-CONTEXT-NOT-SUPPORTED',snapshot={'captured_at_utc':snap.get('captured_at_utc'),'source_revision':snap.get('source_revision'),'total':snap.get('total')},eligible_n=len(eligible),reconstructed_n=len(rows),weak_n=weak,confirmed_move_n=conf,momentum_distribution_by_group={'weak':sw,'confirmed_move':sc},effect_differences=effects,counterexamples=rows,interpretation='DESCRIPTIVE-ONLY: differences require a separately pre-specified confirmatory rule/effect criterion before SUPPORTED can be assigned.',limitations=['Only candles with close_time strictly before entry are used.','No momentum cutoff is selected from this sample.','Observed entries/outcomes are unchanged; this does not simulate a new entry filter.'])
 except Exception as e:emit(out,'BLOCKED-EVIDENCE',reason=repr(e))

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
