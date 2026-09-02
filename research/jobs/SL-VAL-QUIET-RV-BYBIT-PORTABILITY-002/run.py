"""SL-VAL-QUIET-RV-BYBIT-PORTABILITY-002.
Correction-only rerun of 001: Bybit API cursor remains milliseconds, but
stored candle timestamps are normalized to Unix seconds to match Binance.
Frozen Quiet-RV signal/risk/cost parameters are unchanged.
"""
import argparse, csv, hashlib, io, json, math, time, urllib.request, zipfile
from datetime import datetime, timezone
from pathlib import Path

OBJECT_ID='SL-VAL-QUIET-RV-BYBIT-PORTABILITY-002'
ASSETS=['BTCUSDT','ETHUSDT','BNBUSDT','ADAUSDT','XRPUSDT','DOGEUSDT','LINKUSDT','LTCUSDT']
TF='4h'; INTERVAL_SECONDS=4*3600; BYBIT_INTERVAL='240'
WARM=datetime(2022,1,1,tzinfo=timezone.utc); START=datetime(2022,7,1,tzinfo=timezone.utc)
SPLIT=datetime(2025,1,1,tzinfo=timezone.utc); END=datetime(2026,8,1,tzinfo=timezone.utc)
VOL_WIN,VOL_LOOK,VOL_Q=42,540,.30; DEV_WIN,DEV_LOOK,DEV_Q=42,540,.90
HOLD,DECLUSTER=6,6; COST,COST_STRESS=.001,.002; SOFT_DEADLINE_SECONDS=16*60

def emit(out,state,**extra):
 p=Path(out); p.mkdir(parents=True,exist_ok=True); (p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':state,**extra},indent=2,sort_keys=True,default=str))
def http_get(url,timeout=20): return urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'MarketHunter-Research/1.0'}),timeout=timeout).read()
def check_deadline(d,stage):
 if time.monotonic()>d: raise TimeoutError(f'soft deadline exceeded during {stage}')
def binance_month(s,y,m):
 base=f'https://data.binance.vision/data/spot/monthly/klines/{s}/{TF}'; name=f'{s}-{TF}-{y}-{m:02d}.zip'; url=f'{base}/{name}'; blob=http_get(url); expected=http_get(url+'.CHECKSUM').decode().split()[0].lower(); actual=hashlib.sha256(blob).hexdigest()
 if expected!=actual: raise ValueError(f'checksum mismatch {name}')
 rows=[]
 with zipfile.ZipFile(io.BytesIO(blob)) as zf:
  inner=[n for n in zf.namelist() if not n.endswith('/')][0]
  for parts in csv.reader(io.TextIOWrapper(zf.open(inner))):
   try: raw=int(parts[0]); o,c=float(parts[1]),float(parts[4])
   except (ValueError,IndexError): continue
   rows.append((int(raw/1e6 if raw>10**14 else raw/1e3),o,c))
 return rows,{'symbol':s,'venue':'BINANCE','url':url,'sha256':actual,'rows':len(rows)}
def fetch_binance_asset(s,d):
 data={}; files=[]; y,m=WARM.year,WARM.month
 while datetime(y,m,1,tzinfo=timezone.utc)<END:
  check_deadline(d,f'binance {s} {y}-{m:02d}'); rows,meta=binance_month(s,y,m)
  for ts,o,c in rows: data[ts]=(o,c)
  files.append(meta); m+=1
  if m>12: m=1; y+=1
 return data,files
def bybit_page(s,start_ms,end_ms,limit=1000):
 url=f'https://api.bybit.com/v5/market/kline?category=linear&symbol={s}&interval={BYBIT_INTERVAL}&start={start_ms}&end={end_ms}&limit={limit}'; p=json.loads(http_get(url))
 if p.get('retCode')!=0: raise ValueError(f'bybit retCode={p.get("retCode")} retMsg={p.get("retMsg")} symbol={s}')
 return (p.get('result') or {}).get('list') or []
def fetch_bybit_asset(s,start_ms,end_ms,d):
 data={}; cursor_end=end_ms; seen_min=None
 for _ in range(2000):
  check_deadline(d,f'bybit {s}')
  if cursor_end<=start_ms: break
  batch=bybit_page(s,start_ms,cursor_end)
  if not batch: break
  batch_min=None
  for row in batch:
   raw_ms=int(row[0]); ts=raw_ms//1000; o,c=float(row[1]),float(row[4]); data[ts]=(o,c); batch_min=raw_ms if batch_min is None or raw_ms<batch_min else batch_min
  if seen_min is not None and batch_min>=seen_min: break
  seen_min=batch_min; cursor_end=batch_min-1
 return data
def gaps(ts):
 return [[a,b] for a,b in zip(ts,ts[1:]) if b-a>INTERVAL_SECONDS]
def qtl(v,q):
 s=sorted(v); x=(len(s)-1)*q; lo,hi=int(math.floor(x)),int(math.ceil(x)); return s[lo] if lo==hi else s[lo]*(hi-x)+s[hi]*(x-lo)
def stdev(v):
 m=sum(v)/len(v); return math.sqrt(sum((x-m)**2 for x in v)/len(v))
def stats(r):
 if not r:return {'n':0,'mean':None,'median':None,'hit':None,'pf':None,'cum':None,'max_dd':None}
 s=sorted(r); med=s[len(s)//2] if len(s)%2 else (s[len(s)//2-1]+s[len(s)//2])/2; gains=sum(x for x in r if x>0); losses=-sum(x for x in r if x<0); eq=peak=1.; dd=0.
 for x in r: eq*=1+x; peak=max(peak,eq); dd=min(dd,eq/peak-1)
 return {'n':len(r),'mean':sum(r)/len(r),'median':med,'hit':sum(x>0 for x in r)/len(r),'pf':gains/losses if losses else None,'cum':eq-1,'max_dd':dd}
def run_signal(ts,data):
 n=len(ts); close={s:[data[s][t][1] for t in ts] for s in ASSETS}; ret={s:[None]+[math.log(close[s][i]/close[s][i-1]) for i in range(1,n)] for s in ASSETS}; market=[None]+[sum(ret[s][i] for s in ASSETS)/len(ASSETS) for i in range(1,n)]; rv=[None]*n; dev={s:[None]*n for s in ASSETS}
 for i in range(VOL_WIN+1,n):
  rv[i]=stdev(market[i-VOL_WIN+1:i+1])
  for s in ASSETS: dev[s][i]=sum(ret[s][j]-market[j] for j in range(i-DEV_WIN+1,i+1))
 ev=[]; last=-10**9; floor=max(VOL_LOOK,DEV_LOOK)+VOL_WIN+1
 for i in range(floor,n-HOLD-1):
  t=ts[i]
  if t<int(START.timestamp()) or t>=int(END.timestamp()) or i-last<DECLUSTER: continue
  vh=[x for x in rv[i-VOL_LOOK:i] if x is not None]
  if not vh or rv[i]>qtl(vh,VOL_Q): continue
  dh=[abs(dev[s][j]) for j in range(i-DEV_LOOK,i) for s in ASSETS if dev[s][j] is not None]
  if not dh: continue
  th=qtl(dh,DEV_Q); cand=max(ASSETS,key=lambda s:abs(dev[s][i]))
  if abs(dev[cand][i])<=th: continue
  side='SHORT' if dev[cand][i]>0 else 'LONG'; entry=data[cand][ts[i+1]][0]; exit_=data[cand][ts[i+HOLD]][0]; gross=exit_/entry-1 if side=='LONG' else entry/exit_-1
  ev.append({'ts':t,'asset':cand,'side':side,'net10':gross-COST,'net20':gross-COST_STRESS,'period':'IS' if t<int(SPLIT.timestamp()) else 'OOS'}); last=i
 return ev
def main(out,job):
 d=time.monotonic()+SOFT_DEADLINE_SECONDS
 try:
  if json.loads(Path(job).read_text()).get('object_id')!=OBJECT_ID: raise ValueError('object id mismatch')
 except Exception as e: emit(out,'PROVIDER-BLOCKED',reason=repr(e),parameter_tuning=False); return
 try:
  bd={}; files=[]
  for s in ASSETS: x,f=fetch_binance_asset(s,d); bd[s]=x; files+=f
 except Exception as e: emit(out,'PROVIDER-BLOCKED',reason=f'binance: {e!r}',parameter_tuning=False); return
 yd={}; errors={}; start_ms=int(WARM.timestamp()*1000); end_ms=int(END.timestamp()*1000)
 try:
  for s in ASSETS:
   try: yd[s]=fetch_bybit_asset(s,start_ms,end_ms,d)
   except TimeoutError: raise
   except Exception as e: errors[s]=repr(e)
 except TimeoutError as e: emit(out,'PROVIDER-BLOCKED',reason=f'bybit soft-deadline: {e!r}',bybit_symbols_fetched_before_timeout=sorted(yd),parameter_tuning=False); return
 diag={}
 for s in ASSETS:
  b=sorted(bd.get(s,{})); y=sorted(yd.get(s,{})); diag[s]={'binance_rows':len(b),'binance_gap_count':len(gaps(b)),'binance_first_ts':b[0] if b else None,'binance_last_ts':b[-1] if b else None,'bybit_rows':len(y),'bybit_gap_count':len(gaps(y)),'bybit_first_ts':y[0] if y else None,'bybit_last_ts':y[-1] if y else None,'bybit_fetch_error':errors.get(s)}
 missing=[s for s in ASSETS if not yd.get(s)]
 if missing: emit(out,'OUTCOME-COMPLETE',portability_verdict='INCONCLUSIVE',portability_verdict_reason=f'bybit has no usable data for {missing}; frozen 8-asset basket cannot be computed partially',asset_diagnostics=diag,bybit_errors=errors,source_files_binance=files,parameter_tuning=False,timestamp_normalization='bybit_ms_to_unix_seconds'); return
 bc=set.intersection(*[set(bd[s]) for s in ASSETS]); yc=set.intersection(*[set(yd[s]) for s in ASSETS]); both=sorted(bc&yc)
 if len(both)<max(VOL_LOOK,DEV_LOOK)+VOL_WIN+HOLD+2: emit(out,'OUTCOME-COMPLETE',portability_verdict='INCONCLUSIVE',portability_verdict_reason=f'only {len(both)} normalized bars overlap across all 8 assets on both venues',asset_diagnostics=diag,bybit_errors=errors,source_files_binance=files,parameter_tuning=False,timestamp_normalization='bybit_ms_to_unix_seconds'); return
 be=run_signal(both,bd); ye=run_signal(both,yd); bo=[e for e in be if e['period']=='OOS']; yo=[e for e in ye if e['period']=='OOS']; bk={(e['ts'],e['asset'],e['side']) for e in bo}; yk={(e['ts'],e['asset'],e['side']) for e in yo}; overlap=bk&yk; union=bk|yk; ratio=len(overlap)/len(union) if union else None
 def gate(ev):
  r10=[e['net10'] for e in ev]; r20=[e['net20'] for e in ev]; s10,s20=stats(r10),stats(r20); wins=sorted([x for x in r10 if x>0],reverse=True); top=wins[0]/sum(wins) if wins and sum(wins)>0 else None; v='BLOCKED-EVIDENCE' if s10['n']<30 else ('CANDIDATE' if s10['mean']>0 and (s10['pf'] or 0)>1 and s20['mean']>0 and (top is None or top<.5) else 'REJECTED'); return s10,s20,top,v
 bs10,bs20,btop,bg=gate(bo); ys10,ys20,ytop,yg=gate(yo)
 if yg=='BLOCKED-EVIDENCE': verdict='INCONCLUSIVE'; reason=f'only {ys10["n"]} Bybit OOS events (<30)'
 elif yg=='CANDIDATE' and (ratio or 0)>=.70: verdict='VENUE-PORTABLE'; reason=f'Bybit passes frozen gate and event overlap is {ratio:.0%}'
 elif bg=='CANDIDATE' and yg!='CANDIDATE': verdict='BINANCE-SPECIFIC-CANDIDATE'; reason='Binance passes frozen gate on common window; Bybit does not'
 else: verdict='INCONCLUSIVE'; reason=f'binance_gate={bg}, bybit_gate={yg}, event_overlap={ratio}'
 emit(out,'OUTCOME-COMPLETE',contract={'assets':ASSETS,'tf':TF,'common_window_bars':len(both),'common_window_first_ts':both[0],'common_window_last_ts':both[-1],'split':SPLIT.date().isoformat(),'parameter_tuning':False,'timestamp_normalization':'bybit_ms_to_unix_seconds'},asset_diagnostics=diag,bybit_errors=errors,binance_oos_stats_10bps=bs10,binance_oos_stats_20bps=bs20,binance_oos_top_positive_trade_share=btop,binance_gate_verdict=bg,binance_event_count=len(be),bybit_oos_stats_10bps=ys10,bybit_oos_stats_20bps=ys20,bybit_oos_top_positive_trade_share=ytop,bybit_gate_verdict=yg,bybit_event_count=len(ye),oos_event_overlap_ratio=ratio,oos_event_overlap_count=len(overlap),oos_event_union_count=len(union),portability_verdict=verdict,portability_verdict_reason=reason,source_files_binance=files,parameter_tuning=False,limitations=['Bybit timestamps normalized ms->seconds; pagination remains ms','price-only Binance Spot vs Bybit linear perpetual; no funding/OI','no parameter, asset, threshold, holding-period, or cost change'])
if __name__=='__main__':
 p=argparse.ArgumentParser(); p.add_argument('--job',required=True); p.add_argument('--output',required=True); a=p.parse_args(); main(a.output,a.job)
