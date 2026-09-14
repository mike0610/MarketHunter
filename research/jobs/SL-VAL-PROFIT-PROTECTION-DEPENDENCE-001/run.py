import argparse,json,math,subprocess,urllib.request
from datetime import datetime,timezone
from pathlib import Path

O='SL-VAL-PROFIT-PROTECTION-DEPENDENCE-001'
REPO='/home/ubuntu/MarketHunter'; SNAP='data/outcome_intelligence/latest/trades.json'; BRANCH='outcome-intelligence-snapshots'
STRATEGIES={'TrendPullback','VolumeConfirmedBreakout'}; LADDER=((2.0,0.0),(4.0,1.0),(6.0,3.0))
EXPECTED={'n':16,'base':-72.54,'prot':-29.77,'delta':42.76,'trunc':0}; TOL=0.15

def emit(out,state,**x):
 p=Path(out);p.mkdir(parents=True,exist_ok=True);(p/'terminal_result.json').write_text(json.dumps({'object_id':O,'terminal_state':state,**x},indent=2,sort_keys=True))
def load_snapshot():
 subprocess.run(['git','-C',REPO,'fetch','origin',BRANCH],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=90)
 raw=subprocess.run(['git','-C',REPO,'show',f'FETCH_HEAD:{SNAP}'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30).stdout
 return json.loads(raw)
def ms(v):
 if isinstance(v,(int,float)):return int(v)
 d=datetime.fromisoformat(str(v).replace('Z','+00:00'));d=d if d.tzinfo else d.replace(tzinfo=timezone.utc);return int(d.timestamp()*1000)
def klines(symbol,start,end):
 out=[];cur=start
 while cur<=end:
  u=f'https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=1h&startTime={cur}&endTime={end}&limit=1500'
  with urllib.request.urlopen(u,timeout=30) as r: rows=json.loads(r.read())
  if not rows:break
  out.extend(rows);n=int(rows[-1][0])+3600000
  if n<=cur:break
  cur=n
 return [{'t':int(x[0]),'h':float(x[2]),'l':float(x[3])} for x in out if int(x[0])<=end]
def px(entry,d,pct):return entry*(1+pct/100) if d=='LONG' else entry*(1-pct/100)
def replay(t,bars):
 e=float(t['entry_price']);d=str(t['direction']).upper();active=None;exit_px=None;why='ORIGINAL_EXIT'
 for b in bars:
  if active is not None:
   p=px(e,d,active);hit=b['l']<=p if d=='LONG' else b['h']>=p
   if hit:exit_px=p;why=f'PROTECTED_{active:g}';break
  reached=[]
  for trig,lock in LADDER:
   p=px(e,d,trig);ok=b['h']>=p if d=='LONG' else b['l']<=p
   if ok:reached.append((trig,lock))
  if reached:active=max(reached,key=lambda z:z[0])[1]
 if exit_px is None:return float(t['profit_percent']),why,active
 gross=((exit_px/e)-1)*100 if d=='LONG' else ((e/exit_px)-1)*100
 return gross-0.1,why,active
def grouped(rows,key):
 out={}
 for r in rows:
  k=str(r.get(key));g=out.setdefault(k,{'n':0,'delta_sum':0.0,'positive_delta_n':0})
  g['n']+=1;g['delta_sum']+=r['delta'];g['positive_delta_n']+=int(r['delta']>0)
 return out
def close(a,b):return abs(a-b)<=TOL

def main(out,job):
 try:
  cfg=json.loads(Path(job).read_text())
  if cfg.get('object_id')!=O:return emit(out,'BLOCKED-EVIDENCE',reason='object_id mismatch')
  snap=load_snapshot();alltr=snap['trades']
  trades=[t for t in alltr if t.get('strategy') in STRATEGIES and t.get('market')=='futures' and t.get('timeframe')=='1h' and t.get('status') in ('closed','expired') and isinstance(t.get('profit_percent'),(int,float)) and t.get('entry_price') and t.get('opened_at') and t.get('closed_at')]
  rows=[];missing=[]
  for t in trades:
   try:
    bars=klines(t['symbol'],ms(t['opened_at']),ms(t['closed_at']))
    if not bars:missing.append({'id':t.get('id'),'symbol':t.get('symbol'),'reason':'no_1h_futures_klines'});continue
    new,why,active=replay(t,bars);base=float(t['profit_percent'])
    rows.append({'id':t.get('id'),'symbol':t.get('symbol'),'strategy':t.get('strategy'),'direction':str(t.get('direction')).upper(),'baseline':base,'protected':new,'delta':new-base,'exit':why,'highest_lock':active})
   except Exception as e:missing.append({'id':t.get('id'),'symbol':t.get('symbol'),'reason':repr(e)})
  if len(rows)<10:return emit(out,'BLOCKED-EVIDENCE',reason='insufficient replayable trades',eligible_n=len(trades),replayed_n=len(rows),missing=missing[:20])
  base=sum(r['baseline'] for r in rows);prot=sum(r['protected'] for r in rows);delta=prot-base
  trunc=sum(r['baseline']>0 and r['protected']<r['baseline'] for r in rows)
  reproduced=(len(rows)==EXPECTED['n'] and close(base,EXPECTED['base']) and close(prot,EXPECTED['prot']) and close(delta,EXPECTED['delta']) and trunc==EXPECTED['trunc'])
  pred={'replayed_n':len(rows),'baseline_sum_pct':base,'protected_sum_pct':prot,'delta_sum_pp':delta,'winner_truncation_count':trunc,'expected':EXPECTED,'tolerance_pp':TOL}
  if not reproduced:return emit(out,'PREDECESSOR-NOT-REPRODUCED',predecessor=pred,snapshot={'captured_at_utc':snap.get('captured_at_utc'),'source_revision':snap.get('source_revision')},missing_n=len(missing))
  pos=sorted([r['delta'] for r in rows if r['delta']>0],reverse=True);k=max(1,math.ceil(len(rows)*0.10))
  rem1=delta-(pos[0] if pos else 0.0);rem10=delta-sum(pos[:k])
  gs=grouped(rows,'strategy');gd=grouped(rows,'direction');gy=grouped(rows,'symbol')
  breadth={'strategy_positive_groups':sum(v['delta_sum']>0 for v in gs.values()),'direction_positive_groups':sum(v['delta_sum']>0 for v in gd.values()),'symbol_positive_groups':sum(v['delta_sum']>0 for v in gy.values())}
  broad=(delta>0 and rem1>0 and rem10>0 and breadth['strategy_positive_groups']>=2 and breadth['direction_positive_groups']>=2 and breadth['symbol_positive_groups']>=2)
  state='DEPENDENCE-BROAD' if broad else 'DEPENDENCE-CONCENTRATED'
  emit(out,state,predecessor=pred,anti_concentration={'delta_sum_pp':delta,'positive_delta_trade_n':len(pos),'remove_best1_delta_sum_pp':rem1,'remove_top_ceil10pct_delta_sum_pp':rem10,'top_k':k},breadth=breadth,by_strategy=gs,by_direction=gd,by_symbol=gy,by_trade=rows,snapshot={'captured_at_utc':snap.get('captured_at_utc'),'source_revision':snap.get('source_revision'),'total':snap.get('total')},contract={'ladder':LADDER,'same_candle_ordering':'conservative','protected_exit_cost_pct':0.1,'parameter_tuning':False,'terminal_broad_rule':'predecessor reproduces; total delta >0; delta stays >0 after removing best 1 and top ceil(10%) positive-delta trades; >=2 positive-contribution groups across strategy, direction, and symbol'},limitations=['Same 16-trade predecessor sample; this tests dependence of overlay benefit, not trading edge.','1h OHLC cannot resolve intrabar ordering; newly activated protection cannot exit in the same candle.','Category breadth is descriptive and does not authorize strategy/side/symbol filters or sizing.'])
 except Exception as e:emit(out,'PROVIDER-BLOCKED',reason=repr(e))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
