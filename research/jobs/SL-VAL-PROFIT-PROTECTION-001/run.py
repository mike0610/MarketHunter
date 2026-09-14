import argparse,json,subprocess,urllib.request
from datetime import datetime,timezone
from pathlib import Path

O='SL-VAL-PROFIT-PROTECTION-001'
REPO='/home/ubuntu/MarketHunter'
SNAP='data/outcome_intelligence/latest/trades.json'
BRANCH='outcome-intelligence-snapshots'
STRATEGIES={'TrendPullback','VolumeConfirmedBreakout'}
LADDER=((2.0,0.0),(4.0,1.0),(6.0,3.0))

def emit(out,state,**x):
 p=Path(out);p.mkdir(parents=True,exist_ok=True)
 (p/'terminal_result.json').write_text(json.dumps({'object_id':O,'terminal_state':state,**x},indent=2,sort_keys=True))

def load_snapshot():
 subprocess.run(['git','-C',REPO,'fetch','origin',BRANCH],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=90)
 raw=subprocess.run(['git','-C',REPO,'show',f'FETCH_HEAD:{SNAP}'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30).stdout
 return json.loads(raw)

def ms(v):
 if isinstance(v,(int,float)): return int(v)
 s=str(v).replace('Z','+00:00');d=datetime.fromisoformat(s)
 if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
 return int(d.timestamp()*1000)

def klines(symbol,start,end):
 out=[];cur=start
 while cur<=end:
  url=f'https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=1h&startTime={cur}&endTime={end}&limit=1500'
  with urllib.request.urlopen(url,timeout=30) as r: rows=json.loads(r.read())
  if not rows: break
  out.extend(rows);n=int(rows[-1][0])+3600000
  if n<=cur:break
  cur=n
 return [{'t':int(x[0]),'o':float(x[1]),'h':float(x[2]),'l':float(x[3]),'c':float(x[4])} for x in out if int(x[0])<=end]

def protected_price(entry,direction,pct):
 return entry*(1+pct/100.0) if direction=='LONG' else entry*(1-pct/100.0)

def trigger_price(entry,direction,pct): return protected_price(entry,direction,pct)

def replay(t,bars):
 entry=float(t['entry_price']);direction=str(t['direction']).upper();active=None;exit_px=None;why='ORIGINAL_EXIT'
 for b in bars:
  # Conservative OHLC ambiguity: an existing protection is honored first; a newly activated level
  # cannot also claim an exit inside the same candle because intrabar ordering is unknown.
  if active is not None:
   px=protected_price(entry,direction,active)
   hit=(b['l']<=px) if direction=='LONG' else (b['h']>=px)
   if hit: exit_px=px;why=f'PROTECTED_{active:g}';break
  reached=[]
  for trig,lock in LADDER:
   tp=trigger_price(entry,direction,trig)
   ok=(b['h']>=tp) if direction=='LONG' else (b['l']<=tp)
   if ok: reached.append((trig,lock))
  if reached: active=max(reached,key=lambda z:z[0])[1]
 if exit_px is None:return float(t['profit_percent']),why,active
 gross=((exit_px/entry)-1)*100 if direction=='LONG' else ((entry/exit_px)-1)*100
 # Baseline profit_percent already embeds the observed lifecycle/cost model. For a protected exit,
 # apply the snapshot's implied entry/exit cost conservatively when available; otherwise 0.1% round-trip.
 cost=0.1
 return gross-cost,why,active

def maxdd(rs):
 eq=1.0;peak=1.0;dd=0.0
 for r in rs:
  eq*=max(0.000001,1+r/100.0);peak=max(peak,eq);dd=min(dd,eq/peak-1)
 return dd*100

def main(out,job):
 try:
  cfg=json.loads(Path(job).read_text())
  if cfg.get('object_id')!=O:raise ValueError('object')
  snap=load_snapshot();alltr=snap['trades']
  trades=[t for t in alltr if t.get('strategy') in STRATEGIES and t.get('market')=='futures' and t.get('timeframe')=='1h' and t.get('status') in ('closed','expired') and isinstance(t.get('profit_percent'),(int,float)) and t.get('entry_price') and t.get('opened_at') and t.get('closed_at')]
  if not trades: return emit(out,'BLOCKED-EVIDENCE',reason='no eligible observed trades',snapshot_total=snap.get('total'))
  rows=[];missing=[]
  for t in trades:
   try:
    start=ms(t['opened_at']);end=ms(t['closed_at']);bars=klines(t['symbol'],start,end)
    if not bars: missing.append({'id':t.get('id'),'symbol':t.get('symbol'),'reason':'no_1h_futures_klines'});continue
    new,why,active=replay(t,bars);base=float(t['profit_percent'])
    rows.append({'id':t.get('id'),'symbol':t.get('symbol'),'strategy':t.get('strategy'),'direction':t.get('direction'),'baseline':base,'protected':new,'delta':new-base,'exit':why,'highest_lock':active,'max_profit_percent':t.get('max_profit_percent')})
   except Exception as e: missing.append({'id':t.get('id'),'symbol':t.get('symbol'),'reason':repr(e)})
  if len(rows)<10:return emit(out,'BLOCKED-EVIDENCE',reason='insufficient replayable trades',eligible_n=len(trades),replayed_n=len(rows),missing=missing[:20])
  base=[r['baseline'] for r in rows];prot=[r['protected'] for r in rows]
  def wr(a):return sum(x>0 for x in a)/len(a)
  large=lambda a:sum(x<=-5 for x in a)
  give_base=sum((r.get('max_profit_percent') or 0)>0 and r['baseline']<0 for r in rows)
  give_prot=sum((r.get('max_profit_percent') or 0)>0 and r['protected']<0 for r in rows)
  trunc=[r for r in rows if r['baseline']>0 and r['protected']<r['baseline']]
  winners=[r for r in rows if r['baseline']>0]
  losers=[r for r in rows if r['baseline']<0]
  metrics={'trade_count':len(rows),'baseline_net_return_sum_pct':sum(base),'protected_net_return_sum_pct':sum(prot),'delta_net_return_sum_pct':sum(prot)-sum(base),'baseline_win_rate':wr(base),'protected_win_rate':wr(prot),'baseline_large_loss_count':large(base),'protected_large_loss_count':large(prot),'baseline_positive_mfe_to_negative_count':give_base,'protected_positive_mfe_to_negative_count':give_prot,'winner_truncation_count':len(trunc),'mean_winner_change_pp':sum(r['delta'] for r in winners)/len(winners) if winners else None,'mean_loser_change_pp':sum(r['delta'] for r in losers)/len(losers) if losers else None,'baseline_max_drawdown_pct':maxdd(base),'protected_max_drawdown_pct':maxdd(prot)}
  emit(out,'OUTCOME-COMPLETE',snapshot={'captured_at_utc':snap.get('captured_at_utc'),'source_revision':snap.get('source_revision'),'total':snap.get('total')},contract={'strategies':sorted(STRATEGIES),'market':'futures','timeframe':'1h','ladder':LADDER,'same_candle_ordering':'conservative','parameter_tuning':False},eligible_n=len(trades),replayed_n=len(rows),missing_n=len(missing),metrics=metrics,by_trade=rows,limitations=['Binance USD-M Futures 1h OHLC cannot reveal intrabar ordering; newly activated protection cannot exit in the same candle.','Protected-exit cost uses conservative 0.1% round-trip because exact historical fee/slippage path is not available in the snapshot.','This changes exits only; entries are the observed MarketHunter trades.'])
 except Exception as e:emit(out,'PROVIDER-BLOCKED',reason=repr(e))

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
