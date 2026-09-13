import argparse,csv,hashlib,io,json,math,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path

OBJECT_ID='SL-VAL-TREND-PULLBACK-SIDE-ASYMMETRY-CROSS-ASSET-TEMPORAL-001'
SYMBOL='SOLUSDT'
BASE=f'https://data.binance.vision/data/futures/um/monthly/klines/{SYMBOL}/4h'
WARM=datetime(2020,1,1,tzinfo=timezone.utc)
START=datetime(2021,1,1,tzinfo=timezone.utc)
SPLIT=datetime(2025,1,1,tzinfo=timezone.utc)
END=datetime(2026,8,1,tzinfo=timezone.utc)
CUT=datetime(2025,10,16,12,tzinfo=timezone.utc)
TREND=180
PULL=3
ROLL=1080
Q=.90
HOLD=12
DECLUSTER=18
COST=.001
COST_STRESS=.002
POOLED_MIN_SIDE_N=10
PART_MIN_SIDE_N=5
MATERIAL_GAP=.0025

def emit(out,state,**extra):
 p=Path(out);p.mkdir(parents=True,exist_ok=True)
 (p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':state,**extra},indent=2,sort_keys=True))

def get(url):
 req=urllib.request.Request(url,headers={'User-Agent':'MarketHunter-Research/1.0'})
 return urllib.request.urlopen(req,timeout=30).read()

def month(y,m):
 name=f'{SYMBOL}-4h-{y}-{m:02d}.zip';url=f'{BASE}/{name}'
 raw=get(url);expected=get(url+'.CHECKSUM').decode().split()[0].lower();actual=hashlib.sha256(raw).hexdigest()
 if expected!=actual: raise ValueError('checksum '+name)
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

def side_stats(events,cost_key):
 return stats([x[cost_key] for x in events if x['side']=='LONG']),stats([x[cost_key] for x in events if x['side']=='SHORT'])

def passes(l10,s10,l20,s20,min_n):
 if min(l10['n'],s10['n'],l20['n'],s20['n'])<min_n:return False
 return (l10['mean']<=0 and s10['mean']>0 and s10['mean']-l10['mean']>=MATERIAL_GAP and
         l20['mean']<=0 and s20['mean']>0 and s20['mean']-l20['mean']>=MATERIAL_GAP)

def metric_invariants():
 for entry,exitp in [(100.,110.),(100.,90.),(250.,250.),(80.,100.)]:
  q=exitp/entry;lr=q-1;sr=1-q
  if abs(lr+sr)>1e-15:return False
  if abs(sr-(entry-exitp)/entry)>1e-15:return False
 return True

def main(out,job):
 try:
  cfg=json.loads(Path(job).read_text())
  if cfg.get('object_id')!=OBJECT_ID:raise ValueError('object-id-mismatch')
  expected={'CROSS-ASSET-CONCENTRATION-REPLICATED','CROSS-ASSET-CONCENTRATION-NOT-REPLICATED','INSUFFICIENT-PARTITION-BREADTH','EVIDENCE-FAIL','PROVIDER-BLOCKED'}
  if set(cfg.get('terminal_states',[]))!=expected:raise ValueError('terminal-states-mismatch')
 except Exception as e: emit(out,'EVIDENCE-FAIL',reason='job-contract:'+repr(e),parameter_tuning=False);return
 if not metric_invariants(): emit(out,'EVIDENCE-FAIL',reason='metric-invariant',parameter_tuning=False);return
 if SPLIT+(END-SPLIT)/2!=CUT: emit(out,'EVIDENCE-FAIL',reason='partition-midpoint-invariant',parameter_tuning=False);return
 try:
  rows=[];sources=[]
  for y in range(2020,2027):
   for m in range(1,13):
    d=datetime(y,m,1,tzinfo=timezone.utc)
    if d<WARM or d>=END:continue
    try:
     a,meta=month(y,m)
    except Exception as e:
     if d<SPLIT and y<2021: continue
     raise e
    rows+=a;sources.append(meta)
 except Exception as e: emit(out,'PROVIDER-BLOCKED',reason=repr(e),parameter_tuning=False);return
 rows.sort(key=lambda x:x['ts'])
 if not rows: emit(out,'EVIDENCE-FAIL',reason='no-valid-rows',parameter_tuning=False);return
 if len({x['ts'] for x in rows})!=len(rows): emit(out,'EVIDENCE-FAIL',reason='duplicate-kline-timestamps',parameter_tuning=False);return
 pre_split=[x for x in rows if x['ts']<int(SPLIT.timestamp())]
 if len(pre_split)<ROLL+TREND+PULL+HOLD: emit(out,'EVIDENCE-FAIL',reason='insufficient-pre-oos-warmup',pre_oos_rows=len(pre_split),parameter_tuning=False);return
 events=[];last=-10**9;begin=max(TREND,PULL,ROLL)+1
 for i in range(begin,len(rows)-HOLD):
  bar=rows[i]
  if bar['ts']<int(START.timestamp()) or bar['ts']>=int(END.timestamp()) or i-last<DECLUSTER:continue
  try:
   trend_ret=math.log(rows[i-1]['c']/rows[i-1-TREND]['c']);pull_ret=math.log(rows[i]['c']/rows[i-PULL]['c'])
  except (ValueError,ZeroDivisionError): emit(out,'EVIDENCE-FAIL',reason='return-construction',parameter_tuning=False);return
  hist=[abs(math.log(rows[j]['c']/rows[j-PULL]['c'])) for j in range(i-ROLL,i) if j>=PULL]
  if len(hist)<ROLL:continue
  threshold=quantile(hist,Q);side=None
  if trend_ret>0 and pull_ret<0 and abs(pull_ret)>threshold:side='LONG'
  elif trend_ret<0 and pull_ret>0 and abs(pull_ret)>threshold:side='SHORT'
  if side is None:continue
  entry=rows[i+1]['o'];exitp=rows[i+HOLD]['o'];q=exitp/entry;gross=q-1 if side=='LONG' else 1-q
  if bar['ts']<int(SPLIT.timestamp()):part='IS'
  elif bar['ts']<int(CUT.timestamp()):part='OOS_A'
  else:part='OOS_B'
  events.append({'ts':bar['ts'],'side':side,'gross':gross,'net10':gross-COST,'net20':gross-COST_STRESS,'part':part});last=i
 oos=[x for x in events if x['part']!='IS'];a=[x for x in events if x['part']=='OOS_A'];b=[x for x in events if x['part']=='OOS_B']
 pl10,ps10=side_stats(oos,'net10');pl20,ps20=side_stats(oos,'net20')
 a_l10,a_s10=side_stats(a,'net10');a_l20,a_s20=side_stats(a,'net20')
 b_l10,b_s10=side_stats(b,'net10');b_l20,b_s20=side_stats(b,'net20')
 breadth=min(a_l10['n'],a_s10['n'],b_l10['n'],b_s10['n'])>=PART_MIN_SIDE_N
 pooled_support=passes(pl10,ps10,pl20,ps20,POOLED_MIN_SIDE_N)
 a_support=passes(a_l10,a_s10,a_l20,a_s20,PART_MIN_SIDE_N)
 b_support=passes(b_l10,b_s10,b_l20,b_s20,PART_MIN_SIDE_N)
 if not breadth:
  state='INSUFFICIENT-PARTITION-BREADTH'
 else:
  state='CROSS-ASSET-CONCENTRATION-REPLICATED' if (pooled_support and a_support and not b_support) else 'CROSS-ASSET-CONCENTRATION-NOT-REPLICATED'
 emit(out,state,
  market=f'{SYMBOL} Binance USDT-M perpetual',
  contract={'parent_object':'SL-VAL-TREND-PULLBACK-001','claim_under_test':'ETH temporal concentration pattern replicates on one preselected materially distinct crypto asset without tuning','asset_selection':'SOLUSDT selected outcome-blind before SOL outcomes as a liquid non-ETH crypto perpetual; no asset screen','predecessor':'SL-VAL-TREND-PULLBACK-SIDE-ASYMMETRY-DEPENDENCE-001','tf':'4h','trend':'strictly-prior 180-bar return sign','pullback':'3-bar counter-trend move whose absolute return exceeds strictly-prior 1080-bar 90th percentile','entry':'next_bar_open','hold_bars':12,'decluster_bars':18,'split':'2025-01-01','oos_end':'2026-08-01','partition_cut':'2025-10-16T12:00:00Z exact midpoint of frozen OOS window','pooled_min_side_n':POOLED_MIN_SIDE_N,'partition_min_side_n':PART_MIN_SIDE_N,'cost_10bps':COST,'cost_stress_20bps':COST_STRESS,'material_gap':MATERIAL_GAP,'short_return':'1-exit_over_entry fixed entry-notional','long_return':'exit_over_entry-1','replication_gate':'pooled support AND OOS_A support AND NOT OOS_B support, with unchanged 25bp/sign gates','parameter_tuning':False},
  pooled={'long_10bps':pl10,'short_10bps':ps10,'long_20bps':pl20,'short_20bps':ps20,'support_gate':pooled_support},
  oos_a={'start':'2025-01-01T00:00:00Z','end':'2025-10-16T12:00:00Z','long_10bps':a_l10,'short_10bps':a_s10,'long_20bps':a_l20,'short_20bps':a_s20,'support_gate':a_support},
  oos_b={'start':'2025-10-16T12:00:00Z','end':'2026-08-01T00:00:00Z','long_10bps':b_l10,'short_10bps':b_s10,'long_20bps':b_l20,'short_20bps':b_s20,'support_gate':b_support},
  event_count=len(events),source_files=sources,parameter_tuning=False,
  limitations=['single cross-asset replication cannot establish a universal regime law','SOLUSDT and ETHUSDT remain exposed to shared crypto macro regimes','fixed 10/20bp drag omits funding, dynamic spread/slippage, latency and impact','a replicated concentration supports only regime-local dependence concern, not a LONG-disable or SHORT-only trading rule','a non-replication rejects portability of this exact concentration pattern; it does not reject the parent Trend-Pullback strategy'])
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--job',required=True);ap.add_argument('--output',required=True);args=ap.parse_args();main(args.output,args.job)
