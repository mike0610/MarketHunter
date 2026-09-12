import argparse,csv,hashlib,io,json,math,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path

OBJECT_ID='SL-VAL-TAKER-FLOW-PRESCREEN-001-REPAIR-EXEC-001'
ASSETS=['BTCUSDT','ETHUSDT','BNBUSDT','ADAUSDT','XRPUSDT','DOGEUSDT','LINKUSDT','LTCUSDT']
TF='1h'; WARM=datetime(2023,1,1,tzinfo=timezone.utc); START=datetime(2023,7,1,tzinfo=timezone.utc); SPLIT=datetime(2025,1,1,tzinfo=timezone.utc); END=datetime(2026,8,1,tzinfo=timezone.utc)
ROLL=168; THRESH=720; HOLD=4; COST10=.001; COST20=.002
MAX_INVALID_TOTAL=len(ASSETS); MAX_INVALID_PER_SYMBOL=1

def emit(out,state,**x):
 p=Path(out);p.mkdir(parents=True,exist_ok=True);(p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':state,**x},indent=2,sort_keys=True))
def get(u):return urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'MarketHunter-Research/1.0'}),timeout=30).read()
def finite_pos(x):return math.isfinite(x) and x>0
def note_bad(bad,sym,ts,kind,value):
 key=(sym,int(ts),kind)
 if key not in bad:bad[key]={'symbol':sym,'ts':int(ts),'kind':kind,'value':repr(value)}
def safe_ret(curr,prev,bad,sym,ts,kind):
 if not finite_pos(prev):
  note_bad(bad,sym,ts,kind+'_denominator',prev);return None
 if not finite_pos(curr):
  note_bad(bad,sym,ts,kind+'_numerator',curr);return None
 return curr/prev-1.0
def bad_summary(bad):
 vals=sorted(bad.values(),key=lambda x:(x['symbol'],x['ts'],x['kind']))
 by={s:sum(x['symbol']==s for x in vals) for s in ASSETS}
 material=len(vals)>MAX_INVALID_TOTAL or any(n>MAX_INVALID_PER_SYMBOL for n in by.values())
 return {'count':len(vals),'by_symbol':by,'examples':vals[:50],'material':material,'policy':{'max_invalid_total':MAX_INVALID_TOTAL,'max_invalid_per_symbol':MAX_INVALID_PER_SYMBOL}}
def month(sym,y,m,bad):
 base=f'https://data.binance.vision/data/spot/monthly/klines/{sym}/{TF}';n=f'{sym}-{TF}-{y}-{m:02d}.zip';u=f'{base}/{n}';z=get(u);e=get(u+'.CHECKSUM').decode().split()[0].lower();a=hashlib.sha256(z).hexdigest()
 if e!=a:raise ValueError('checksum '+n)
 rows=[]
 with zipfile.ZipFile(io.BytesIO(z)) as q:
  name=[v for v in q.namelist() if not v.endswith('/')][0]
  for r in csv.reader(io.TextIOWrapper(q.open(name))):
   try:raw=int(r[0]);o=float(r[1]);c=float(r[4]);v=float(r[5]);tb=float(r[9])
   except:continue
   ts=int(raw/1e6 if raw>10**14 else raw/1e3)
   if not math.isfinite(v) or v<=0:continue
   if not finite_pos(o):note_bad(bad,sym,ts,'open',o)
   if not finite_pos(c):note_bad(bad,sym,ts,'close',c)
   if not math.isfinite(tb):note_bad(bad,sym,ts,'taker_buy_base_volume',tb);continue
   flow=(2.0*tb-v)/v
   ret=safe_ret(c,o,bad,sym,ts,'same_bar_return')
   rows.append((ts,o,c,ret,flow))
 return rows,{'symbol':sym,'url':u,'sha256':a,'rows':len(rows)}
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
def self_test():
 b={}
 assert safe_ret(2.0,1.0,b,'TEST',1,'fixture')==1.0
 assert safe_ret(2.0,0.0,b,'TEST',2,'fixture') is None
 assert safe_ret(2.0,float('nan'),b,'TEST',3,'fixture') is None
 assert safe_ret(float('inf'),1.0,b,'TEST',4,'fixture') is None
 assert len(b)==3

def main(out,job):
 self_test()
 if json.loads(Path(job).read_text()).get('object_id')!=OBJECT_ID:emit(out,'BLOCKED-EVIDENCE',reason='object mismatch',parameter_tuning=False);return
 data={};files=[];bad={}
 try:
  for sym in ASSETS:
   rows=[]
   for y in range(2023,2027):
    for m in range(1,13):
     d=datetime(y,m,1,tzinfo=timezone.utc)
     if d<WARM or d>=END:continue
     a,b=month(sym,y,m,bad);rows+=a;files.append(b)
   data[sym]={ts:(o,c,r,f) for ts,o,c,r,f in rows}
 except Exception as e:
  emit(out,'PROVIDER-BLOCKED',reason=repr(e),invalid_price=bad_summary(bad),parameter_tuning=False);return
 if bad_summary(bad)['material']:
  emit(out,'PROVIDER-BLOCKED',reason='material invalid-price evidence before scoring',invalid_price=bad_summary(bad),source_files=files,parameter_tuning=False);return
 common=sorted(set.intersection(*[set(data[s]) for s in ASSETS]));idx={t:i for i,t in enumerate(common)}
 residual={s:{} for s in ASSETS}
 for s in ASSETS:
  for i in range(ROLL,len(common)):
   t=common[i];hist=common[i-ROLL:i];xs=[];ys=[]
   for h in hist:
    j=idx[h]
    if j<=0:continue
    rr=safe_ret(data[s][h][2],data[s][common[j-1]][2],bad,s,h,'close_to_close_return')
    y=data[s][h][3]
    if rr is None or y is None or not math.isfinite(y):continue
    xs.append(rr);ys.append(y)
   if len(xs)!=len(ys) or len(xs)<20 or i==0:continue
   x=safe_ret(data[s][t][2],data[s][common[i-1]][2],bad,s,t,'close_to_close_return');y=data[s][t][3]
   if x is None or y is None or not math.isfinite(y):continue
   z=lin_resid(xs,ys,x,y)
   if z is not None and math.isfinite(z):residual[s][t]=z
 if bad_summary(bad)['material']:
  emit(out,'PROVIDER-BLOCKED',reason='material invalid-price evidence during residualization',invalid_price=bad_summary(bad),source_files=files,parameter_tuning=False);return
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
   gross=safe_ret(data[s][common[i+HOLD+1]][0],data[s][common[i+1]][0],bad,s,t,'event_open_to_open_return')
   if gross is None:continue
   gross=side*gross
   ts_events.append({'ts':t,'symbol':s,'side':side,'residual':z,'net10':gross-COST10,'net20':gross-COST20,'period':period});last_ts[s]=i
  avail=[(residual[s].get(t),s) for s in ASSETS if residual[s].get(t) is not None]
  if len(avail)==len(ASSETS) and i-last_x>=HOLD:
   q=sorted(avail);shorts=[x[1] for x in q[:2]];longs=[x[1] for x in q[-2:]]
   lr=[];sr=[]
   for s in longs:
    r=safe_ret(data[s][common[i+HOLD+1]][0],data[s][common[i+1]][0],bad,s,t,'xs_open_to_open_return')
    if r is None:break
    lr.append(r)
   for s in shorts:
    r=safe_ret(data[s][common[i+HOLD+1]][0],data[s][common[i+1]][0],bad,s,t,'xs_open_to_open_return')
    if r is None:break
    sr.append(r)
   if len(lr)!=2 or len(sr)!=2:continue
   gross=.5*(sum(lr)/2.0)+.5*(sum(-r for r in sr)/2.0)
   xs_events.append({'ts':t,'longs':longs,'shorts':shorts,'net10':gross-COST10,'net20':gross-COST20,'period':period});last_x=i
 if bad_summary(bad)['material']:
  emit(out,'PROVIDER-BLOCKED',reason='material invalid-price evidence during event construction',invalid_price=bad_summary(bad),source_files=files,parameter_tuning=False);return
 def pack(ev):
  o=[e for e in ev if e['period']=='OOS'];s10=stats([e['net10'] for e in o]);s20=stats([e['net20'] for e in o]);return {'event_count':len(ev),'is_10bps':stats([e['net10'] for e in ev if e['period']=='IS']),'oos_10bps':s10,'oos_20bps':s20,'verdict':verdict(s10,s20)}
 tpack=pack(ts_events);xpack=pack(xs_events)
 terminal='OUTCOME-COMPLETE' if tpack['verdict']!='BLOCKED-EVIDENCE' or xpack['verdict']!='BLOCKED-EVIDENCE' else 'BLOCKED-EVIDENCE'
 emit(out,terminal,contract={'purpose':'bounded information-value prescreen only; not broad-universe promotion evidence','parent_object':'SL-VAL-TAKER-FLOW-PRESCREEN-001','repair':'deterministic non-finite/non-positive price denominator guard only','repair_policy':'skip invalid return observation; record provenance; PROVIDER-BLOCKED if >8 unique invalid observations total or >1 for any symbol','self_test':'zero/nan/inf denominator/numerator cannot crash or become a signal','assets':ASSETS,'venue':'Binance Spot public klines','tf':TF,'flow_proxy':'(2*taker_buy_base_volume-total_base_volume)/total_base_volume','return_control':'rolling 168h linear residualization versus same-bar close-to-close return','time_series_branch':'asset-local residual top/bottom rolling 720h decile, continuation sign, 4h non-overlap','cross_sectional_branch':'hourly rank residual; long top2 short bottom2, 4h non-overlap','entry':'next_bar_open benchmark only','hold_hours':HOLD,'costs':[COST10,COST20],'split':'2025-01-01','parameter_tuning':False,'execution_note':'signal-edge prescreen only; no market-order promotion. Any paper promotion requires separately frozen LIMIT-first contract.'},time_series=tpack,cross_sectional=xpack,invalid_price=bad_summary(bad),source_files=files,parameter_tuning=False,limitations=['fixed eight-asset long-lived basket; not broad-universe evidence','spot archives used as price/flow evidence; short branch is diagnostic only','current test measures venue-local taker-flow proxy, not academic world order flow','simple linear return control only','no ML, leverage, sizing, funding, or order-book execution model'])
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
