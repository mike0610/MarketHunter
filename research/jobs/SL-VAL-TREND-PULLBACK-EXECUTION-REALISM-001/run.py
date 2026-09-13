import argparse,csv,hashlib,io,json,math,urllib.parse,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path

OBJECT_ID='SL-VAL-TREND-PULLBACK-EXECUTION-REALISM-001'
SYMBOL='ETHUSDT'
BASE=f'https://data.binance.vision/data/futures/um/monthly/klines/{SYMBOL}/4h'
FUNDING_URL='https://fapi.binance.com/fapi/v1/fundingRate'
WARM=datetime(2020,1,1,tzinfo=timezone.utc)
START=datetime(2021,1,1,tzinfo=timezone.utc)
SPLIT=datetime(2025,1,1,tzinfo=timezone.utc)
END=datetime(2026,8,1,tzinfo=timezone.utc)
TREND=180;PULL=3;ROLL=1080;Q=.90;HOLD=12;DECLUSTER=18
COSTS=(.001,.002,.003,.005)
OOS_MIN_N=20

def emit(out,state,**extra):
 p=Path(out);p.mkdir(parents=True,exist_ok=True)
 (p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':state,**extra},indent=2,sort_keys=True))

def get(url):
 req=urllib.request.Request(url,headers={'User-Agent':'MarketHunter-Research/1.0'})
 return urllib.request.urlopen(req,timeout=30).read()

def month(y,m):
 name=f'{SYMBOL}-4h-{y}-{m:02d}.zip';url=f'{BASE}/{name}'
 raw=get(url);published=get(url+'.CHECKSUM').decode().split()[0].lower();actual=hashlib.sha256(raw).hexdigest()
 if published!=actual: raise ValueError('checksum '+name)
 rows=[]
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  members=[x for x in z.namelist() if not x.endswith('/')]
  if len(members)!=1: raise ValueError('archive-members '+name)
  for r in csv.reader(io.TextIOWrapper(z.open(members[0]))):
   try: ts_raw=int(r[0]);o,h,l,c=map(float,r[1:5])
   except Exception: continue
   if not all(math.isfinite(x) and x>0 for x in (o,h,l,c)): continue
   ts=ts_raw/1e6 if ts_raw>10**14 else ts_raw/1e3
   rows.append({'ts':int(ts),'o':o,'h':h,'l':l,'c':c})
 return rows,{'url':url,'sha256':actual,'rows':len(rows),'symbol':SYMBOL,'year':y,'month':m}

def quantile(values,q):
 s=sorted(values);x=(len(s)-1)*q;lo=int(math.floor(x));hi=int(math.ceil(x))
 return s[lo] if lo==hi else s[lo]*(hi-x)+s[hi]*(x-lo)

def stats(v):
 if not v:return {'n':0,'mean':None,'median':None,'hit':None,'pf':None,'cum':None,'max_dd':None}
 s=sorted(v);med=s[len(s)//2] if len(s)%2 else (s[len(s)//2-1]+s[len(s)//2])/2
 gains=sum(x for x in v if x>0);losses=-sum(x for x in v if x<0);eq=peak=1.;dd=0.
 for x in v: eq*=1+x;peak=max(peak,eq);dd=min(dd,eq/peak-1)
 return {'n':len(v),'mean':sum(v)/len(v),'median':med,'hit':sum(x>0 for x in v)/len(v),'pf':gains/losses if losses else None,'cum':eq-1,'max_dd':dd}

def funding_history():
 start=int((SPLIT.timestamp()-86400)*1000);end=int(END.timestamp()*1000);cur=start;out=[]
 while cur<end:
  q=urllib.parse.urlencode({'symbol':SYMBOL,'startTime':cur,'endTime':end,'limit':1000})
  a=json.loads(get(FUNDING_URL+'?'+q).decode())
  if not isinstance(a,list): raise ValueError('funding-response-not-list')
  if not a: break
  for x in a:
   ts=int(x['fundingTime'])//1000;rate=float(x['fundingRate']);mark=float(x['markPrice'])
   if not (math.isfinite(rate) and math.isfinite(mark) and mark>0): raise ValueError('invalid-funding-row')
   out.append({'ts':ts,'rate':rate,'mark':mark})
  nxt=max(int(x['fundingTime']) for x in a)+1
  if nxt<=cur: raise ValueError('funding-pagination-stall')
  cur=nxt
 out=sorted({x['ts']:x for x in out}.values(),key=lambda x:x['ts'])
 if not out: raise ValueError('no-funding')
 gaps=[b['ts']-a['ts'] for a,b in zip(out,out[1:])]
 if gaps and max(gaps)>9*3600: raise ValueError('funding-gap>9h')
 return out

def metric_invariants():
 for e,x in [(100.,110.),(100.,90.),(250.,250.)]:
  q=x/e
  if abs((q-1)+(1-q))>1e-15:return False
 return True

def main(out,job):
 try:
  cfg=json.loads(Path(job).read_text())
  expected={'EXECUTION-MARGIN-SURVIVES','EXECUTION-MARGIN-ERASED','INSUFFICIENT-OOS-BREADTH','EVIDENCE-FAIL','PROVIDER-BLOCKED'}
  if cfg.get('object_id')!=OBJECT_ID or cfg.get('executor')!='vps' or set(cfg.get('terminal_states',[]))!=expected: raise ValueError('job-contract')
  if not (1<=int(cfg.get('timeout_minutes',0))<=20): raise ValueError('timeout-contract')
  if not metric_invariants(): raise ValueError('metric-invariant')
 except Exception as e: emit(out,'EVIDENCE-FAIL',reason=repr(e),parameter_tuning=False);return
 try:
  rows=[];sources=[]
  for y in range(2020,2027):
   for m in range(1,13):
    d=datetime(y,m,1,tzinfo=timezone.utc)
    if d<WARM or d>=END:continue
    a,meta=month(y,m);rows+=a;sources.append(meta)
  funding=funding_history()
 except Exception as e: emit(out,'PROVIDER-BLOCKED',reason=repr(e),parameter_tuning=False);return
 rows.sort(key=lambda x:x['ts'])
 if not rows or len({x['ts'] for x in rows})!=len(rows): emit(out,'EVIDENCE-FAIL',reason='kline-integrity',parameter_tuning=False);return
 events=[];last=-10**9;begin=max(TREND,PULL,ROLL)+1
 for i in range(begin,len(rows)-HOLD):
  b=rows[i]
  if b['ts']<int(START.timestamp()) or b['ts']>=int(END.timestamp()) or i-last<DECLUSTER: continue
  try:
   trend_ret=math.log(rows[i-1]['c']/rows[i-1-TREND]['c']);pull_ret=math.log(rows[i]['c']/rows[i-PULL]['c'])
   hist=[abs(math.log(rows[j]['c']/rows[j-PULL]['c'])) for j in range(i-ROLL,i)]
  except Exception as e: emit(out,'EVIDENCE-FAIL',reason='return-construction:'+repr(e),parameter_tuning=False);return
  if len(hist)<ROLL: continue
  th=quantile(hist,Q);side=None
  if trend_ret>0 and pull_ret<0 and abs(pull_ret)>th: side='LONG'
  elif trend_ret<0 and pull_ret>0 and abs(pull_ret)>th: side='SHORT'
  if side is None: continue
  entry_i=i+1;exit_i=i+HOLD;entry=rows[entry_i]['o'];exitp=rows[exit_i]['o'];q=exitp/entry
  gross=q-1 if side=='LONG' else 1-q
  frows=[x for x in funding if rows[entry_i]['ts']<=x['ts']<rows[exit_i]['ts']]
  if b['ts']>=int(SPLIT.timestamp()) and not frows:
   emit(out,'EVIDENCE-FAIL',reason='missing-funding-inside-oos-hold',event_ts=b['ts'],parameter_tuning=False);return
  sign=1 if side=='LONG' else -1
  funding_return=sum(-sign*x['rate']*(x['mark']/entry) for x in frows)
  pre=gross+funding_return
  events.append({'signal_ts':b['ts'],'entry_ts':rows[entry_i]['ts'],'exit_ts':rows[exit_i]['ts'],'side':side,'gross':gross,'funding_return':funding_return,'funding_count':len(frows),'pre_friction':pre,'period':'IS' if b['ts']<int(SPLIT.timestamp()) else 'OOS',**{f'net_{int(c*10000)}bp':pre-c for c in COSTS}})
  last=i
 oos=[x for x in events if x['period']=='OOS']
 if len(oos)<OOS_MIN_N:
  emit(out,'INSUFFICIENT-OOS-BREADTH',oos_n=len(oos),required_n=OOS_MIN_N,parameter_tuning=False);return
 ladder={f'{int(c*10000)}bp':stats([x[f'net_{int(c*10000)}bp'] for x in oos]) for c in COSTS}
 s20=ladder['20bp'];state='EXECUTION-MARGIN-SURVIVES' if s20['mean'] is not None and s20['mean']>0 else 'EXECUTION-MARGIN-ERASED'
 be=10000*stats([x['pre_friction'] for x in oos])['mean']
 emit(out,state,
  market=f'{SYMBOL} Binance USDT-M perpetual',
  contract={'parent_object':'SL-VAL-TREND-PULLBACK-001','tf':'4h','trend':'strictly-prior 180-bar return sign','pullback':'3-bar counter-trend move whose absolute return exceeds strictly-prior 1080-bar 90th percentile','entry':'next_bar_open','exit':'open at signal_index+12 (frozen parent indexing)','decluster_bars':18,'split':'2025-01-01','oos_end':'2026-08-01','long_return':'exit_over_entry-1','short_return':'1-exit_over_entry fixed entry-notional','funding':'actual public Binance ETHUSDT funding rates during each hold; cashflow scaled by funding mark/entry under fixed entry-notional quantity','friction_ladder_round_trip_bps':[10,20,30,50],'classification_gate':'pooled OOS arithmetic mean after actual funding and pre-existing 20bp stress > 0','oos_min_n':OOS_MIN_N,'parameter_tuning':False},
  oos_pre_friction=stats([x['pre_friction'] for x in oos]),oos_cost_ladder=ladder,
  oos_long_20bp=stats([x['net_20bp'] for x in oos if x['side']=='LONG']),oos_short_20bp=stats([x['net_20bp'] for x in oos if x['side']=='SHORT']),
  oos_funding=stats([x['funding_return'] for x in oos]),break_even_round_trip_friction_bps=be,
  oos_funding_counts={'min':min(x['funding_count'] for x in oos),'max':max(x['funding_count'] for x in oos),'mean':sum(x['funding_count'] for x in oos)/len(oos)},
  event_count=len(events),oos_event_count=len(oos),source_files=sources,parameter_tuning=False,
  limitations=['funding cashflow uses public funding mark price and fixed entry-notional quantity; it does not model changing margin balance','10/20/30/50bp ladder is an adverse all-in friction envelope, not reconstructed historical bid/ask spread or realized slippage','latency, queue position, partial fills, market impact and venue outages are not reconstructed from 4h klines','classification uses the already-existing 20bp stress convention; 30/50bp are diagnostics only and do not change the terminal state','pooled result does not authorize LONG-disable, SHORT-only tuning, leverage, sizing or canonical promotion'])
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--job',required=True);ap.add_argument('--output',required=True);args=ap.parse_args();main(args.output,args.job)
