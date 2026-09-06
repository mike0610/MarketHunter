import argparse,csv,hashlib,io,json,math,urllib.parse,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path

OBJECT_ID='SL-VAL-TREND-PULLBACK-FUNDING-CONTEXT-001'
BASE='https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/4h'
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

def emit(o,s,**x):
 p=Path(o);p.mkdir(parents=True,exist_ok=True)
 (p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':s,**x},indent=2,sort_keys=True))

def get(u): return urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'MarketHunter-Research/1.0'}),timeout=30).read()

def mon(y,m):
 n=f'BTCUSDT-4h-{y}-{m:02d}.zip';u=f'{BASE}/{n}'
 z=get(u);e=get(u+'.CHECKSUM').decode().split()[0].lower();a=hashlib.sha256(z).hexdigest()
 if e!=a: raise ValueError('checksum '+n)
 r=[]
 with zipfile.ZipFile(io.BytesIO(z)) as q:
  for x in csv.reader(io.TextIOWrapper(q.open([v for v in q.namelist() if not v.endswith('/')][0]))):
   try: raw=int(x[0]);o,h,l,c=map(float,x[1:5])
   except: continue
   ts=raw/1e6 if raw>10**14 else raw/1e3
   r.append({'ts':int(ts),'o':o,'h':h,'l':l,'c':c})
 return r,{'url':u,'sha256':a,'rows':len(r)}

def quantile(a,q):
 s=sorted(a);x=(len(s)-1)*q;lo=int(math.floor(x));hi=int(math.ceil(x))
 return s[lo] if lo==hi else s[lo]*(hi-x)+s[hi]*(x-lo)

def st(a):
 if not a:return {'n':0,'mean':None,'median':None,'hit':None,'pf':None,'cum':None,'max_dd':None}
 s=sorted(a);med=s[len(s)//2] if len(s)%2 else (s[len(s)//2-1]+s[len(s)//2])/2
 g=sum(x for x in a if x>0);l=-sum(x for x in a if x<0);eq=pk=1.;dd=0.
 for x in a:eq*=1+x;pk=max(pk,eq);dd=min(dd,eq/pk-1)
 return {'n':len(a),'mean':sum(a)/len(a),'median':med,'hit':sum(x>0 for x in a)/len(a),'pf':g/l if l else None,'cum':eq-1,'max_dd':dd}

def main(out,job):
 try:
  if json.loads(Path(job).read_text()).get('object_id')!=OBJECT_ID:raise ValueError('object')
  rows=[];files=[]
  for y in range(2020,2027):
   for m in range(1,13):
    d=datetime(y,m,1,tzinfo=timezone.utc)
    if d<WARM or d>=END:continue
    a,b=mon(y,m);rows+=a;files.append(b)
 except Exception as e: emit(out,'PROVIDER-BLOCKED',reason=repr(e),parameter_tuning=False);return
 rows.sort(key=lambda x:x['ts'])
 # Funding state is frozen from strictly prior observations only.
 funding=[];cur=int(datetime(2021,7,1,tzinfo=timezone.utc).timestamp()*1000);end=int(END.timestamp()*1000)
 try:
  while cur<end:
   q=urllib.parse.urlencode({'symbol':'BTCUSDT','startTime':cur,'endTime':end,'limit':1000})
   a=json.loads(get('https://fapi.binance.com/fapi/v1/fundingRate?'+q).decode())
   if not a:break
   funding += [{'ts':int(x['fundingTime']//1000) if isinstance(x['fundingTime'],int) else int(int(x['fundingTime'])//1000),'rate':float(x['fundingRate'])} for x in a]
   nxt=max(int(x['fundingTime']) for x in a)+1
   if nxt<=cur:break
   cur=nxt
 except Exception as e:emit(out,'PROVIDER-BLOCKED',reason='funding '+repr(e),parameter_tuning=False);return
 funding=sorted({x['ts']:x for x in funding}.values(),key=lambda x:x['ts'])
 events=[];last=-10**9
 for i in range(max(TREND,PULL,ROLL)+1,len(rows)-HOLD):
  b=rows[i]
  if b['ts']<int(START.timestamp()) or b['ts']>=int(END.timestamp()) or i-last<DECLUSTER:continue
  trend_ret=math.log(rows[i-1]['c']/rows[i-1-TREND]['c'])
  pull_ret=math.log(rows[i]['c']/rows[i-PULL]['c'])
  hist=[]
  for j in range(i-ROLL,i):
   if j<PULL:continue
   hist.append(abs(math.log(rows[j]['c']/rows[j-PULL]['c'])))
  if len(hist)<ROLL:continue
  th=quantile(hist,Q)
  side=None
  if trend_ret>0 and pull_ret<0 and abs(pull_ret)>th: side='LONG'
  elif trend_ret<0 and pull_ret>0 and abs(pull_ret)>th: side='SHORT'
  if not side:continue
  prior=[x for x in funding if x['ts']<=b['ts']]
  if len(prior)<301:continue
  current=prior[-1]['rate'];histf=[x['rate'] for x in prior[-541:-1]]
  if len(histf)<300:continue
  q05=quantile(histf,.05);q95=quantile(histf,.95)
  state='CROWDED-LONG' if current>q95 else ('CROWDED-SHORT' if current<q05 else 'NORMAL')
  entry=rows[i+1]['o'];exitp=rows[i+HOLD]['o']
  gross=exitp/entry-1 if side=='LONG' else entry/exitp-1
  events.append({'ts':b['ts'],'side':side,'funding_rate':current,'funding_state':state,'trend_ret':trend_ret,'pull_ret':pull_ret,'threshold':th,'gross':gross,'net':gross-COST,'net20':gross-.002,'period':'IS' if b['ts']<int(SPLIT.timestamp()) else 'OOS'})
  last=i
 o=[x for x in events if x['period']=='OOS'];r=[x['net'] for x in o];r20=[x['net20'] for x in o];s=st(r);s20=st(r20)
 normal=st([x['net'] for x in o if x['funding_state']=='NORMAL'])
 crowded_same=st([x['net'] for x in o if (x['side']=='LONG' and x['funding_state']=='CROWDED-LONG') or (x['side']=='SHORT' and x['funding_state']=='CROWDED-SHORT')])
 crowded_opp=st([x['net'] for x in o if (x['side']=='LONG' and x['funding_state']=='CROWDED-SHORT') or (x['side']=='SHORT' and x['funding_state']=='CROWDED-LONG')])
 wins=sorted([x for x in r if x>0],reverse=True);top=(wins[0]/sum(wins)) if wins and sum(wins)>0 else None
 if crowded_same['n']<5 or normal['n']<20:v='BLOCKED-EVIDENCE'
 elif crowded_same['mean'] is not None and normal['mean'] is not None and crowded_same['mean']<normal['mean']:v='CROWDING-RISK-SUPPORTED'
 else:v='CROWDING-RISK-NOT-SUPPORTED'
 emit(out,'OUTCOME-COMPLETE',
      contract={'market':'BTCUSDT Spot','tf':'4h','trend':'strictly-prior 180-bar return sign','pullback':'3-bar counter-trend move whose absolute return exceeds strictly-prior 1080-bar 90th percentile','entry':'next_bar_open','hold_bars':12,'decluster_bars':18,'cost':.001,'cost_stress':.002,'split':'2025-01-01','no_sl_tp':True,'funding_context':'strictly-prior Binance BTC perpetual funding; 5/95 pct of prior 540 observations','parameter_tuning':False},
      is_stats=st([x['net'] for x in events if x['period']=='IS']),
      oos_stats_10bps=s,oos_stats_20bps=s20,
      oos_long=st([x['net'] for x in o if x['side']=='LONG']),
      oos_short=st([x['net'] for x in o if x['side']=='SHORT']),
      oos_funding_normal=normal,oos_crowded_same_direction=crowded_same,oos_crowded_opposite_direction=crowded_opp,
      oos_top_positive_trade_share=top,terminal_verdict=v,event_count=len(events),source_files=files,
      parameter_tuning=False,
      limitations=['single BTC structural strategy + BTC perpetual funding context','fixed hold without stop/target','no spread/slippage beyond fixed round-trip cost','candidate requires separate robustness and capital-survival gate'])
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)

