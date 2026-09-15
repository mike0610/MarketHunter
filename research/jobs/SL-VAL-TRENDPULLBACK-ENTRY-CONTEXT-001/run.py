import argparse,json,math,subprocess,urllib.request
from datetime import datetime,timezone
from pathlib import Path

O='SL-VAL-TRENDPULLBACK-ENTRY-CONTEXT-001'
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
 return [{'t':int(x[0]),'o':float(x[1]),'h':float(x[2]),'l':float(x[3]),'c':float(x[4])} for x in rows]

def atr(b,n=14):
 if len(b)<n+1:return None
 tr=[]
 for i in range(1,len(b)):
  x,p=b[i],b[i-1]['c'];tr.append(max(x['h']-x['l'],abs(x['h']-p),abs(x['l']-p)))
 return sum(tr[-n:])/n

def slope_return(b,n):
 if len(b)<n+1:return None
 return b[-1]['c']/b[-1-n]['c']-1

def context(symbol,entry_ms,direction):
 # Only completed candles before entry. Fetch enough 1h/4h history for frozen descriptive features.
 h1=klines(symbol,'1h',entry_ms-220*HOUR,entry_ms-1)
 h4=klines(symbol,'4h',entry_ms-80*4*HOUR,entry_ms-1)
 if len(h1)<60 or len(h4)<30:return None
 a=atr(h1,14);c=h1[-1]['c']
 r24=slope_return(h1,24);r72=slope_return(h1,72);r4=slope_return(h4,24)
 if None in (a,r24,r72,r4) or not a:return None
 ht='UP' if r4>0 else 'DOWN' if r4<0 else 'FLAT'
 align=(direction=='LONG' and ht=='UP') or (direction=='SHORT' and ht=='DOWN')
 # Pullback depth against the 72h directional range, descriptive and frozen.
 w=h1[-72:];hi=max(x['h'] for x in w);lo=min(x['l'] for x in w);rng=max(hi-lo,1e-12)
 depth=(hi-c)/rng if direction=='LONG' else (c-lo)/rng
 # Simple causal structure state from last 24h high/low versus preceding 24h high/low.
 a24=h1[-24:];p24=h1[-48:-24]
 ah,al=max(x['h'] for x in a24),min(x['l'] for x in a24);ph,pl=max(x['h'] for x in p24),min(x['l'] for x in p24)
 structure='HH_HL' if ah>ph and al>pl else 'LH_LL' if ah<ph and al<pl else 'MIXED'
 impulse=abs(r24)/(a/c) if a and c else None
 return {'htf_trend':ht,'trend_aligned':align,'pullback_depth':depth,'structure':structure,'atr_pct':a/c,'pre_entry_return_24h':r24,'pre_entry_return_72h':r72,'htf_return_4d':r4,'impulse_atr_units':impulse}

def mean(xs):return sum(xs)/len(xs) if xs else None

def summarize(rows,group):
 z=[r for r in rows if r['group']==group]
 nums=['pullback_depth','atr_pct','pre_entry_return_24h','pre_entry_return_72h','htf_return_4d','impulse_atr_units']
 return {'n':len(z),'trend_aligned_rate':mean([1.0 if r['context']['trend_aligned'] else 0.0 for r in z]),'htf_trend_counts':{k:sum(r['context']['htf_trend']==k for r in z) for k in ('UP','DOWN','FLAT')},'structure_counts':{k:sum(r['context']['structure']==k for r in z) for k in ('HH_HL','LH_LL','MIXED')},**{k:mean([r['context'][k] for r in z if r['context'][k] is not None]) for k in nums}}

def main(out,job):
 try:
  cfg=json.loads(Path(job).read_text())
  if cfg.get('job_id')!=O:raise ValueError('job_id')
  snap=load_snapshot();ts=snap['trades']
  eligible=[t for t in ts if t.get('strategy')=='TrendPullback' and t.get('market')=='futures' and t.get('timeframe')=='1h' and t.get('status') in ('closed','expired') and isinstance(t.get('profit_percent'),(int,float)) and t.get('entry_price') and t.get('opened_at')]
  rows=[];missing=[]
  for t in eligible:
   mfe=t.get('max_profit_percent')
   if not isinstance(mfe,(int,float)):
    missing.append({'id':t.get('id'),'symbol':t.get('symbol'),'reason':'missing_mfe'});continue
   group='weak' if mfe<2.0 and float(t['profit_percent'])<0 else 'confirmed_move' if mfe>=2.0 else 'other'
   if group=='other':continue
   try:c=context(t['symbol'],ms(t['opened_at']),str(t.get('direction','')).upper())
   except Exception as e:c=None;missing.append({'id':t.get('id'),'symbol':t.get('symbol'),'reason':repr(e)})
   if c:rows.append({'id':t.get('id'),'symbol':t.get('symbol'),'direction':t.get('direction'),'profit_percent':t.get('profit_percent'),'mfe_percent':mfe,'group':group,'context':c})
  weak=sum(r['group']=='weak' for r in rows);conf=sum(r['group']=='confirmed_move' for r in rows)
  if weak<3 or conf<3:return emit(out,'BLOCKED-EVIDENCE',eligible_n=len(eligible),reconstructed_n=len(rows),weak_n=weak,confirmed_move_n=conf,missing=missing[:30],reason='insufficient comparison groups')
  sw=summarize(rows,'weak');sc=summarize(rows,'confirmed_move')
  diffs={k:(sw[k]-sc[k]) for k in ('trend_aligned_rate','pullback_depth','atr_pct','pre_entry_return_24h','pre_entry_return_72h','htf_return_4d','impulse_atr_units') if sw.get(k) is not None and sc.get(k) is not None}
  ranked=sorted(diffs.items(),key=lambda kv:abs(kv[1]),reverse=True)
  emit(out,'ENTRY-CONTEXT-DIFFERENCE-SUPPORTED' if ranked else 'ENTRY-CONTEXT-DIFFERENCE-NOT-SUPPORTED',snapshot={'captured_at_utc':snap.get('captured_at_utc'),'source_revision':snap.get('source_revision'),'total':snap.get('total')},eligible_n=len(eligible),reconstructed_n=len(rows),weak_n=weak,confirmed_move_n=conf,context_distribution_by_group={'weak':sw,'confirmed_move':sc},largest_context_differences=ranked,candidate_entry_defects=ranked[:3],counterexamples=[r for r in rows if (r['group']=='weak' and r['context']['trend_aligned']) or (r['group']=='confirmed_move' and not r['context']['trend_aligned'])][:20],by_trade=rows,limitations=['Descriptive causal context reconstruction, not a new entry filter.','HTF trend uses completed 4h return sign; structure uses completed 1h 24h-vs-prior-24h ranges.','No thresholds are tuned from outcomes; any candidate defect requires a separate frozen validation before code change.'])
 except Exception as e:emit(out,'BLOCKED-EVIDENCE',reason=repr(e))

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
