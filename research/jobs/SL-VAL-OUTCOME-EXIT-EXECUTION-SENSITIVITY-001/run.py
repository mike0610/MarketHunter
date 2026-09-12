import argparse, hashlib, json, math, random, subprocess, time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

OBJECT_ID='SL-VAL-OUTCOME-EXIT-EXECUTION-SENSITIVITY-001'
REPO='/home/ubuntu/MarketHunter'; SNAP_BRANCH='outcome-intelligence-snapshots'
SNAP_COMMIT='614fd31472c9fc616cdee4a068609e6def67cb77'; SNAP='data/outcome_intelligence/latest/trades.json'
MIN_PER_STRATEGY=16; MIN_HALF=8; MIN_TS_COVERAGE=.90; MIN_EXEC_DATA_COVERAGE=.90
BOOTSTRAPS=10000; SEED=20260912; EXCLUDED={'Breaker'}; ROUND_TRIP_COST_PP=.12
EXIT_TYPES={'take_profit','stop_loss','live_stop_loss'}

def emit(out,state,**p):
 d=Path(out); d.mkdir(parents=True,exist_ok=True); (d/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':state,**p},indent=2,sort_keys=True))
def pts(x):
 if not x:return None
 try:return datetime.fromisoformat(str(x).replace('Z','+00:00'))
 except ValueError:return None
def mean(x):return sum(x)/len(x)
def pctile(x,q):
 y=sorted(x); p=(len(y)-1)*q; lo=int(math.floor(p)); hi=int(math.ceil(p)); return y[lo] if lo==hi else y[lo]+(y[hi]-y[lo])*(p-lo)
def boot(vals):
 r=random.Random(SEED); z=[mean([vals[r.randrange(len(vals))] for _ in vals]) for _ in range(BOOTSTRAPS)]; return [pctile(z,.025),pctile(z,.975)]
def classify(dm,lo,hi):
 if dm>0:
  if lo>0:return 'SIGN-PERSISTS'
  if hi<0:return 'SIGN-REVERSES'
 elif dm<0:
  if hi<0:return 'SIGN-PERSISTS'
  if lo>0:return 'SIGN-REVERSES'
 return 'MIXED-STABILITY'
def getjson(url,params=None):
 if params:url+='?'+urlencode(params)
 req=Request(url,headers={'User-Agent':'MarketHunter-Research/1.0'})
 with urlopen(req,timeout=12) as r:return json.loads(r.read().decode())
def interval_ms(tf):
 n=int(tf[:-1]); u=tf[-1]; return n*{'m':60000,'h':3600000,'d':86400000,'w':604800000}[u]
def venue_maps():
 out={}
 for market,base in [('futures','https://fapi.binance.com'),('spot','https://api.binance.com')]:
  data=getjson(base+('/fapi/v1/exchangeInfo' if market=='futures' else '/api/v3/exchangeInfo'))
  mp={}
  for s in data.get('symbols',[]):
   for f in s.get('filters',[]):
    if f.get('filterType')=='PRICE_FILTER':
     try:mp[s['symbol']]=float(f['tickSize'])
     except:pass
  out[market]=(base,mp)
 return out
def exit_confirmation(row,venues):
 ot=str(row.get('outcome_type') or '').strip().lower()
 if ot not in EXIT_TYPES:return None,'unsupported_outcome_type'
 market='spot' if str(row.get('market')).lower()=='spot' else 'futures'; base,ticks=venues[market]; sym=str(row['symbol']); tick=ticks.get(sym)
 if not tick or tick<=0:return None,'missing_tick'
 tf=str(row.get('timeframe') or ''); closed=pts(row.get('closed_at')); direction=str(row.get('direction') or '').upper()
 try: span=interval_ms(tf)
 except:return None,'unsupported_timeframe'
 if not closed:return None,'missing_closed_at'
 try:
  level=float(row['take_profit'] if ot=='take_profit' else row['stop_loss'])
 except:return None,'missing_exit_level'
 t=int(closed.timestamp()*1000); endpoint='/fapi/v1/klines' if market=='futures' else '/api/v3/klines'
 try: arr=getjson(base+endpoint,{'symbol':sym,'interval':tf,'startTime':max(0,t-span),'endTime':t+span,'limit':3})
 except Exception as e:return None,'kline_error:'+type(e).__name__
 candle=None
 for k in arr:
  if int(k[0])<=t<=int(k[6]):candle=k;break
 if candle is None:return None,'no_containing_candle'
 high=float(candle[2]); low=float(candle[3])
 if ot=='take_profit':
  if direction=='LONG':ok=high >= level+tick-1e-12
  elif direction=='SHORT':ok=low <= level-tick+1e-12
  else:return None,'bad_direction'
 else:
  if direction=='LONG':ok=low <= level-tick+1e-12
  elif direction=='SHORT':ok=high >= level+tick-1e-12
  else:return None,'bad_direction'
 return ok,{'outcome_type':ot,'tick_size':tick,'candle_open_ms':int(candle[0]),'high':high,'low':low,'level':level,'direction':direction,'rule':'TP/SL candle must penetrate planned exit level by >= one venue tick; mere touch fails'}
def main(out,job):
 try:
  cfg=json.loads(Path(job).read_text()); assert cfg.get('object_id')==OBJECT_ID
  subprocess.run(['git','-C',REPO,'fetch','origin',SNAP_BRANCH],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=90)
  raw=subprocess.run(['git','-C',REPO,'show',f'{SNAP_COMMIT}:{SNAP}'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30).stdout
  snap=json.loads(raw); trades=snap.get('trades'); assert isinstance(trades,list)
  by=defaultdict(list); exc=Counter()
  for t in trades:
   if t.get('research_group')!='core' or t.get('is_experimental'):exc['not_core_or_experimental']+=1;continue
   if t.get('status') not in ('closed','expired') or t.get('outcome_group') not in ('positive','negative'):exc['not_completed_binary_outcome']+=1;continue
   try:pp=float(t.get('profit_percent'))
   except:exc['missing_profit']+=1;continue
   if not math.isfinite(pp) or pp==0:exc['invalid_profit']+=1;continue
   s=str(t.get('strategy') or '').strip()
   if not s or s in EXCLUDED:exc['missing_or_excluded_strategy']+=1;continue
   z=dict(t); z['_closed']=pts(t.get('closed_at')); z['_pp']=pp; by[s].append(z)
  cand={}; counts=[]
  for s,rows in sorted(by.items()):
   before=len(rows); v=[r for r in rows if r['_closed']]; v.sort(key=lambda r:(r['_closed'],str(r.get('id')))); cov=len(v)/before if before else 0; mid=len(v)//2; a,b=v[:mid],v[mid:]
   ok=len(v)>=MIN_PER_STRATEGY and cov>=MIN_TS_COVERAGE and len(a)>=MIN_HALF and len(b)>=MIN_HALF; rec={'strategy':s,'eligible_timestamped':len(v),'timestamp_coverage':cov,'first_n':len(a),'second_n':len(b),'candidate':ok}; counts.append(rec)
   if ok:cand[s]=(rec,a,b)
  if not cand:emit(out,'BLOCKED-EVIDENCE',reason='no frozen eligible non-Breaker strategy',candidate_counts=counts);return
  selected=sorted(cand,key=lambda s:(-cand[s][0]['eligible_timestamped'],s))[0]; rec,a,b=cand[selected]
  venues=venue_maps(); details=[]; failures=Counter(); eligible={'a':[],'b':[]}; confirmed={'a':[],'b':[]}
  for half,rows in [('a',a),('b',b)]:
   for r in rows:
    if str(r.get('outcome_type') or '').strip().lower() not in EXIT_TYPES:continue
    eligible[half].append(r); ok,meta=exit_confirmation(r,venues)
    if ok is None:failures[str(meta)]+=1
    elif ok:confirmed[half].append(r)
    details.append({'id':str(r.get('id')),'half':half,'exit_confirmed':ok,'meta':meta}); time.sleep(.04)
  queried=len(details); data_ok=sum(1 for x in details if x['exit_confirmed'] is not None); coverage=data_ok/queried if queried else 0
  if coverage<MIN_EXEC_DATA_COVERAGE or len(confirmed['a'])<MIN_HALF or len(confirmed['b'])<MIN_HALF:
   emit(out,'BLOCKED-EVIDENCE',reason='insufficient TP/SL execution-data coverage or exit-confirmed observations under frozen gates',selected_strategy=selected,execution_data_coverage=coverage,eligible_exit_first_n=len(eligible['a']),eligible_exit_second_n=len(eligible['b']),confirmed_first_n=len(confirmed['a']),confirmed_second_n=len(confirmed['b']),failures=dict(failures),parameter_tuning=False);return
  base_a=[r['_pp']-ROUND_TRIP_COST_PP for r in eligible['a']]; base_b=[r['_pp']-ROUND_TRIP_COST_PP for r in eligible['b']]; ea=[r['_pp']-ROUND_TRIP_COST_PP for r in confirmed['a']]; eb=[r['_pp']-ROUND_TRIP_COST_PP for r in confirmed['b']]
  base_ci=boot(base_b); exit_ci=boot(eb); base_state=classify(mean(base_a),*base_ci); exit_state=classify(mean(ea),*exit_ci)
  state={'SIGN-PERSISTS':'EXIT-CONFIRMED-SIGN-PERSISTS','SIGN-REVERSES':'EXIT-CONFIRMED-SIGN-REVERSES','MIXED-STABILITY':'EXIT-CONFIRMED-MIXED-STABILITY'}[exit_state]
  evidence={'snapshot':{'pinned_commit':SNAP_COMMIT,'captured_at_utc':snap.get('captured_at_utc'),'source_revision':snap.get('source_revision'),'sha256':hashlib.sha256(raw.encode()).hexdigest()},'contract':{'selection':'same frozen outcome-blind rank-1 eligible non-Breaker candidate and chronological 50/50 split','exit_scope':'only take_profit, stop_loss and live_stop_loss outcomes with explicit planned exit levels','exit_proxy':'Binance candle containing stored closed_at must penetrate planned TP/SL by >= one PRICE_FILTER tick; mere touch fails','cost_model':'same frozen 12 bps round-trip deduction','no_sweep':True,'bootstrap':{'iterations':BOOTSTRAPS,'seed':SEED},'interpretation':'exit execution sensitivity only; does not model intrabar queue, latency, spread path, gap slippage or impact and cannot promote a strategy'},'selected_strategy':selected,'selected_counts':rec,'eligible_exit_first_n':len(eligible['a']),'eligible_exit_second_n':len(eligible['b']),'execution_data_coverage':coverage,'confirmed_first_n':len(ea),'confirmed_second_n':len(eb),'baseline_explicit_exit_cost_adjusted':{'discovery_mean_pp':mean(base_a),'heldout_mean_pp':mean(base_b),'ci95':base_ci,'stability':base_state},'exit_confirmed_cost_adjusted':{'discovery_mean_pp':mean(ea),'heldout_mean_pp':mean(eb),'ci95':exit_ci,'stability':exit_state},'verdict_changed_by_exit_proxy':base_state!=exit_state,'failures':dict(failures),'details':details,'parameter_tuning':False}
  d=Path(out); d.mkdir(parents=True,exist_ok=True); eraw=json.dumps(evidence,indent=2,sort_keys=True); (d/'exit_execution_sensitivity_evidence.json').write_text(eraw)
  emit(out,state,reason='frozen one-tick TP/SL exit-confirmation sensitivity completed',evidence_file='exit_execution_sensitivity_evidence.json',evidence_sha256=hashlib.sha256(eraw.encode()).hexdigest(),**evidence)
 except Exception as e:emit(out,'BLOCKED-EVIDENCE',reason=f'execution/data failure: {e!r}',pinned_commit=SNAP_COMMIT,parameter_tuning=False)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--job',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();main(a.output,a.job)
