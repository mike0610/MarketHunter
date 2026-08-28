import argparse,csv,hashlib,io,json,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path
OBJECT_ID='SL-VAL-LSWEEP-001';BASE='https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1h'
START=datetime(2022,1,1,tzinfo=timezone.utc);SPLIT=datetime(2025,1,1,tzinfo=timezone.utc);END=datetime(2026,8,1,tzinfo=timezone.utc);N=24;HOLD=6;COST=.001

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
def st(a):
 if not a:return {'n':0,'mean':None,'median':None,'hit':None,'pf':None,'cum':None,'max_dd':None}
 s=sorted(a);med=s[len(s)//2] if len(s)%2 else(sum(s[len(s)//2-1:len(s)//2+1])/2);g=sum(x for x in a if x>0);l=-sum(x for x in a if x<0);eq=pk=1.;dd=0.
 for x in a:eq*=1+x;pk=max(pk,eq);dd=min(dd,eq/pk-1)
 return {'n':len(a),'mean':sum(a)/len(a),'median':med,'hit':sum(x>0 for x in a)/len(a),'pf':g/l if l else None,'cum':eq-1,'max_dd':dd}
def main(out,job):
 try:
  if json.loads(Path(job).read_text()).get('object_id')!=OBJECT_ID:raise ValueError('object')
  rows=[];files=[]
  for y in range(2021,2027):
   for m in range(1,13):
    d=datetime(y,m,1,tzinfo=timezone.utc)
    if d<datetime(2021,12,1,tzinfo=timezone.utc) or d>=END:continue
    a,b=mon(y,m);rows+=a;files.append(b)
 except Exception as e:emit(out,'PROVIDER-BLOCKED',reason=repr(e),parameter_tuning=False);return
 rows.sort(key=lambda x:x['ts']);events=[]
 for i in range(N,len(rows)-HOLD):
  b=rows[i]
  if b['ts']<int(START.timestamp()) or b['ts']>=int(END.timestamp()):continue
  hi=max(x['h'] for x in rows[i-N:i]);lo=min(x['l'] for x in rows[i-N:i]);side=None
  if b['h']>hi and b['c']<hi:side='SHORT'
  elif b['l']<lo and b['c']>lo:side='LONG'
  if not side:continue
  entry=rows[i+1]['o'];exitp=rows[i+HOLD]['o'];gross=exitp/entry-1 if side=='LONG' else entry/exitp-1
  # unconditional same-direction 6h return baseline at every eligible timestamp, defined before outcomes
  bg=exitp/entry-1 if side=='LONG' else entry/exitp-1
  events.append({'ts':b['ts'],'side':side,'gross':gross,'net':gross-COST,'net20':gross-.002,'period':'IS' if b['ts']<int(SPLIT.timestamp()) else'OOS','baseline':bg})
 o=[x for x in events if x['period']=='OOS'];r=[x['net'] for x in o];r20=[x['net20'] for x in o]
 # baseline comparator is unconditional distribution of same-direction 6h returns at all eligible bars, balanced by event side mix
 bl=[]
 for e in o:
  side=e['side']
  for i in range(N,len(rows)-HOLD,24):
   b=rows[i]
   if b['ts']<int(SPLIT.timestamp()) or b['ts']>=int(END.timestamp()):continue
   en=rows[i+1]['o'];ex=rows[i+HOLD]['o'];bl.append(ex/en-1 if side=='LONG' else en/ex-1)
 s=st(r);s20=st(r20);bs=st(bl)
 if s['n']<30:v='BLOCKED-EVIDENCE'
 elif s['mean']>0 and (s['pf'] or 0)>1 and s20['mean']>0 and bs['mean'] is not None and s['mean']>bs['mean']:v='CANDIDATE'
 else:v='REJECTED'
 emit(out,'OUTCOME-COMPLETE',contract={'market':'BTCUSDT Spot','tf':'1h','prior_range_bars':24,'hold_bars':6,'entry':'next_bar_open','cost':.001,'split':'2025-01-01','no_sl_tp':True,'parameter_tuning':False},is_stats=st([x['net'] for x in events if x['period']=='IS']),oos_stats_10bps=s,oos_stats_20bps=s20,baseline_stats=bs,terminal_verdict=v,event_count=len(events),source_files=files,parameter_tuning=False)
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
