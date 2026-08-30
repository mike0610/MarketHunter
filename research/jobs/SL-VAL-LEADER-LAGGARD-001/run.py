import argparse,csv,hashlib,io,json,math,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path
OBJECT_ID='SL-VAL-LEADER-LAGGARD-001'
ASSETS=['BTCUSDT','ETHUSDT','BNBUSDT','ADAUSDT','XRPUSDT','DOGEUSDT','LINKUSDT','LTCUSDT'];LEADERS=['BTCUSDT','ETHUSDT'];LAGGARDS=[x for x in ASSETS if x not in LEADERS];TF='1h'
WARM=datetime(2022,1,1,tzinfo=timezone.utc);START=datetime(2022,7,1,tzinfo=timezone.utc);SPLIT=datetime(2025,1,1,tzinfo=timezone.utc);END=datetime(2026,8,1,tzinfo=timezone.utc);ROLL=720;Q=.95;HOLD=3;DECLUSTER=6;COST=.001

def emit(o,s,**x):
 p=Path(o);p.mkdir(parents=True,exist_ok=True);(p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':s,**x},indent=2,sort_keys=True))
def get(u):return urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'MarketHunter-Research/1.0'}),timeout=30).read()
def mon(sym,y,m):
 base=f'https://data.binance.vision/data/spot/monthly/klines/{sym}/{TF}';n=f'{sym}-{TF}-{y}-{m:02d}.zip';u=f'{base}/{n}';z=get(u);e=get(u+'.CHECKSUM').decode().split()[0].lower();a=hashlib.sha256(z).hexdigest()
 if e!=a:raise ValueError('checksum '+n)
 r=[]
 with zipfile.ZipFile(io.BytesIO(z)) as q:
  for x in csv.reader(io.TextIOWrapper(q.open([v for v in q.namelist() if not v.endswith('/')][0]))):
   try:raw=int(x[0]);o=float(x[1]);c=float(x[4])
   except:continue
   ts=int(raw/1e6 if raw>10**14 else raw/1e3);r.append((ts,o,c))
 return r,{'symbol':sym,'url':u,'sha256':a,'rows':len(r)}
def quantile(a,q):
 s=sorted(a);x=(len(s)-1)*q;lo=int(math.floor(x));hi=int(math.ceil(x));return s[lo] if lo==hi else s[lo]*(hi-x)+s[hi]*(x-lo)
def st(a):
 if not a:return {'n':0,'mean':None,'median':None,'hit':None,'pf':None,'cum':None,'max_dd':None}
 s=sorted(a);med=s[len(s)//2] if len(s)%2 else (s[len(s)//2-1]+s[len(s)//2])/2;g=sum(x for x in a if x>0);l=-sum(x for x in a if x<0);eq=pk=1.;dd=0.
 for x in a:eq*=1+x;pk=max(pk,eq);dd=min(dd,eq/pk-1)
 return {'n':len(a),'mean':sum(a)/len(a),'median':med,'hit':sum(x>0 for x in a)/len(a),'pf':g/l if l else None,'cum':eq-1,'max_dd':dd}
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
 except Exception as e:emit(out,'PROVIDER-BLOCKED',reason=repr(e),parameter_tuning=False);return
 common=sorted(set.intersection(*[set(data[x]) for x in ASSETS]));events=[];last={x:-10**9 for x in LEADERS}
 for leader in LEADERS:
  closes=[data[leader][t][1] for t in common];rets=[None]+[math.log(closes[i]/closes[i-1]) for i in range(1,len(closes))]
  for i in range(ROLL+1,len(common)-HOLD-1):
   ts=common[i]
   if ts<int(START.timestamp()) or ts>=int(END.timestamp()) or i-last[leader]<DECLUSTER:continue
   hist=[abs(x) for x in rets[i-ROLL:i] if x is not None]
   if len(hist)<ROLL:continue
   th=quantile(hist,Q);r=rets[i]
   if abs(r)<=th:continue
   side='LONG' if r>0 else 'SHORT';basket=[]
   for lag in LAGGARDS:
    entry=data[lag][common[i+1]][0];exitp=data[lag][common[i+HOLD]][0];gross=exitp/entry-1 if side=='LONG' else entry/exitp-1;basket.append(gross)
   gross=sum(basket)/len(basket);events.append({'ts':ts,'leader':leader,'side':side,'gross':gross,'net':gross-COST,'net20':gross-.002,'period':'IS' if ts<int(SPLIT.timestamp()) else 'OOS'});last[leader]=i
 o=[x for x in events if x['period']=='OOS'];r=[x['net'] for x in o];r20=[x['net20'] for x in o];s=st(r);s20=st(r20);wins=sorted([x for x in r if x>0],reverse=True);top=wins[0]/sum(wins) if wins and sum(wins)>0 else None
 if s['n']<30:v='BLOCKED-EVIDENCE'
 elif s['mean']>0 and (s['pf'] or 0)>1 and s20['mean']>0 and (top is None or top<.5):v='CANDIDATE'
 else:v='REJECTED'
 emit(out,'OUTCOME-COMPLETE',contract={'book':'FUTURES-DIAGNOSTIC','capital_usdt':1000,'leaders':LEADERS,'laggards':LAGGARDS,'tf':TF,'leader_shock':'absolute 1h return above strictly-prior 720h 95th percentile','direction':'follow leader sign in equal-weight laggard basket','entry':'next_bar_open','hold_hours':3,'decluster_hours_per_leader':6,'base_cost':.001,'stress_cost':.002,'split':'2025-01-01','edge_gate_notional':'1x','parameter_tuning':False},is_stats=st([x['net'] for x in events if x['period']=='IS']),oos_stats_10bps=s,oos_stats_20bps=s20,oos_btc_leader=st([x['net'] for x in o if x['leader']=='BTCUSDT']),oos_eth_leader=st([x['net'] for x in o if x['leader']=='ETHUSDT']),oos_top_positive_trade_share=top,terminal_verdict=v,event_count=len(events),source_files=files,parameter_tuning=False,limitations=['fixed predeclared long-lived liquid basket is a bounded probe, not full crypto universe','equal-weight laggard basket','directional SHORT legs require futures; spot source data is used only for synchronized price evidence','futures edge is diagnostic at 1x; funding and leverage are not modeled here','fixed cost proxy; no order-book slippage','leader-specific or asset-specific filters discovered after outcomes require new frozen hypothesis'])
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
