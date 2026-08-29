import argparse,csv,hashlib,io,json,math,statistics,urllib.request,zipfile
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
OBJECT_ID='SL-VAL-VOL-COMPRESSION-BREAKOUT-001'
BASE='https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1h'
WARM=datetime(2021,11,1,tzinfo=timezone.utc);START=datetime(2022,1,1,tzinfo=timezone.utc);SPLIT=datetime(2025,1,1,tzinfo=timezone.utc);END=datetime(2026,8,1,tzinfo=timezone.utc)
VOLWIN=24;ROLL=720;Q=.20;BREAK=24;HOLD=6;DECLUSTER=12;COST=.001

def emit(o,s,**x):
 p=Path(o);p.mkdir(parents=True,exist_ok=True);(p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':s,**x},indent=2,sort_keys=True))
def get(u):return urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'MarketHunter-Research/1.0'}),timeout=30).read()
def mon(y,m):
 n=f'BTCUSDT-1h-{y}-{m:02d}.zip';u=f'{BASE}/{n}';z=get(u);e=get(u+'.CHECKSUM').decode().split()[0].lower();a=hashlib.sha256(z).hexdigest()
 if e!=a:raise ValueError('checksum '+n)
 r=[]
 with zipfile.ZipFile(io.BytesIO(z)) as q:
  for x in csv.reader(io.TextIOWrapper(q.open([v for v in q.namelist() if not v.endswith('/')][0]))):
   try:raw=int(x[0]);o,h,l,c=map(float,x[1:5])
   except:continue
   ts=raw/1e6 if raw>10**14 else raw/1e3;r.append({'ts':int(ts),'o':o,'h':h,'l':l,'c':c})
 return r,{'url':u,'sha256':a,'rows':len(r)}
def quantile(a,q):
 s=sorted(a);x=(len(s)-1)*q;lo=int(math.floor(x));hi=int(math.ceil(x));return s[lo] if lo==hi else s[lo]*(hi-x)+s[hi]*(x-lo)
def st(a):
 if not a:return {'n':0,'mean':None,'median':None,'hit':None,'pf':None,'cum':None,'max_dd':None}
 s=sorted(a);med=statistics.median(s);g=sum(x for x in a if x>0);l=-sum(x for x in a if x<0);eq=pk=1.;dd=0.
 for x in a:eq*=1+x;pk=max(pk,eq);dd=min(dd,eq/pk-1)
 return {'n':len(a),'mean':sum(a)/len(a),'median':med,'hit':sum(x>0 for x in a)/len(a),'pf':g/l if l else None,'cum':eq-1,'max_dd':dd}
def bucket(events):
 b=defaultdict(list)
 for e in events:
  d=datetime.fromtimestamp(e['ts'],tz=timezone.utc);b[f'{d.year}-{d.month:02d}'].append(e['net'])
 out={k:st(v) for k,v in sorted(b.items())};q=list(out.values())
 return {'months':out,'positive_mean_month_fraction':sum(v['mean']>0 for v in q)/len(q) if q else None}
def main(out,job):
 try:
  if json.loads(Path(job).read_text()).get('object_id')!=OBJECT_ID:raise ValueError('object')
  rows=[];files=[]
  for y in range(2021,2027):
   for m in range(1,13):
    d=datetime(y,m,1,tzinfo=timezone.utc)
    if d<WARM or d>=END:continue
    a,b=mon(y,m);rows+=a;files.append(b)
 except Exception as e:emit(out,'PROVIDER-BLOCKED',reason=repr(e),parameter_tuning=False);return
 rows.sort(key=lambda x:x['ts']);rets=[None]
 for i in range(1,len(rows)):rets.append(math.log(rows[i]['c']/rows[i-1]['c']))
 rv=[None]*len(rows)
 for i in range(VOLWIN,len(rows)):
  w=[x for x in rets[i-VOLWIN+1:i+1] if x is not None]
  if len(w)==VOLWIN:rv[i]=statistics.pstdev(w)
 events=[];last=-10**9
 start=max(ROLL+VOLWIN,BREAK+2)
 for i in range(start,len(rows)-HOLD):
  b=rows[i]
  if b['ts']<int(START.timestamp()) or b['ts']>=int(END.timestamp()) or i-last<DECLUSTER:continue
  prior_rv=[x for x in rv[i-ROLL-1:i-1] if x is not None]
  if len(prior_rv)<ROLL:continue
  threshold=quantile(prior_rv,Q);compressed=rv[i-1] is not None and rv[i-1]<=threshold
  if not compressed:continue
  hi=max(x['h'] for x in rows[i-BREAK:i]);lo=min(x['l'] for x in rows[i-BREAK:i]);c=b['c']
  if c>hi:side='LONG'
  elif c<lo:side='SHORT'
  else:continue
  entry=rows[i+1]['o'];exitp=rows[i+HOLD]['o'];gross=exitp/entry-1 if side=='LONG' else entry/exitp-1
  events.append({'ts':b['ts'],'side':side,'compression_rv':rv[i-1],'threshold':threshold,'gross':gross,'net':gross-COST,'net20':gross-.002,'period':'IS' if b['ts']<int(SPLIT.timestamp()) else 'OOS'});last=i
 o=[x for x in events if x['period']=='OOS'];r=[x['net'] for x in o];r20=[x['net20'] for x in o];s=st(r);s20=st(r20);wins=sorted([x for x in r if x>0],reverse=True);top=(wins[0]/sum(wins)) if wins and sum(wins)>0 else None
 if s['n']<30:v='BLOCKED-EVIDENCE'
 elif s['mean']>0 and (s['pf'] or 0)>1 and s20['mean']>0 and (top is None or top<.5):v='CANDIDATE'
 else:v='REJECTED'
 emit(out,'OUTCOME-COMPLETE',contract={'market':'BTCUSDT Spot','tf':'1h','compression':'24h realized vol at prior bar <= strictly-prior 720h 20th percentile','breakout':'current close beyond prior 24h high/low','entry':'next_bar_open','hold_bars':6,'decluster_bars':12,'cost':.001,'cost_stress':.002,'split':'2025-01-01','no_sl_tp':True,'parameter_tuning':False},is_stats=st([x['net'] for x in events if x['period']=='IS']),oos_stats_10bps=s,oos_stats_20bps=s20,oos_long=st([x['net'] for x in o if x['side']=='LONG']),oos_short=st([x['net'] for x in o if x['side']=='SHORT']),oos_time_profile=bucket(o),oos_top_positive_trade_share=top,terminal_verdict=v,event_count=len(events),source_files=files,parameter_tuning=False,limitations=['single asset first-pass','time profile diagnostic only','no spread/slippage beyond fixed round-trip cost','candidate requires separate robustness/regime gate'])
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
