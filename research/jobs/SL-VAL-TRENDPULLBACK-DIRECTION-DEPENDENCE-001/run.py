import argparse,json,subprocess,urllib.request
from datetime import datetime,timezone
from pathlib import Path

O='SL-VAL-TRENDPULLBACK-DIRECTION-DEPENDENCE-001'
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

def differences(rows):
 out={}
 for direction in ('LONG','SHORT'):
  z=[r for r in rows if r['direction']==direction]
  w=[r for r in z if r['group']=='weak'];c=[r for r in z if r['group']=='confirmed_move']
  if not w or not c:
   out[direction]={'status':'BLOCKED-EVIDENCE','weak_n':len(w),'confirmed_move_n':len(c),'reason':'missing within-direction comparison group'}
   continue
  keys=('directional_return_24h','directional_return_72h','impulse_atr_units')
  out[direction]={'status':'DESCRIPTIVE-ONLY','weak_n':len(w),'confirmed_move_n':len(c),'features':{k:{'weak_mean':mean([r['context'][k] for r in w]),'confirmed_mean':mean([r['context'][k] for r in c]),'weak_median':median([r['context'][k] for r in w]),'confirmed_median':median([r['context'][k] for r in c]),'median_difference_weak_minus_confirmed':median([r['context'][k] for r in w])-median([r['context'][k] for r in c])} for k in keys}}
 return out

def main(out,job):
 try:
  cfg=json.loads(Path(job).read_text())
  if cfg.get('object_id')!=O:raise ValueError('object_id')
  snap=load_snapshot()
  eligible=[t for t in snap['trades'] if t.get('strategy')=='TrendPullback' and t.get('market')=='futures' and t.get('timeframe')=='1h' and t.get('status') in ('closed','expired') and isinstance(t.get('profit_percent'),(int,float)) and isinstance(t.get('max_profit_percent'),(int,float)) and t.get('entry_price') and t.get('opened_at')]
  rows=[];missing=[]
  for t in eligible:
   mfe=float(t['max_profit_percent']);p=float(t['profit_percent'])
   group='weak' if mfe<2.0 and p<0 else 'confirmed_move' if mfe>=2.0 else 'other'
   if group=='other':continue
   direction=str(t.get('direction','')).upper()
   if direction not in ('LONG','SHORT'):
    missing.append({'id':t.get('id'),'reason':'invalid_direction'});continue
   try:
    entry_ms=ms(t['opened_at'])
    c=context(t['symbol'],entry_ms,direction)
   except Exception as e:
    c=None;missing.append({'id':t.get('id'),'symbol':t.get('symbol'),'reason':repr(e)})
   if c:rows.append({'id':t.get('id'),'symbol':t.get('symbol'),'entry_ms':entry_ms,'direction':direction,'group':group,'profit_percent':p,'mfe_percent':mfe,'context':c})
  rows.sort(key=lambda r:(r['entry_ms'],str(r['id'])))
  if not rows:return emit(out,'BLOCKED-EVIDENCE',eligible_trade_count=len(eligible),reconstructed_trade_count=0,missing=missing[:30],reason='no reconstructable trades')
  symbol_counts={s:sum(r['symbol']==s for r in rows) for s in sorted({r['symbol'] for r in rows})}
  repeated={s:n for s,n in symbol_counts.items() if n>1}
  overlap_pairs=[{'earlier_id':a['id'],'later_id':b['id'],'hours_apart':(b['entry_ms']-a['entry_ms'])/HOUR,'same_symbol':a['symbol']==b['symbol']} for i,a in enumerate(rows) for b in rows[i+1:] if b['entry_ms']-a['entry_ms']<72*HOUR]
  one_per_symbol=[];seen=set()
  for r in rows:
   if r['symbol'] not in seen:one_per_symbol.append(r);seen.add(r['symbol'])
  nonoverlap=[];last=None
  for r in rows:
   if last is None or r['entry_ms']-last>=72*HOUR:nonoverlap.append(r);last=r['entry_ms']
  full=differences(rows)
  state='DIRECTION-DEPENDENCE-AUDIT-COMPLETE' if any(x['status']=='DESCRIPTIVE-ONLY' for x in full.values()) else 'BLOCKED-EVIDENCE'
  emit(out,state,snapshot={'captured_at_utc':snap.get('captured_at_utc'),'source_revision':snap.get('source_revision')},eligible_trade_count=len(eligible),reconstructed_trade_count=len(rows),direction_group_counts={d:{g:sum(r['direction']==d and r['group']==g for r in rows) for g in ('weak','confirmed_move')} for d in ('LONG','SHORT')},direction_specific_momentum_distributions=full,repeated_symbol_counts=repeated,overlapping_window_counts={'window_hours':72,'pair_count':len(overlap_pairs),'pairs':overlap_pairs},dependence_sensitivity={'all_trades':full,'earliest_one_per_symbol':{'n':len(one_per_symbol),'direction_comparisons':differences(one_per_symbol)},'earliest_nonoverlapping_72h':{'n':len(nonoverlap),'direction_comparisons':differences(nonoverlap)}},counterexamples=[r for r in rows if r['group']=='confirmed_move' and r['profit_percent']<0],by_trade=rows,missing=missing[:30],limitations=['Descriptive audit, not a momentum entry filter or causal proof.','Earliest-per-symbol and earliest-nonoverlapping-72h are deterministic sensitivity checks, not independent validation samples.','Only candles fully closed before each entry are used.','Confirmed favorable excursion is not equivalent to realized profit.','No within-direction inference where either comparison group is absent.'])
 except Exception as e:emit(out,'BLOCKED-EVIDENCE',reason=repr(e))

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
