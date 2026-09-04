import argparse,csv,hashlib,io,json,math,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path

OBJECT_ID='SL-VAL-TAKER-FLOW-PRESCREEN-001'
ASSETS=['BTCUSDT','ETHUSDT','BNBUSDT','ADAUSDT','XRPUSDT','DOGEUSDT','LINKUSDT','LTCUSDT']
TF='1h'; WARM=datetime(2023,1,1,tzinfo=timezone.utc); START=datetime(2023,7,1,tzinfo=timezone.utc); SPLIT=datetime(2025,1,1,tzinfo=timezone.utc); END=datetime(2026,8,1,tzinfo=timezone.utc)
ROLL=168; THRESH=720; HOLD=4; COST10=.001; COST20=.002
MAX_INVALID_PRICE_ROWS=20; MAX_INVALID_PRICE_RATE=.001


def emit(out,state,**x):
 p=Path(out);p.mkdir(parents=True,exist_ok=True);(p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':state,**x},indent=2,sort_keys=True))
def get(u):return urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'MarketHunter-Research/1.0'}),timeout=30).read()
def month(sym,y,m):
 base=f'https://data.binance.vision/data/spot/monthly/klines/{sym}/{TF}';n=f'{sym}-{TF}-{y}-{m:02d}.zip';u=f'{base}/{n}';z=get(u);e=get(u+'.CHECKSUM').decode().split()[0].lower();a=hashlib.sha256(z).hexdigest()
 if e!=a:raise ValueError('checksum '+n)
 rows=[]
 with zipfile.ZipFile(io.BytesIO(z)) as q:
  name=[v for v in q.namelist() if not v.endswith('/')][0]
  for r in csv.reader(io.TextIOWrapper(q.open(name))):
   try:
    raw=int(r[0]);o=float(r[1]);c=float(r[4]);v=float(r[5]);tb=float(r[9])
   except:continue
   ts=int(raw/1e6 if raw>10**14 else raw/1e3)
   if v<=0:continue
   flow=(2.0*tb-v)/v
   ret=c/o-1.0 if o else 0.0
   rows.append((ts,o,c,ret,flow))
 return rows,{'symbol':sym,'url':u,'sha256':a,'rows':len(rows)}
def valid_price(x):return isinstance(x,(int,float)) and math.isfinite(x) and x>0
def safe_ratio_return(numer,denom):
 if not valid_price(numer) or not valid_price(denom):return None
 return numer/denom-1.0
def pct(vals,p):
 if not vals:return None
 s=sorted(vals);k=(len(s)-1)*p;f=math.floor(k);c=math.ceil(k)
 if f==c:return s[int(k)]
 return s[f]*(c-k)+s[c]*(k-f)
def lin_resid(xs,ys,x,y):
 n=len(xs)
 if n<20:return None
 mx=sum(xs)/n;my=sum(ys)/n;vx=sum((z-mx)**2 for z in xs)
 b=sum((xs[i]-mx)*(ys[i]-my) for i in range(n))/vx if vx>0 else 0.0
 a=my-b*mx
 return y-(a+b*x)
def stats(arr):
 if not arr:return {'n':0,'mean':None,'median':None,'hit':None,'pf':None,'cum':None,'max_dd':None}
 s=sorted(arr);med=s[len(s)//2] if len(s)%2 else (s[len(s)//2-1]+s[len(s)//2])/2;g=sum(x for x in arr if x>0);l=-sum(x for x in arr if x<0);eq=pk=1.0;dd=0.0
 for x in arr:eq*=1+x;pk=max(pk,eq);dd=min(dd,eq/pk-1)
 return {'n':len(arr),'mean':sum(arr)/len(arr),'median':med,'hit':sum(x>0 for x in arr)/len(arr),'pf':g/l if l else None,'cum':eq-1,'max_dd':dd}
def verdict(s10,s20):
 if s10['n']<30:return 'BLOCKED-EVIDENCE'
 if s10['mean']>0 and (s10['pf'] or 0)>1 and s20['mean']>0 and (s20['pf'] or 0)>1:return 'CANDIDATE'
 return 'REJECTED'
def main(out,job):
 try:
  if json.loads(Path(job).read_text()).get('object_id')!=OBJECT_ID:raise ValueError('object mismatch')
  data={};files=[]
  for sym in ASSETS:
   rows=[]
   for y in range(2023,2027):
    for m in range(1,13):
     d=datetime(y,m,1,tzinfo=timezone.utc)
     if d<WARM or d>=END:continue
     a,b=month(sym,y,m);rows+=a;files.append(b)
   data[sym]={ts:(o,c,r,f) for ts,o,c,r,f in rows}
 except Exception as e:
  emit(out,'PROVIDER-BLOCKED',reason=repr(e),parameter_tuning=False);return
 common=sorted(set.intersection(*[set(data[s]) for s in ASSETS]));idx={t:i for i,t in enumerate(common)}
 invalid_price_rows={};price_ratio_checks=0
 def record_invalid(sym,ts_now,ts_prev,context,numer,denom):
  key=(sym,ts_now,ts_prev,context)
  if key not in invalid_price_rows:
   invalid_price_rows[key]={'symbol':sym,'ts':ts_now,'prev_ts':ts_prev,'context':context,'numerator':numer,'denominator':denom}
 def checked_return(sym,ts_now,ts_prev,context):
  nonlocal price_ratio_checks
  price_ratio_checks+=1
  numer=data[sym][ts_now][2];denom=data[sym][ts_prev][2]
  v=safe_ratio_return(numer,denom)
  if v is None:record_invalid(sym,ts_now,ts_prev,context,numer,denom)
  return v
 residual={s:{} for s in ASSETS}
 for s in ASSETS:
  for i in range(ROLL,len(common)):
   t=common[i]
   xs=[];ys=[]
   for j in range(i-ROLL,i):
    if j<=0:continue
    h=common[j];rv=checked_return(s,h,common[j-1],'residual_history')
    if rv is not None:
     xs.append(rv);ys.append(data[s][h][3])
   if len(xs)!=len(ys) or len(xs)<20 or i==0:continue
   x=checked_return(s,t,common[i-1],'residual_current');y=data[s][t][3]
   if x is None:continue
   z=lin_resid(xs,ys,x,y)
   if z is not None:residual[s][t]=z
 ts_events=[];xs_events=[];last_ts={s:-10**9 for s in ASSETS};last_x=-10**9
 for i,t in enumerate(common):
  if t<int(START.timestamp()) or t>=int(END.timestamp()) or i+HOLD+1>=len(common) or i<THRESH:continue
  period='IS' if t<int(SPLIT.timestamp()) else 'OOS'
  for s in ASSETS:
   z=residual[s].get(t)
   if z is None or i-last_ts[s]<HOLD:continue
   hist=[residual[s].get(common[j]) for j in range(max(ROLL,i-THRESH),i)];hist=[v for v in hist if v is not None]
   if len(hist)<200:continue
   lo=pct(hist,.10);hi=pct(hist,.90);side=1 if z>=hi else (-1 if z<=lo else 0)
   if not side:continue
   entry=data[s][common[i+1]][0];exitp=data[s][common[i+HOLD+1]][0];price_ratio_checks+=1
   gross0=safe_ratio_return(exitp,entry)
   if gross0 is None:
    record_invalid(s,common[i+HOLD+1],common[i+1],'time_series_execution',exitp,entry);continue
   gross=side*gross0
   ts_events.append({'ts':t,'symbol':s,'side':side,'residual':z,'net10':gross-COST10,'net20':gross-COST20,'period':period});last_ts[s]=i
  avail=[(residual[s].get(t),s) for s in ASSETS if residual[s].get(t) is not None]
  if len(avail)==len(ASSETS) and i-last_x>=HOLD:
   q=sorted(avail);shorts=[x[1] for x in q[:2]];longs=[x[1] for x in q[-2:]]
   long_returns=[];short_returns=[];bad_xs=False
   for s in longs:
    price_ratio_checks+=1;rv=safe_ratio_return(data[s][common[i+HOLD+1]][0],data[s][common[i+1]][0])
    if rv is None:
     record_invalid(s,common[i+HOLD+1],common[i+1],'cross_sectional_long_execution',data[s][common[i+HOLD+1]][0],data[s][common[i+1]][0]);bad_xs=True;break
    long_returns.append(rv)
   if bad_xs:continue
   for s in shorts:
    price_ratio_checks+=1;rv=safe_ratio_return(data[s][common[i+HOLD+1]][0],data[s][common[i+1]][0])
    if rv is None:
     record_invalid(s,common[i+HOLD+1],common[i+1],'cross_sectional_short_execution',data[s][common[i+HOLD+1]][0],data[s][common[i+1]][0]);bad_xs=True;break
    short_returns.append(-rv)
   if bad_xs:continue
   lg=sum(long_returns)/2.0;sh=sum(short_returns)/2.0
   gross=.5*lg+.5*sh;xs_events.append({'ts':t,'longs':longs,'shorts':shorts,'net10':gross-COST10,'net20':gross-COST20,'period':period});last_x=i
 invalid_examples=list(invalid_price_rows.values())
 invalid_rate=(len(invalid_examples)/price_ratio_checks) if price_ratio_checks else 0.0
 if len(invalid_examples)>MAX_INVALID_PRICE_ROWS or invalid_rate>MAX_INVALID_PRICE_RATE:
  emit(out,'PROVIDER-BLOCKED',reason='material invalid/non-finite/non-positive price rows',data_quality={'invalid_price_rows':len(invalid_examples),'price_ratio_checks':price_ratio_checks,'invalid_rate':invalid_rate,'max_invalid_rows':MAX_INVALID_PRICE_ROWS,'max_invalid_rate':MAX_INVALID_PRICE_RATE,'examples':invalid_examples[:50]},parameter_tuning=False);return
 def pack(ev):
  o=[e for e in ev if e['period']=='OOS'];s10=stats([e['net10'] for e in o]);s20=stats([e['net20'] for e in o]);return {'event_count':len(ev),'is_10bps':stats([e['net10'] for e in ev if e['period']=='IS']),'oos_10bps':s10,'oos_20bps':s20,'verdict':verdict(s10,s20)}
 tpack=pack(ts_events);xpack=pack(xs_events)
 terminal='OUTCOME-COMPLETE' if tpack['verdict']!='BLOCKED-EVIDENCE' or xpack['verdict']!='BLOCKED-EVIDENCE' else 'BLOCKED-EVIDENCE'
 emit(out,terminal,data_quality={'invalid_price_rows':len(invalid_examples),'price_ratio_checks':price_ratio_checks,'invalid_rate':invalid_rate,'max_invalid_rows':MAX_INVALID_PRICE_ROWS,'max_invalid_rate':MAX_INVALID_PRICE_RATE,'examples':invalid_examples[:50]},contract={'purpose':'bounded information-value prescreen only; not broad-universe promotion evidence','assets':ASSETS,'venue':'Binance Spot public klines','tf':TF,'flow_proxy':'(2*taker_buy_base_volume-total_base_volume)/total_base_volume','return_control':'rolling 168h linear residualization versus same-bar close-to-close return','time_series_branch':'asset-local residual top/bottom rolling 720h decile, continuation sign, 4h non-overlap','cross_sectional_branch':'hourly rank residual; long top2 short bottom2, 4h non-overlap','entry':'next_bar_open benchmark only','hold_hours':HOLD,'costs':[COST10,COST20],'split':'2025-01-01','parameter_tuning':False,'execution_note':'signal-edge prescreen only; no market-order promotion. Any paper promotion requires separately frozen LIMIT-first contract.'},time_series=tpack,cross_sectional=xpack,source_files=files,parameter_tuning=False,limitations=['fixed eight-asset long-lived basket; not broad-universe evidence','spot archives used as price/flow evidence; short branch is diagnostic only','current test measures venue-local taker-flow proxy, not academic world order flow','simple linear return control only','no ML, leverage, sizing, funding, or order-book execution model'])
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
