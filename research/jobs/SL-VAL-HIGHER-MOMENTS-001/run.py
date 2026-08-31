import argparse,csv,hashlib,io,json,math,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path

OBJECT_ID='SL-VAL-HIGHER-MOMENTS-001'
ASSETS=['BTCUSDT','ETHUSDT','BNBUSDT','ADAUSDT','XRPUSDT','DOGEUSDT','LINKUSDT','LTCUSDT']
TF='1h'
WARM=datetime(2022,1,1,tzinfo=timezone.utc)
START=datetime(2022,2,1,tzinfo=timezone.utc)
SPLIT=datetime(2025,1,1,tzinfo=timezone.utc)
END=datetime(2026,8,1,tzinfo=timezone.utc)
LOOK=168
STEP=24
EXIT_OFFSET=25
COST=.001

def emit(o,s,**x):
 p=Path(o);p.mkdir(parents=True,exist_ok=True)
 (p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':s,**x},indent=2,sort_keys=True))

def get(u):
 return urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'MarketHunter-Research/1.0'}),timeout=30).read()

def mon(sym,y,m):
 base=f'https://data.binance.vision/data/spot/monthly/klines/{sym}/{TF}'
 n=f'{sym}-{TF}-{y}-{m:02d}.zip';u=f'{base}/{n}'
 z=get(u);e=get(u+'.CHECKSUM').decode().split()[0].lower();a=hashlib.sha256(z).hexdigest()
 if e!=a:raise ValueError('checksum '+n)
 r=[]
 with zipfile.ZipFile(io.BytesIO(z)) as q:
  for x in csv.reader(io.TextIOWrapper(q.open([v for v in q.namelist() if not v.endswith('/')][0]))):
   try:raw=int(x[0]);o=float(x[1]);c=float(x[4])
   except:continue
   ts=int(raw/1e6 if raw>10**14 else raw/1e3);r.append((ts,o,c))
 return r,{'symbol':sym,'url':u,'sha256':a,'rows':len(r)}

def st(a):
 if not a:return {'n':0,'mean':None,'median':None,'hit':None,'pf':None,'cum':None,'max_dd':None}
 s=sorted(a);med=s[len(s)//2] if len(s)%2 else (s[len(s)//2-1]+s[len(s)//2])/2
 g=sum(x for x in a if x>0);l=-sum(x for x in a if x<0);eq=pk=1.;dd=0.
 for x in a:eq*=1+x;pk=max(pk,eq);dd=min(dd,eq/pk-1)
 return {'n':len(a),'mean':sum(a)/len(a),'median':med,'hit':sum(x>0 for x in a)/len(a),'pf':g/l if l else None,'cum':eq-1,'max_dd':dd}

def moments(x):
 n=len(x)
 if n<20:return None
 mu=sum(x)/n
 d=[v-mu for v in x]
 m2=sum(v*v for v in d)/n
 if m2<=0:return None
 sd=math.sqrt(m2)
 skew=(sum(v**3 for v in d)/n)/(sd**3)
 kurt=(sum(v**4 for v in d)/n)/(m2*m2)-3.0
 return sd,skew,kurt

def zscores(vals):
 mu=sum(vals)/len(vals)
 var=sum((v-mu)**2 for v in vals)/len(vals)
 sd=math.sqrt(var)
 return [0.0 if sd==0 else (v-mu)/sd for v in vals]

def main(out,job):
 try:
  if json.loads(Path(job).read_text()).get('object_id')!=OBJECT_ID:raise ValueError('object')
  data={};files=[]
  for sym in ASSETS:
   rows=[]
   for y in range(2022,2027):
    for m in range(1,13):
     d=datetime(y,m,1,tzinfo=timezone.utc)
     if d<WARM or d>=END:continue
     a,b=mon(sym,y,m);rows+=a;files.append(b)
   data[sym]={ts:(o,c) for ts,o,c in rows}
 except Exception as e:
  emit(out,'PROVIDER-BLOCKED',reason=repr(e),parameter_tuning=False);return

 common=sorted(set.intersection(*[set(data[x]) for x in ASSETS]))
 events=[]
 for i in range(LOOK,len(common)-EXIT_OFFSET-1,STEP):
  ts=common[i]
  if ts<int(START.timestamp()) or ts>=int(END.timestamp()):continue
  rows=[]
  ok=True
  for s in ASSETS:
   rets=[]
   for j in range(i-LOOK+1,i+1):
    p0=data[s][common[j-1]][1];p1=data[s][common[j]][1]
    if p0<=0 or p1<=0:ok=False;break
    rets.append(math.log(p1/p0))
   if not ok:break
   mm=moments(rets)
   if mm is None:ok=False;break
   rows.append((s,*mm))
  if not ok:continue
  zv=zscores([x[1] for x in rows]);zs=zscores([x[2] for x in rows]);zk=zscores([x[3] for x in rows])
  scores=sorted([(zv[k]+zk[k]-zs[k],rows[k][0]) for k in range(len(rows))],reverse=True)
  longs=[x[1] for x in scores[:2]];shorts=[x[1] for x in scores[-2:]]
  entry_ts=common[i+1];exit_ts=common[i+EXIT_OFFSET]
  lg=sum(data[s][exit_ts][0]/data[s][entry_ts][0]-1 for s in longs)/2
  sh=sum(1-data[s][exit_ts][0]/data[s][entry_ts][0] for s in shorts)/2
  gross=.5*lg+.5*sh
  events.append({'ts':ts,'longs':longs,'shorts':shorts,'net':gross-COST,'net20':gross-.002,'period':'IS' if ts<int(SPLIT.timestamp()) else 'OOS'})

 o=[x for x in events if x['period']=='OOS'];r=[x['net'] for x in o];r20=[x['net20'] for x in o]
 s10=st(r);s20=st(r20);wins=sorted([x for x in r if x>0],reverse=True);top=wins[0]/sum(wins) if wins and sum(wins)>0 else None
 if s10['n']<30:v='BLOCKED-EVIDENCE'
 elif s10['mean']>0 and (s10['pf'] or 0)>1 and s20['mean']>0 and (top is None or top<.5):v='CANDIDATE'
 else:v='REJECTED'
 emit(out,'OUTCOME-COMPLETE',
  contract={'book':'FUTURES-DIAGNOSTIC','capital_usdt':1000,'assets':ASSETS,'universe_policy':'fixed predeclared long-lived liquid basket; NOT survivorship-aware full-market evidence','tf':TF,'lookback_hours':LOOK,'rebalance_hours':STEP,'holding_hours':24,'score':'cross-sectional z(realized_vol)+z(excess_kurtosis)-z(skewness)','long':'top 2 score assets','short':'bottom 2 score assets','portfolio':'50% equal-weight long sleeve + 50% equal-weight short sleeve','entry':'next_bar_open','exit':'open exactly 24h after entry','base_cost':.001,'stress_cost':.002,'split':'2025-01-01','edge_gate_notional':'1x','parameter_tuning':False},
  is_stats=st([x['net'] for x in events if x['period']=='IS']),
  oos_stats_10bps=s10,oos_stats_20bps=s20,oos_top_positive_period_share=top,terminal_verdict=v,event_count=len(events),source_files=files,parameter_tuning=False,
  limitations=['fixed eight-asset liquid basket cannot establish broad-market or survivorship-aware higher-moment premia','composite sign and equal weights are frozen before outcomes and are not estimated from MarketHunter results','small cross-section makes skewness and kurtosis ranks noisy','short sleeve requires futures; spot archives are synchronized price evidence only','funding/leverage excluded from base edge gate','fixed round-trip cost proxy; no order-book slippage','positive result requires separate dynamic-universe and venue robustness before promotion'])

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
