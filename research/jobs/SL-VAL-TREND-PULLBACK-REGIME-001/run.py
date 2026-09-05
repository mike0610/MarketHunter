import argparse,csv,hashlib,io,json,math,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path

OBJECT_ID='SL-VAL-TREND-PULLBACK-REGIME-001'
SYMBOL='ETHUSDT'
BASE=f'https://data.binance.vision/data/spot/monthly/klines/{SYMBOL}/4h'
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
 n=f'{SYMBOL}-4h-{y}-{m:02d}.zip';u=f'{BASE}/{n}'
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
  entry=rows[i+1]['o'];exitp=rows[i+HOLD]['o']
  gross=exitp/entry-1 if side=='LONG' else entry/exitp-1
  regime_ret=math.log(rows[i-1]['c']/rows[i-1-720]['c'])
  regime='UP' if regime_ret>0 else 'DOWN' if regime_ret<0 else 'NEUTRAL'
  alignment='WITH-REGIME' if (side=='LONG' and regime=='UP') or (side=='SHORT' and regime=='DOWN') else 'COUNTER-REGIME'
  events.append({'ts':b['ts'],'side':side,'regime':regime,'alignment':alignment,'gross':gross,'net':gross-COST,'net20':gross-.002,'period':'IS' if b['ts']<int(SPLIT.timestamp()) else 'OOS'})
  last=i
 o=[x for x in events if x['period']=='OOS'];r=[x['net'] for x in o];r20=[x['net20'] for x in o];s=st(r);s20=st(r20)
 wins=sorted([x for x in r if x>0],reverse=True);top=(wins[0]/sum(wins)) if wins and sum(wins)>0 else None
 wr=st([x['net'] for x in o if x['alignment']=='WITH-REGIME'])
 cr=st([x['net'] for x in o if x['alignment']=='COUNTER-REGIME'])
 if wr['n']<10 or cr['n']<10:v='BLOCKED-EVIDENCE'
 elif wr['mean']>cr['mean'] and (wr['pf'] or 0)>(cr['pf'] or 0):v='REGIME-DEPENDENCE-SUPPORTED'
 else:v='REGIME-DEPENDENCE-NOT-SUPPORTED'
 emit(out,'OUTCOME-COMPLETE',market=f'{SYMBOL} Spot',
      contract={'parent_object':'SL-VAL-TREND-PULLBACK-001','purpose':'outcome-blind frozen regime-dependence falsifier','market':f'{SYMBOL} Spot','tf':'4h','trend':'strictly-prior 180-bar return sign','regime':'strictly-prior 720-bar return sign; fixed before outcome review','pullback':'3-bar counter-trend move whose absolute return exceeds strictly-prior 1080-bar 90th percentile','entry':'next_bar_open','hold_bars':12,'decluster_bars':18,'cost':.001,'cost_stress':.002,'split':'2025-01-01','no_sl_tp':True,'parameter_tuning':False},
      is_stats=st([x['net'] for x in events if x['period']=='IS']),oos_stats_10bps=s,oos_stats_20bps=s20,
      oos_long=st([x['net'] for x in o if x['side']=='LONG']),oos_short=st([x['net'] for x in o if x['side']=='SHORT']),
      oos_with_regime=wr,oos_counter_regime=cr,
      oos_top_positive_trade_share=top,terminal_verdict=v,event_count=len(events),source_files=files,parameter_tuning=False,
      limitations=['single ETHUSDT regime falsifier only','fixed hold without stop/target','no spread/slippage beyond fixed round-trip cost','support does not imply promotion eligibility'])
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
