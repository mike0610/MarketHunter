import argparse,csv,hashlib,io,json,math,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path

OBJECT_ID='SL-VAL-TREND-PULLBACK-SIDE-ASYMMETRY-001'
SYMBOL='ETHUSDT'
BASE=f'https://data.binance.vision/data/futures/um/monthly/klines/{SYMBOL}/4h'
WARM=datetime(2020,1,1,tzinfo=timezone.utc)
START=datetime(2021,1,1,tzinfo=timezone.utc)
SPLIT=datetime(2025,1,1,tzinfo=timezone.utc)
END=datetime(2026,8,1,tzinfo=timezone.utc)
TREND=180
PULL=3
ROLL=1080
Q=.90
HOLD=12
DECLUSTER=18
COST=.001
COST_STRESS=.002
MIN_SIDE_N=10
MATERIAL_GAP=.0025

def emit(out,state,**extra):
 p=Path(out);p.mkdir(parents=True,exist_ok=True)
 payload={'object_id':OBJECT_ID,'terminal_state':state,**extra}
 (p/'terminal_result.json').write_text(json.dumps(payload,indent=2,sort_keys=True))

def get(url):
 req=urllib.request.Request(url,headers={'User-Agent':'MarketHunter-Research/1.0'})
 return urllib.request.urlopen(req,timeout=30).read()

def month(y,m):
 name=f'{SYMBOL}-4h-{y}-{m:02d}.zip';url=f'{BASE}/{name}'
 raw=get(url)
 expected=get(url+'.CHECKSUM').decode().split()[0].lower()
 actual=hashlib.sha256(raw).hexdigest()
 if expected!=actual: raise ValueError('checksum '+name)
 rows=[]
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  members=[x for x in z.namelist() if not x.endswith('/')]
  if len(members)!=1: raise ValueError('archive-members '+name)
  for r in csv.reader(io.TextIOWrapper(z.open(members[0]))):
   try:
    ts_raw=int(r[0]);o,h,l,c=map(float,r[1:5])
   except Exception:
    continue
   if not all(math.isfinite(x) and x>0 for x in (o,h,l,c)): continue
   ts=ts_raw/1e6 if ts_raw>10**14 else ts_raw/1e3
   rows.append({'ts':int(ts),'o':o,'h':h,'l':l,'c':c})
 return rows,{'url':url,'sha256':actual,'rows':len(rows),'symbol':SYMBOL,'year':y,'month':m}

def quantile(values,q):
 s=sorted(values);x=(len(s)-1)*q;lo=int(math.floor(x));hi=int(math.ceil(x))
 return s[lo] if lo==hi else s[lo]*(hi-x)+s[hi]*(x-lo)

def stats(values):
 if not values:return {'n':0,'mean':None,'median':None,'hit':None,'pf':None,'cum':None,'max_dd':None}
 s=sorted(values);med=s[len(s)//2] if len(s)%2 else (s[len(s)//2-1]+s[len(s)//2])/2
 gains=sum(x for x in values if x>0);losses=-sum(x for x in values if x<0)
 eq=peak=1.;dd=0.
 for x in values:
  eq*=1+x;peak=max(peak,eq);dd=min(dd,eq/peak-1)
 return {'n':len(values),'mean':sum(values)/len(values),'median':med,'hit':sum(x>0 for x in values)/len(values),'pf':gains/losses if losses else None,'cum':eq-1,'max_dd':dd}

def main(out,job):
 try:
  cfg=json.loads(Path(job).read_text())
  if cfg.get('object_id')!=OBJECT_ID: raise ValueError('object-id-mismatch')
  rows=[];sources=[]
  for y in range(2020,2027):
   for m in range(1,13):
    d=datetime(y,m,1,tzinfo=timezone.utc)
    if d<WARM or d>=END: continue
    a,meta=month(y,m);rows+=a;sources.append(meta)
 except Exception as e:
  emit(out,'PROVIDER-BLOCKED',reason=repr(e),parameter_tuning=False);return
 rows.sort(key=lambda x:x['ts'])
 if not rows:
  emit(out,'EVIDENCE-FAIL',reason='no-valid-rows',parameter_tuning=False);return
 if len({x['ts'] for x in rows})!=len(rows):
  emit(out,'EVIDENCE-FAIL',reason='duplicate-kline-timestamps',parameter_tuning=False);return
 events=[];last=-10**9
 begin=max(TREND,PULL,ROLL)+1
 for i in range(begin,len(rows)-HOLD):
  bar=rows[i]
  if bar['ts']<int(START.timestamp()) or bar['ts']>=int(END.timestamp()) or i-last<DECLUSTER: continue
  try:
   trend_ret=math.log(rows[i-1]['c']/rows[i-1-TREND]['c'])
   pull_ret=math.log(rows[i]['c']/rows[i-PULL]['c'])
  except (ValueError,ZeroDivisionError):
   emit(out,'EVIDENCE-FAIL',reason='return-construction',parameter_tuning=False);return
  hist=[]
  for j in range(i-ROLL,i):
   if j<PULL: continue
   hist.append(abs(math.log(rows[j]['c']/rows[j-PULL]['c'])))
  if len(hist)<ROLL: continue
  threshold=quantile(hist,Q)
  side=None
  if trend_ret>0 and pull_ret<0 and abs(pull_ret)>threshold: side='LONG'
  elif trend_ret<0 and pull_ret>0 and abs(pull_ret)>threshold: side='SHORT'
  if side is None: continue
  entry=rows[i+1]['o'];exitp=rows[i+HOLD]['o']
  gross=exitp/entry-1 if side=='LONG' else entry/exitp-1
  events.append({'ts':bar['ts'],'side':side,'gross':gross,'net10':gross-COST,'net20':gross-COST_STRESS,'period':'IS' if bar['ts']<int(SPLIT.timestamp()) else 'OOS'})
  last=i
 oos=[x for x in events if x['period']=='OOS']
 l10=stats([x['net10'] for x in oos if x['side']=='LONG']);s10=stats([x['net10'] for x in oos if x['side']=='SHORT'])
 l20=stats([x['net20'] for x in oos if x['side']=='LONG']);s20=stats([x['net20'] for x in oos if x['side']=='SHORT'])
 if l10['n']<MIN_SIDE_N or s10['n']<MIN_SIDE_N:
  state='INSUFFICIENT-SIDE-BREADTH'
 else:
  supported=(l10['mean']<=0 and s10['mean']>0 and (s10['mean']-l10['mean'])>=MATERIAL_GAP and l20['mean']<=0 and s20['mean']>0 and (s20['mean']-l20['mean'])>=MATERIAL_GAP)
  state='SIDE-ASYMMETRY-SUPPORTED' if supported else 'SIDE-ASYMMETRY-NOT-SUPPORTED'
 emit(out,state,
      market=f'{SYMBOL} Binance USDT-M perpetual',
      contract={'parent_object':'SL-VAL-TREND-PULLBACK-001','purpose':'independent-instrument prosecution of post-observed Spot LONG/SHORT asymmetry','tf':'4h','trend':'strictly-prior 180-bar return sign','pullback':'3-bar counter-trend move whose absolute return exceeds strictly-prior 1080-bar 90th percentile','entry':'next_bar_open','hold_bars':12,'decluster_bars':18,'split':'2025-01-01','cost_10bps':COST,'cost_stress_20bps':COST_STRESS,'side_min_n':MIN_SIDE_N,'material_gap':MATERIAL_GAP,'material_gap_source':'reuses predeclared 25bp context materiality convention; not tuned to observed side gap','parameter_tuning':False},
      is_stats_10bps=stats([x['net10'] for x in events if x['period']=='IS']),
      oos_all_10bps=stats([x['net10'] for x in oos]),oos_all_20bps=stats([x['net20'] for x in oos]),
      oos_long_10bps=l10,oos_short_10bps=s10,oos_long_20bps=l20,oos_short_20bps=s20,
      oos_side_gap_10bps=(s10['mean']-l10['mean']) if l10['mean'] is not None and s10['mean'] is not None else None,
      oos_side_gap_20bps=(s20['mean']-l20['mean']) if l20['mean'] is not None and s20['mean'] is not None else None,
      event_count=len(events),source_files=sources,parameter_tuning=False,
      limitations=['USDT-M perpetual is correlated with Spot and is not independent macro-regime evidence','fixed 10/20bp round-trip drag does not model futures funding, dynamic fees, spread, slippage, latency or impact','support would validate directional asymmetry only, not promote the parent strategy','no side-specific filter or parameter is changed by this test'])
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--job',required=True);ap.add_argument('--output',required=True);args=ap.parse_args();main(args.output,args.job)
