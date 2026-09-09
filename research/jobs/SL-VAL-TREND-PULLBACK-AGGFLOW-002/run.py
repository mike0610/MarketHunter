import argparse,csv,hashlib,io,json,math,random,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path

OBJECT_ID='SL-VAL-TREND-PULLBACK-AGGFLOW-002'
BASE='https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/4h'
WARM=datetime(2020,1,1,tzinfo=timezone.utc)
START=datetime(2021,1,1,tzinfo=timezone.utc)
SPLIT=datetime(2025,1,1,tzinfo=timezone.utc)
END=datetime(2026,8,1,tzinfo=timezone.utc)
TREND=180;PULL=3;ROLL=1080;Q=.90;HOLD=12;DECLUSTER=18;COST=.001
DRAWS=50000;SEED=20260909;ALPHA=.05;MINCELL=5;LOO_REQ=.90;CONC=.80

def emit(o,s,**x):
 p=Path(o);p.mkdir(parents=True,exist_ok=True)
 (p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':s,**x},indent=2,sort_keys=True))

def get(u):
 return urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'MarketHunter-Research/1.0'}),timeout=30).read()

def mon(y,m):
 n=f'BTCUSDT-4h-{y}-{m:02d}.zip';u=f'{BASE}/{n}'
 z=get(u);exp=get(u+'.CHECKSUM').decode().split()[0].lower();act=hashlib.sha256(z).hexdigest()
 if exp!=act: raise ValueError('checksum '+n)
 out=[]
 with zipfile.ZipFile(io.BytesIO(z)) as q:
  name=[v for v in q.namelist() if not v.endswith('/')][0]
  for x in csv.reader(io.TextIOWrapper(q.open(name))):
   try:
    raw=int(x[0]);o,h,l,c=map(float,x[1:5])
   except: continue
   ts=raw/1e6 if raw>10**14 else raw/1e3
   out.append({'ts':int(ts),'o':o,'h':h,'l':l,'c':c})
 return out,{'url':u,'sha256':act,'rows':len(out)}

def quantile(a,q):
 s=sorted(a);x=(len(s)-1)*q;lo=int(math.floor(x));hi=int(math.ceil(x))
 return s[lo] if lo==hi else s[lo]*(hi-x)+s[hi]*(x-lo)

def mean(a): return sum(a)/len(a) if a else None

def diff(events):
 a=[x['net'] for x in events if x['alignment']=='COUNTER-FLOW']
 b=[x['net'] for x in events if x['alignment']=='WITH-FLOW']
 return (mean(a)-mean(b)) if a and b else None

def counts(events):
 return {'counter':sum(x['alignment']=='COUNTER-FLOW' for x in events),
         'with':sum(x['alignment']=='WITH-FLOW' for x in events)}

def main(out,job):
 try:
  cfg=json.loads(Path(job).read_text())
  if cfg.get('object_id')!=OBJECT_ID: raise ValueError('object')
  rows=[];sources=[]
  for y in range(2020,2027):
   for m in range(1,13):
    d=datetime(y,m,1,tzinfo=timezone.utc)
    if d<WARM or d>=END: continue
    a,b=mon(y,m);rows+=a;sources.append(b)
  rows.sort(key=lambda x:x['ts'])
  flow={}
  for y in range(2025,2027):
   for m in range(1,13):
    d=datetime(y,m,1,tzinfo=timezone.utc)
    if d<SPLIT or d>=END: continue
    n=f'BTCUSDT-4h-{y}-{m:02d}.zip'
    u=f'https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/4h/{n}'
    z=get(u);exp=get(u+'.CHECKSUM').decode().split()[0].lower();act=hashlib.sha256(z).hexdigest()
    if exp!=act: raise ValueError('checksum '+n)
    with zipfile.ZipFile(io.BytesIO(z)) as q:
     name=[v for v in q.namelist() if not v.endswith('/')][0]
     for x in csv.reader(io.TextIOWrapper(q.open(name))):
      try: raw=int(x[0]);vol=float(x[5]);tb=float(x[9])
      except: continue
      ts=int(raw/1e6 if raw>10**14 else raw/1e3)
      if vol>0: flow[ts]=(tb,max(0.,vol-tb))
    sources.append({'url':u,'sha256':act})
 except Exception as e:
  emit(out,'PROVIDER-BLOCKED',reason=repr(e),parameter_tuning=False);return

 events=[];last=-10**9
 for i in range(max(TREND,PULL,ROLL)+1,len(rows)-HOLD):
  b=rows[i]
  if b['ts']<int(START.timestamp()) or b['ts']>=int(END.timestamp()) or i-last<DECLUSTER: continue
  tr=math.log(rows[i-1]['c']/rows[i-1-TREND]['c'])
  pr=math.log(rows[i]['c']/rows[i-PULL]['c'])
  hist=[abs(math.log(rows[j]['c']/rows[j-PULL]['c'])) for j in range(i-ROLL,i) if j>=PULL]
  if len(hist)<ROLL: continue
  th=quantile(hist,Q);side=None
  if tr>0 and pr<0 and abs(pr)>th: side='LONG'
  elif tr<0 and pr>0 and abs(pr)>th: side='SHORT'
  if not side: continue
  vals=[]
  for k in range(1,4):
   d=flow.get(b['ts']-k*14400)
   if d and d[0]+d[1]>0: vals.append((d[0]-d[1])/(d[0]+d[1]))
  if len(vals)<3: continue
  imb=sum(vals)/3
  state='BUY-PRESSURE' if imb>0 else ('SELL-PRESSURE' if imb<0 else 'NEUTRAL')
  align='WITH-FLOW' if (side=='LONG' and state=='BUY-PRESSURE') or (side=='SHORT' and state=='SELL-PRESSURE') else 'COUNTER-FLOW'
  entry=rows[i+1]['o'];exitp=rows[i+HOLD]['o']
  gross=exitp/entry-1 if side=='LONG' else entry/exitp-1
  dt=datetime.fromtimestamp(b['ts'],tz=timezone.utc)
  events.append({'ts':b['ts'],'year':dt.year,'side':side,'alignment':align,'net':gross-COST,'period':'IS' if b['ts']<int(SPLIT.timestamp()) else 'OOS'})
  last=i

 o=[x for x in events if x['period']=='OOS']; c=counts(o); obs=diff(o)
 if obs is None or c['counter']<10 or c['with']<10:
  emit(out,'BLOCKED-EVIDENCE',oos_n=len(o),counts=c,reason='insufficient primary alignment cells',parameter_tuning=False);return

 # Two-sided randomization test with fixed seed and fixed alignment counts.
 vals=[x['net'] for x in o]; ncf=c['counter']; rng=random.Random(SEED); extreme=0
 for _ in range(DRAWS):
  idx=list(range(len(vals)));rng.shuffle(idx)
  ac=[vals[i] for i in idx[:ncf]];aw=[vals[i] for i in idx[ncf:]]
  if abs(mean(ac)-mean(aw))>=abs(obs)-1e-15: extreme+=1
 p=(extreme+1)/(DRAWS+1)

 sign=1 if obs>0 else -1
 loo=[]
 for i in range(len(o)):
  d=diff(o[:i]+o[i+1:])
  if d is not None: loo.append(1 if d*sign>0 else 0)
 loo_ret=sum(loo)/len(loo) if loo else 0

 by_year={}
 year_ok=True
 for y in sorted(set(x['year'] for x in o)):
  e=[x for x in o if x['year']==y]; cc=counts(e); dd=diff(e)
  by_year[str(y)]={'counts':cc,'mean_diff_counter_minus_with':dd}
  if cc['counter']<MINCELL or cc['with']<MINCELL or dd is None or dd*sign<=0: year_ok=False

 by_side={}
 side_ok=True
 side_abs={}
 for s in ['LONG','SHORT']:
  e=[x for x in o if x['side']==s];cc=counts(e);dd=diff(e)
  sm=sum(x['net'] for x in e)
  by_side[s]={'counts':cc,'mean_diff_counter_minus_with':dd,'sum_net':sm}
  side_abs[s]=abs(sm)
  if cc['counter']<MINCELL or cc['with']<MINCELL or dd is None or dd*sign<=0: side_ok=False
 den=sum(side_abs.values()); concentration=max(side_abs.values())/den if den>0 else 1.0

 if concentration>=CONC:
  terminal='DEPENDENCE-CONCENTRATED'
 elif p<=ALPHA and loo_ret>=LOO_REQ and year_ok and side_ok:
  terminal='ROBUSTNESS-SUPPORT'
 else:
  terminal='ROBUSTNESS-FAIL'

 emit(out,terminal,
      frozen_contract={'source_object':'SL-VAL-TREND-PULLBACK-AGGFLOW-001','signal_parameters_unchanged':True,'cost':COST,'permutation_draws':DRAWS,'seed':SEED,'alpha':ALPHA,'minimum_cell_n':MINCELL,'loo_required':LOO_REQ,'side_concentration_threshold':CONC,'parameter_tuning':False},
      oos_n=len(o),counts=c,observed_mean_diff_counter_minus_with=obs,two_sided_permutation_p=p,
      leave_one_out_sign_retention=loo_ret,by_year=by_year,by_side=by_side,side_concentration=concentration,
      source_files=sources,parameter_tuning=False,
      limitations=['same BTC OOS sample as AGGFLOW-001; this is robustness not fresh OOS','randomization tests label exchangeability, not causality','fixed 10 bps round-trip cost; no spread/slippage/latency replay','no parameter inversion or COUNTER-FLOW trading rule may be inferred'])

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
